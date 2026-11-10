import hashlib
import json
import logging
import secrets
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import connect, initialize
from .gemini import GeminiService, ReplyGenerator
from .rag import RAGService


logger = logging.getLogger(__name__)
password_hasher = PasswordHash.recommended()
COOKIE_NAME = "chatbot_session"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class User(BaseModel):
    id: int
    username: str


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class Message(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ConversationDetail(Conversation):
    messages: list[Message]


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank.")
        return value


class SendResult(BaseModel):
    conversation: Conversation
    messages: list[Message]


class ChatRequest(BaseModel):
    message: str


def create_app(
    settings: Settings | None = None,
    generator: ReplyGenerator | None = None,
    rag_service: RAGService | None = None,
) -> FastAPI:
    config = settings or Settings()
    ai = generator or GeminiService(config)
    rag = rag_service or RAGService(config)
    inflight: set[str] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize(config.database_path)
        yield
        await ai.close()

    app = FastAPI(title="Orbit Enterprise RAG API", version="2.5.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def protect_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and origin not in config.allowed_origins
        ):
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed."})
        return await call_next(request)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        logger.exception("Database operation failed", exc_info=exc)
        return JSONResponse(
            status_code=503, content={"detail": "Database unavailable. Please try again."}
        )

    def current_user(request: Request) -> User:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Please sign in.")
        with connect(config.database_path) as db:
            row = db.execute(
                """SELECT users.id, users.username FROM sessions
                   JOIN users ON users.id = sessions.user_id
                   WHERE token_hash = ? AND expires_at > ?""",
                (token_hash(token), int(time.time())),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Session expired. Please sign in.")
        return User(**dict(row))

    AuthUser = Annotated[User, Depends(current_user)]

    def start_session(db: sqlite3.Connection, user_id: int, response: Response) -> None:
        token = secrets.token_urlsafe(32)
        duration = config.session_days * 86400
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        db.execute(
            "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash(token), user_id, int(time.time()) + duration),
        )
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=duration,
            httponly=True,
            secure=config.cookie_secure,
            samesite="lax",
            path="/api",
        )

    def owned_conversation(db: sqlite3.Connection, conversation_id: str, user_id: int):
        row = db.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return dict(row)

    class AuditRequest(BaseModel):
        document_text: str = Field(min_length=1, max_length=50000)
        criteria: str = Field(default="technical accuracy, architecture, risks", max_length=1000)

    @app.get("/api/health")
    def health():
        configured = bool(config.orchestrator_keys or config.google_api_key)
        return {
            "status": "ok",
            "model": config.gemini_model,
            "embedding_model": config.embedding_model,
            "worker_audit_model": getattr(config, "worker_audit_model", "gemini-3.5-flash"),
            "ai_configured": configured,
            "orchestrator_configured": bool(config.gemini_orchestrator_key or config.orchestrator_keys),
            "worker_configured": bool(config.gemini_worker_key or config.worker_keys),
            "dual_key_isolation": True,
            "failover_active": True,
            "rag_enabled": True,
            "hybrid_search": True,
            "streaming_enabled": True,
        }

    @app.post("/api/audit")
    async def run_audit(req: AuditRequest, user: AuthUser):
        """Dedicated Worker Key heavy auditing endpoint (Project B quota)."""
        try:
            analysis = await rag.deep_technical_audit(req.document_text, req.criteria)
            return {"status": "success", "analysis": analysis}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # --- Authentication Endpoints ---
    @app.post("/api/auth/register", response_model=User, status_code=201)
    async def register(credentials: Credentials, response: Response):
        hashed = await run_in_threadpool(password_hasher.hash, credentials.password)
        with connect(config.database_path) as db:
            try:
                cursor = db.execute(
                    "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                    (credentials.username, hashed, now()),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="Username already taken.") from exc
            user_id = cursor.lastrowid
            start_session(db, user_id, response)
        return User(id=user_id, username=credentials.username)

    @app.post("/api/auth/login", response_model=User)
    async def login(credentials: Credentials, response: Response):
        with connect(config.database_path) as db:
            row = db.execute(
                "SELECT * FROM users WHERE username = ?", (credentials.username,)
            ).fetchone()
        if row is None:
            await run_in_threadpool(password_hasher.hash, credentials.password)
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        valid = await run_in_threadpool(
            password_hasher.verify, credentials.password, row["password_hash"]
        )
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        with connect(config.database_path) as db:
            start_session(db, row["id"], response)
        return User(id=row["id"], username=row["username"])

    @app.get("/api/auth/me", response_model=User)
    def me(user: AuthUser):
        return user

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            with connect(config.database_path) as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
        response.delete_cookie(
            COOKIE_NAME, path="/api", secure=config.cookie_secure, httponly=True, samesite="lax"
        )

    # --- Conversation Endpoints ---
    @app.get("/api/conversations", response_model=list[Conversation])
    def list_conversations(user: AuthUser):
        with connect(config.database_path) as db:
            rows = db.execute(
                "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC, id",
                (user.id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @app.post("/api/conversations", response_model=Conversation, status_code=201)
    def create_conversation(user: AuthUser):
        timestamp = now()
        conversation_id = uuid4().hex
        with connect(config.database_path) as db:
            db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
                (conversation_id, user.id, "New session", timestamp, timestamp),
            )
            return owned_conversation(db, conversation_id, user.id)

    @app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
    def get_conversation(conversation_id: str, user: AuthUser):
        with connect(config.database_path) as db:
            conversation = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return {**conversation, "messages": [dict(row) for row in rows]}

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(conversation_id: str, user: AuthUser):
        with connect(config.database_path) as db:
            owned_conversation(db, conversation_id, user.id)
            if conversation_id in inflight:
                raise HTTPException(status_code=409, detail="Wait for the current reply before deleting.")
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    @app.get("/api/conversations/{conversation_id}/export")
    def export_conversation(conversation_id: str, user: AuthUser):
        """Export session dialogue as formatted Markdown."""
        with connect(config.database_path) as db:
            conversation = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

        md_lines = [f"# {conversation['title']}\n\n*Exported from Orbit on {now()}*\n\n---\n"]
        for row in rows:
            speaker = "Orbit" if row["role"] == "assistant" else user.username
            md_lines.append(f"### {speaker} ({row['created_at']})\n\n{row['content']}\n\n---\n")

        return PlainTextResponse(
            content="".join(md_lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{conversation["title"][:30]}.md"'},
        )

    # --- Document Ingestion & Content Endpoints ---
    @app.post("/upload")
    @app.post("/api/upload")
    async def upload_document(
        request: Request,
        file: UploadFile = File(...),
        conversation_id: str | None = Form(None),
    ):
        """Accepts a PDF or text file, chunks by page/structure, embeds, and indexes into Qdrant."""
        if not file.filename.lower().endswith((".pdf", ".txt", ".md", ".csv", ".json")):
            raise HTTPException(status_code=400, detail="Only PDF and text files (.pdf, .txt, .md) are supported.")

        user_id = None
        token = request.cookies.get(COOKIE_NAME)
        if token:
            with connect(config.database_path) as db:
                row = db.execute(
                    "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
                    (token_hash(token), int(time.time())),
                ).fetchone()
                if row:
                    user_id = row["user_id"]

        try:
            file_bytes = await file.read()
            result = await rag.ingest_document(
                filename=file.filename,
                file_bytes=file_bytes,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.exception("Upload processing failed", exc_info=exc)
            raise HTTPException(status_code=500, detail=f"Failed to process document: {str(exc)}")

    @app.post("/api/conversations/{conversation_id}/upload")
    async def upload_conversation_document(
        conversation_id: str,
        user: AuthUser,
        file: UploadFile = File(...),
    ):
        """Uploads and indexes a document directly into the active session."""
        with connect(config.database_path) as db:
            owned_conversation(db, conversation_id, user.id)

        if not file.filename.lower().endswith((".pdf", ".txt", ".md", ".csv", ".json")):
            raise HTTPException(status_code=400, detail="Only PDF and text files are supported.")

        try:
            file_bytes = await file.read()
            result = await rag.ingest_document(
                filename=file.filename,
                file_bytes=file_bytes,
                conversation_id=conversation_id,
                user_id=user.id,
            )
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.exception("Conversation upload failed", exc_info=exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/conversations/{conversation_id}/documents")
    def get_conversation_documents(conversation_id: str, user: AuthUser):
        """Lists all document names indexed for this session."""
        with connect(config.database_path) as db:
            owned_conversation(db, conversation_id, user.id)
        docs = rag.list_documents(conversation_id=conversation_id)
        return {"documents": docs}

    @app.get("/api/conversations/{conversation_id}/documents/{filename}/content")
    def get_conversation_document_content(conversation_id: str, filename: str, user: AuthUser):
        """Provides page-by-page text for Split-Screen Document Viewer."""
        with connect(config.database_path) as db:
            owned_conversation(db, conversation_id, user.id)
        pages = rag.get_document_content(filename, conversation_id=conversation_id)
        return {"filename": filename, "pages": pages}

    @app.post("/chat")
    @app.post("/api/chat")
    async def direct_rag_chat(chat_req: ChatRequest):
        """Phase 3 Direct RAG Endpoint."""
        search_results = await rag.search_relevant_chunks(chat_req.message, limit=4)
        if not search_results:
            context = "No relevant documents found."
            sources = []
        else:
            context_parts = [
                f"Source: {hit['source']} (Page {hit.get('page', 1)})\n{hit['text']}"
                for hit in search_results
            ]
            context = "\n\n---\n\n".join(context_parts)
            sources = list(dict.fromkeys(hit["source"] for hit in search_results))

        system_prompt = (
            "You are an intelligent data assistant. Use ONLY the following document context to answer the user's question.\n"
            'If the answer is not contained in the context, explicitly state "I cannot find the answer in the provided documents."\n'
            "Do not use outside knowledge.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"USER MESSAGE: {chat_req.message}\n"
        )
        reply = await ai.reply([{"role": "user", "content": system_prompt}])
        return {
            "reply": reply,
            "sources": sources,
        }

    # --- Messaging Endpoint (with Hybrid RAG & Memory Expansion) ---
    @app.post("/api/conversations/{conversation_id}/messages", response_model=SendResult)
    async def send_message(conversation_id: str, payload: SendMessage, user: AuthUser):
        with connect(config.database_path) as db:
            owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                """SELECT role, content FROM (
                       SELECT id, role, content FROM messages
                       WHERE conversation_id = ? ORDER BY id DESC LIMIT 40
                   ) ORDER BY id""",
                (conversation_id,),
            ).fetchall()

        if conversation_id in inflight:
            raise HTTPException(status_code=409, detail="A reply is already being generated.")
        inflight.add(conversation_id)
        try:
            history = [dict(row) for row in rows]
            while history and sum(len(item["content"]) for item in history) > 40_000:
                history = history[2:]

            # Advanced Hybrid RAG Retrieval (Dense + BM25 + Cross-Encoder Rerank)
            search_results = await rag.search_relevant_chunks(
                payload.content,
                conversation_id=conversation_id,
                user_id=user.id,
                limit=4,
                history=history,
            )
            context = None
            if search_results:
                context_parts = [
                    f"[Document: {hit['source']} | Page: {hit.get('page', 1)} | Score: {hit['score']:.2f}]\n{hit['text']}"
                    for hit in search_results
                ]
                context = "\n\n---\n\n".join(context_parts)

            reply = await ai.reply(
                [*history, {"role": "user", "content": payload.content}],
                context=context,
            )

            timestamp = now()
            with connect(config.database_path) as db:
                conversation = owned_conversation(db, conversation_id, user.id)
                has_messages = db.execute(
                    "SELECT 1 FROM messages WHERE conversation_id = ? LIMIT 1",
                    (conversation_id,),
                ).fetchone()
                title = conversation["title"] if has_messages else " ".join(payload.content.split())[:60]
                inserted = []
                for role, content in (("user", payload.content), ("assistant", reply)):
                    cursor = db.execute(
                        "INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                        (conversation_id, role, content, timestamp),
                    )
                    inserted.append(
                        {"id": cursor.lastrowid, "role": role, "content": content, "created_at": timestamp}
                    )
                db.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (title, timestamp, conversation_id),
                )
                conversation = owned_conversation(db, conversation_id, user.id)
            return {"conversation": conversation, "messages": inserted}
        finally:
            inflight.discard(conversation_id)

    # --- Streaming SSE Endpoint ---
    @app.post("/api/conversations/{conversation_id}/messages/stream")
    async def send_message_stream(conversation_id: str, payload: SendMessage, user: AuthUser):
        """Streams assistant reply tokens via Server-Sent Events (SSE)."""
        with connect(config.database_path) as db:
            owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                """SELECT role, content FROM (
                       SELECT id, role, content FROM messages
                       WHERE conversation_id = ? ORDER BY id DESC LIMIT 40
                   ) ORDER BY id""",
                (conversation_id,),
            ).fetchall()

        if conversation_id in inflight:
            raise HTTPException(status_code=409, detail="A reply is already being generated.")

        history = [dict(row) for row in rows]
        while history and sum(len(item["content"]) for item in history) > 40_000:
            history = history[2:]

        # Hybrid RAG search
        search_results = await rag.search_relevant_chunks(
            payload.content,
            conversation_id=conversation_id,
            user_id=user.id,
            limit=4,
            history=history,
        )
        context = None
        sources = []
        if search_results:
            context_parts = [
                f"[Document: {hit['source']} | Page: {hit.get('page', 1)} | Score: {hit['score']:.2f}]\n{hit['text']}"
                for hit in search_results
            ]
            context = "\n\n---\n\n".join(context_parts)
            sources = list(dict.fromkeys(hit["source"] for hit in search_results))

        inflight.add(conversation_id)

        async def event_generator() -> AsyncIterator[str]:
            full_reply_parts = []
            try:
                # First yield any referenced sources
                if sources:
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

                # Check if generator supports reply_stream
                if hasattr(ai, "reply_stream"):
                    async for token in ai.reply_stream(
                        [*history, {"role": "user", "content": payload.content}],
                        context=context,
                    ):
                        full_reply_parts.append(token)
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                else:
                    reply = await ai.reply(
                        [*history, {"role": "user", "content": payload.content}],
                        context=context,
                    )
                    full_reply_parts.append(reply)
                    yield f"data: {json.dumps({'type': 'token', 'token': reply})}\n\n"

                final_reply = "".join(full_reply_parts).strip()
                timestamp = now()

                with connect(config.database_path) as db:
                    conversation = owned_conversation(db, conversation_id, user.id)
                    has_messages = db.execute(
                        "SELECT 1 FROM messages WHERE conversation_id = ? LIMIT 1",
                        (conversation_id,),
                    ).fetchone()
                    title = conversation["title"] if has_messages else " ".join(payload.content.split())[:60]
                    inserted = []
                    for role, content in (("user", payload.content), ("assistant", final_reply)):
                        cursor = db.execute(
                            "INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                            (conversation_id, role, content, timestamp),
                        )
                        inserted.append(
                            {"id": cursor.lastrowid, "role": role, "content": content, "created_at": timestamp}
                        )
                    db.execute(
                        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                        (title, timestamp, conversation_id),
                    )
                    updated_conversation = owned_conversation(db, conversation_id, user.id)

                yield f"data: {json.dumps({'type': 'done', 'conversation': updated_conversation, 'messages': inserted})}\n\n"
            except Exception as exc:
                logger.exception("Error during response streaming", exc_info=exc)
                yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
            finally:
                inflight.discard(conversation_id)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
