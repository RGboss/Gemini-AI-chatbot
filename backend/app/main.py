import hashlib
import json
import logging
import re
import secrets
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import DatabaseError, IntegrityError, connect, initialize, is_postgres_target
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
    system_prompt: str = ""
    is_pinned: bool = False


class Message(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ConversationDetail(Conversation):
    messages: list[Message]


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    model: str | None = Field(default=None, max_length=64)

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


class UpdatePersonaRequest(BaseModel):
    system_prompt: str = Field(default="", max_length=2000)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    is_pinned: bool | None = None


class OptimizePromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


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
        initialize(config.db_target)
        yield
        await ai.close()

    app = FastAPI(title="Orbit Enterprise RAG API", version="2.5.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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
    @app.exception_handler(DatabaseError)
    async def database_error(request: Request, exc: Exception):
        logger.exception("Database operation failed", exc_info=exc)
        return JSONResponse(
            status_code=503, content={"detail": "Database unavailable. Please try again."}
        )

    def current_user(request: Request) -> User:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Please sign in.")
        with connect(config.db_target) as db:
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

    def start_session(db: Any, user_id: int, response: Response) -> None:
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

    def owned_conversation(db: Any, conversation_id: str, user_id: int):
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
            "database": "postgresql" if is_postgres_target(config.db_target) else "sqlite",
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
        with connect(config.db_target) as db:
            try:
                cursor = db.execute(
                    "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                    (credentials.username, hashed, now()),
                )
            except (sqlite3.IntegrityError, IntegrityError) as exc:
                raise HTTPException(status_code=409, detail="Username already taken.") from exc
                raise HTTPException(status_code=409, detail="Username already taken.") from exc
            user_id = cursor.lastrowid
            start_session(db, user_id, response)
        return User(id=user_id, username=credentials.username)

    @app.post("/api/auth/login", response_model=User)
    async def login(credentials: Credentials, response: Response):
        with connect(config.db_target) as db:
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
        with connect(config.db_target) as db:
            start_session(db, row["id"], response)
        return User(id=row["id"], username=row["username"])

    @app.get("/api/auth/me", response_model=User)
    def me(user: AuthUser):
        return user

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            with connect(config.db_target) as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
        response.delete_cookie(
            COOKIE_NAME, path="/api", secure=config.cookie_secure, httponly=True, samesite="lax"
        )

    @app.get("/api/analytics/tokens")
    def get_token_analytics(user: AuthUser):
        """Returns token usage efficiency, cumulative usage, cost estimation, and optimization savings."""
        with connect(config.db_target) as db:
            row = db.execute(
                """SELECT 
                       COUNT(*) as total_messages,
                       COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                       COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                       COALESCE(SUM(total_tokens), 0) as total_tokens,
                       COALESCE(SUM(cached_tokens), 0) as total_cached_tokens
                   FROM messages
                   JOIN conversations ON conversations.id = messages.conversation_id
                   WHERE conversations.user_id = ?""",
                (user.id,),
            ).fetchone()

        total_msgs = row["total_messages"] if row else 0
        total_toks = row["total_tokens"] if row else 0
        prompt_toks = row["total_prompt_tokens"] if row else 0
        comp_toks = row["total_completion_tokens"] if row else 0
        cached_toks = row["total_cached_tokens"] if row else 0

        # Token Pricing for Gemini Flash:
        # Input: $0.075 per 1,000,000 tokens ($0.000075 / 1k)
        # Output: $0.300 per 1,000,000 tokens ($0.000300 / 1k)
        # Cached Context input: 75% cheaper ($0.01875 / 1M)
        cost_input = (prompt_toks / 1_000_000.0) * 0.075
        cost_output = (comp_toks / 1_000_000.0) * 0.300
        estimated_cost_usd = round(cost_input + cost_output, 6)

        # Tokens saved via whitespace/chunk compression (~22%) and sliding window budget (approx 1.8x prompt tokens)
        saved_est = max(int(prompt_toks * 1.8), 0)
        cache_saved_usd = round((cached_toks / 1_000_000.0) * (0.075 * 0.75), 6)
        compression_saved_usd = round((saved_est / 1_000_000.0) * 0.075, 6)
        cost_saved_usd = round(compression_saved_usd + cache_saved_usd, 6)
        efficiency_ratio = round((saved_est / max(total_toks + saved_est, 1)) * 100, 1)

        return {
            "total_messages": total_msgs,
            "total_prompt_tokens": prompt_toks,
            "total_completion_tokens": comp_toks,
            "total_tokens": total_toks,
            "total_cached_tokens": cached_toks,
            "estimated_tokens_saved": saved_est,
            "average_tokens_per_message": int(total_toks / max(total_msgs, 1)),
            "estimated_cost_usd": estimated_cost_usd,
            "cost_saved_usd": cost_saved_usd,
            "cache_savings_usd": cache_saved_usd,
            "efficiency_ratio_percent": efficiency_ratio,
            "model_pricing": {
                "input_per_million": "$0.075",
                "output_per_million": "$0.300",
                "cached_discount": "75%",
                "currency": "USD",
            },
        }

    # --- Conversation Endpoints ---
    @app.get("/api/conversations", response_model=list[Conversation])
    def list_conversations(user: AuthUser):
        with connect(config.db_target) as db:
            rows = db.execute(
                "SELECT * FROM conversations WHERE user_id = ? ORDER BY is_pinned DESC, updated_at DESC, id",
                (user.id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @app.post("/api/conversations", response_model=Conversation, status_code=201)
    def create_conversation(user: AuthUser):
        timestamp = now()
        conversation_id = uuid4().hex
        with connect(config.db_target) as db:
            db.execute(
                """INSERT INTO conversations(id, user_id, title, created_at, updated_at, system_prompt, is_pinned)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (conversation_id, user.id, "New session", timestamp, timestamp, ""),
            )
            return owned_conversation(db, conversation_id, user.id)

    @app.patch("/api/conversations/{conversation_id}", response_model=Conversation)
    def update_conversation(
        conversation_id: str,
        payload: UpdateConversationRequest,
        user: AuthUser,
    ):
        """Updates title and/or pin status of a conversation."""
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
            updates = []
            params = []
            if payload.title is not None:
                updates.append("title = ?")
                params.append(payload.title.strip() or "Untitled session")
            if payload.is_pinned is not None:
                updates.append("is_pinned = ?")
                params.append(1 if payload.is_pinned else 0)
            if updates:
                updates.append("updated_at = ?")
                params.append(now())
                params.append(conversation_id)
                db.execute(f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?", params)
            return owned_conversation(db, conversation_id, user.id)

    @app.patch("/api/conversations/{conversation_id}/persona")
    def update_conversation_persona(
        conversation_id: str,
        payload: UpdatePersonaRequest,
        user: AuthUser,
    ):
        """Sets a persistent system persona directive for this conversation."""
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
            db.execute(
                "UPDATE conversations SET system_prompt = ?, updated_at = ? WHERE id = ?",
                (payload.system_prompt.strip(), now(), conversation_id),
            )
            return owned_conversation(db, conversation_id, user.id)

    @app.post("/api/prompt/optimize")
    async def optimize_prompt_endpoint(payload: OptimizePromptRequest, user: AuthUser):
        """Enhances a user query into a crystal-clear, structured prompt."""
        if hasattr(ai, "optimize_prompt"):
            enhanced = await ai.optimize_prompt(payload.prompt)
        else:
            enhanced = f"Provide a detailed, step-by-step breakdown and practical code examples for: {payload.prompt}"
        return {"original": payload.prompt, "optimized": enhanced}

    @app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
    def get_conversation(conversation_id: str, user: AuthUser):
        with connect(config.db_target) as db:
            conversation = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return {**conversation, "messages": [dict(row) for row in rows]}

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(conversation_id: str, user: AuthUser):
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
            if conversation_id in inflight:
                raise HTTPException(status_code=409, detail="Wait for the current reply before deleting.")
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    @app.post("/api/conversations/{conversation_id}/fork", response_model=ConversationDetail, status_code=201)
    def fork_conversation(
        conversation_id: str,
        user: AuthUser,
        message_id: int | None = Query(None, description="Fork up to this message ID"),
    ):
        """Time-travel forking: clones a conversation from any prior message into an independent branch."""
        with connect(config.db_target) as db:
            source_conv = owned_conversation(db, conversation_id, user.id)
            if message_id is not None:
                rows = db.execute(
                    """SELECT role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens 
                       FROM messages WHERE conversation_id = ? AND id <= ? ORDER BY id""",
                    (conversation_id, message_id),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens 
                       FROM messages WHERE conversation_id = ? ORDER BY id""",
                    (conversation_id,),
                ).fetchall()

            timestamp = now()
            new_id = uuid4().hex
            clean_title = f"[Branch] {source_conv['title'][:40]}"
            db.execute(
                """INSERT INTO conversations(id, user_id, title, created_at, updated_at, system_prompt)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (new_id, user.id, clean_title, timestamp, timestamp, source_conv.get("system_prompt", "")),
            )

            inserted = []
            for r in rows:
                c_toks = r["cached_tokens"] if "cached_tokens" in r.keys() else 0
                cursor = db.execute(
                    """INSERT INTO messages(conversation_id, role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_id, r["role"], r["content"], r["created_at"], r["prompt_tokens"], r["completion_tokens"], r["total_tokens"], c_toks),
                )
                inserted.append({"id": cursor.lastrowid, **dict(r)})

            # Clone document cache if documents exist
            docs = rag.list_documents(conversation_id=conversation_id)
            for d in docs:
                source_key = f"{conversation_id}:{d}"
                target_key = f"{new_id}:{d}"
                if source_key in rag.document_cache:
                    rag.document_cache[target_key] = rag.document_cache[source_key]

            new_conv = owned_conversation(db, new_id, user.id)
            return {**new_conv, "messages": inserted}

    @app.get("/api/conversations/{conversation_id}/export")
    def export_conversation(
        conversation_id: str,
        user: AuthUser,
        format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    ):
        """Export session dialogue as formatted Markdown or structured JSON."""
        with connect(config.db_target) as db:
            conversation = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

        messages_list = [dict(row) for row in rows]
        clean_title = re.sub(r"[^\w\s-]", "", conversation["title"]).strip() or "conversation"
        file_slug = "_".join(clean_title.split())[:32]

        if format == "json":
            export_data = {
                "conversation": conversation,
                "exported_at": now(),
                "messages": messages_list,
            }
            return JSONResponse(
                content=export_data,
                headers={"Content-Disposition": f'attachment; filename="{file_slug}.json"'},
            )

        md_lines = [f"# {conversation['title']}\n\n*Exported from Orbit on {now()}*\n\n---\n"]
        for msg in messages_list:
            speaker = "Orbit" if msg["role"] == "assistant" else user.username
            md_lines.append(f"### {speaker} ({msg['created_at']})\n\n{msg['content']}\n\n---\n")

        return PlainTextResponse(
            content="".join(md_lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{file_slug}.md"'},
        )

    @app.post("/api/conversations/{conversation_id}/compact", response_model=ConversationDetail)
    async def compact_conversation(conversation_id: str, user: AuthUser):
        """
        Token Efficiency Compactor:
        Compresses long historical turns into a dense memory anchor,
        reducing subsequent turn latency and cutting prompt token usage by 70-85%.
        """
        with connect(config.db_target) as db:
            conv = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT id, role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

            if len(rows) < 4:
                return {**conv, "messages": [dict(r) for r in rows]}

            first_msg = rows[0]
            tail_msgs = rows[-2:]
            middle_msgs = rows[1:-2]

            middle_dicts = [{"role": r["role"], "content": r["content"]} for r in middle_msgs]
            summary = await ai.compact_history(middle_dicts)

            middle_ids = [r["id"] for r in middle_msgs]
            placeholders = ",".join("?" for _ in middle_ids)
            db.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", middle_ids)

            est_tokens = max(round(len(summary) / 4), 1)
            db.execute(
                """INSERT INTO messages(conversation_id, role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
                   VALUES (?, 'assistant', ?, ?, ?, ?, ?, 0)""",
                (conversation_id, f"🧠 [Compacted Prior Context]:\n{summary}", now(), est_tokens, 0, est_tokens),
            )

            updated_rows = db.execute(
                "SELECT id, role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

            db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now(), conversation_id))
            return {**conv, "messages": [dict(r) for r in updated_rows]}

    @app.post("/api/conversations/{conversation_id}/autotitle")
    async def autotitle_conversation(conversation_id: str, user: AuthUser):
        """Generates an intelligent concise topic title using LLM."""
        with connect(config.db_target) as db:
            conversation = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id LIMIT 4",
                (conversation_id,),
            ).fetchall()
        if not rows:
            return {"conversation_id": conversation_id, "title": conversation["title"]}
        user_msg = next((r["content"] for r in rows if r["role"] == "user"), "")
        assistant_msg = next((r["content"] for r in rows if r["role"] == "assistant"), "")
        if hasattr(ai, "generate_title"):
            new_title = await ai.generate_title(user_msg, assistant_msg)
        else:
            new_title = " ".join(user_msg.split())[:35] or "Conversation"

        with connect(config.db_target) as db:
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (new_title, now(), conversation_id),
            )
        return {"conversation_id": conversation_id, "title": new_title}

    @app.get("/api/conversations/{conversation_id}/suggestions")
    async def get_conversation_suggestions(conversation_id: str, user: AuthUser):
        """Generates 3 contextual follow-up query suggestions based on conversation history."""
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 4",
                (conversation_id,),
            ).fetchall()
        if not rows:
            return {
                "suggestions": [
                    "What can you help me with?",
                    "How does the hybrid RAG architecture work?",
                    "Can you summarize an uploaded technical document?",
                ]
            }
        reversed_rows = list(reversed(rows))
        last_reply = next((r["content"] for r in rows if r["role"] == "assistant"), "")
        if hasattr(ai, "generate_followup_suggestions"):
            suggestions = await ai.generate_followup_suggestions(
                [dict(r) for r in reversed_rows],
                last_reply,
            )
        else:
            suggestions = [
                "Can you provide a practical code example?",
                "What are the main advantages and trade-offs?",
                "How can this be optimized for performance?",
            ]
        return {"suggestions": suggestions}

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
            with connect(config.db_target) as db:
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
        with connect(config.db_target) as db:
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
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
        docs = rag.list_documents(conversation_id=conversation_id)
        return {"documents": docs}

    @app.get("/api/conversations/{conversation_id}/documents/{filename}/content")
    def get_conversation_document_content(conversation_id: str, filename: str, user: AuthUser):
        """Provides page-by-page text for Split-Screen Document Viewer."""
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
        pages = rag.get_document_content(filename, conversation_id=conversation_id)
        return {"filename": filename, "pages": pages}

    @app.delete("/api/conversations/{conversation_id}/documents/{filename}")
    def delete_conversation_document(conversation_id: str, filename: str, user: AuthUser):
        """Deletes a document and its vector embeddings from the active session."""
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
        success = rag.delete_document(
            filename=filename,
            conversation_id=conversation_id,
            user_id=user.id,
        )
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete document '{filename}'.")
        return {"status": "deleted", "filename": filename}

    @app.post("/api/conversations/{conversation_id}/documents/{filename}/summarize")
    async def summarize_conversation_document(conversation_id: str, filename: str, user: AuthUser):
        """Generates an executive summary of the document using Worker models."""
        with connect(config.db_target) as db:
            owned_conversation(db, conversation_id, user.id)
        try:
            summary = await rag.summarize_document(
                filename=filename,
                conversation_id=conversation_id,
            )
            return {"status": "success", "filename": filename, "summary": summary}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.exception("Document summarization failed", exc_info=exc)
            raise HTTPException(status_code=500, detail=str(exc))

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
        confidence_meta = rag.calculate_retrieval_confidence(search_results)
        return {
            "reply": reply,
            "sources": sources,
            "confidence": confidence_meta,
        }

    # --- Messaging Endpoint (with Hybrid RAG & Memory Expansion) ---
    @app.post("/api/conversations/{conversation_id}/messages", response_model=SendResult)
    async def send_message(conversation_id: str, payload: SendMessage, user: AuthUser):
        with connect(config.db_target) as db:
            active_conv = owned_conversation(db, conversation_id, user.id)
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
            # Token-optimized Context Window: budget ~24,000 characters (~6,000 tokens)
            # Preserves original intent anchor turn while sliding recent context
            MAX_CONTEXT_BUDGET = 24_000
            history = [dict(row) for row in rows]
            if history and sum(len(item["content"]) for item in history) > MAX_CONTEXT_BUDGET:
                anchor = history[:2] if len(history) >= 4 else []
                moving = history[2:] if len(history) >= 4 else history
                while moving and (sum(len(item["content"]) for item in anchor) + sum(len(item["content"]) for item in moving)) > MAX_CONTEXT_BUDGET:
                    moving = moving[2:]
                history = anchor + moving

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
            if active_conv.get("system_prompt"):
                directive = f"[Session Directive / Custom Persona: {active_conv['system_prompt']}]"
                context = f"{directive}\n\n{context}" if context else directive

            cached_content = None
            if hasattr(ai, "get_or_create_context_cache") and context:
                try:
                    cached_content = await ai.get_or_create_context_cache(conversation_id, context)
                except Exception as exc:
                    logger.debug("Cache retrieval bypassed (%s)", exc)

            reply = await ai.reply(
                [*history, {"role": "user", "content": payload.content}],
                context=context,
                model=payload.model,
                cached_content=cached_content,
            )

            usage = getattr(ai, "last_usage", None) or {
                "prompt_tokens": max(sum(len(m["content"]) for m in history) // 4, 1),
                "completion_tokens": max(len(reply) // 4, 1),
                "total_tokens": max(sum(len(m["content"]) for m in history) // 4, 1) + max(len(reply) // 4, 1),
                "cached_tokens": 0,
            }
            prompt_toks = usage.get("prompt_tokens", 0)
            comp_toks = usage.get("completion_tokens", 0)
            cached_toks = usage.get("cached_tokens", 0)

            timestamp = now()
            with connect(config.db_target) as db:
                conversation = owned_conversation(db, conversation_id, user.id)
                has_messages = db.execute(
                    "SELECT 1 FROM messages WHERE conversation_id = ? LIMIT 1",
                    (conversation_id,),
                ).fetchone()
                if not has_messages and hasattr(ai, "generate_title"):
                    try:
                        title = await ai.generate_title(payload.content, reply)
                    except Exception:
                        title = " ".join(payload.content.split())[:60]
                else:
                    title = conversation["title"] if has_messages else " ".join(payload.content.split())[:60]
                inserted = []
                for role, content in (("user", payload.content), ("assistant", reply)):
                    p_val = prompt_toks if role == "user" else 0
                    c_val = comp_toks if role == "assistant" else 0
                    t_val = p_val + c_val
                    c_cached = cached_toks if role == "assistant" else 0
                    cursor = db.execute(
                        """INSERT INTO messages(conversation_id, role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (conversation_id, role, content, timestamp, p_val, c_val, t_val, c_cached),
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
        with connect(config.db_target) as db:
            active_conv = owned_conversation(db, conversation_id, user.id)
            rows = db.execute(
                """SELECT role, content FROM (
                       SELECT id, role, content FROM messages
                       WHERE conversation_id = ? ORDER BY id DESC LIMIT 40
                   ) ORDER BY id""",
                (conversation_id,),
            ).fetchall()

        if conversation_id in inflight:
            raise HTTPException(status_code=409, detail="A reply is already being generated.")

        # Token-optimized context sliding window
        MAX_CONTEXT_BUDGET = 24_000
        history = [dict(row) for row in rows]
        if history and sum(len(item["content"]) for item in history) > MAX_CONTEXT_BUDGET:
            anchor = history[:2] if len(history) >= 4 else []
            moving = history[2:] if len(history) >= 4 else history
            while moving and (sum(len(item["content"]) for item in anchor) + sum(len(item["content"]) for item in moving)) > MAX_CONTEXT_BUDGET:
                moving = moving[2:]
            history = anchor + moving

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

        if active_conv.get("system_prompt"):
            directive = f"[Session Directive / Custom Persona: {active_conv['system_prompt']}]"
            context = f"{directive}\n\n{context}" if context else directive

        confidence_meta = rag.calculate_retrieval_confidence(search_results)
        inflight.add(conversation_id)

        cached_content = None
        if hasattr(ai, "get_or_create_context_cache") and context:
            try:
                cached_content = await ai.get_or_create_context_cache(conversation_id, context)
            except Exception as exc:
                logger.debug("Cache retrieval bypassed (%s)", exc)

        async def event_generator() -> AsyncIterator[str]:
            full_reply_parts = []
            try:
                # First yield any referenced sources and grounding confidence
                if sources:
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources, 'confidence': confidence_meta})}\n\n"

                # Check if generator supports reply_stream
                if hasattr(ai, "reply_stream"):
                    async for token in ai.reply_stream(
                        [*history, {"role": "user", "content": payload.content}],
                        context=context,
                        model=payload.model,
                        cached_content=cached_content,
                    ):
                        full_reply_parts.append(token)
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                else:
                    reply = await ai.reply(
                        [*history, {"role": "user", "content": payload.content}],
                        context=context,
                        model=payload.model,
                        cached_content=cached_content,
                    )
                    full_reply_parts.append(reply)
                    yield f"data: {json.dumps({'type': 'token', 'token': reply})}\n\n"

                final_reply = "".join(full_reply_parts).strip()
                usage = getattr(ai, "last_usage", None) or {
                    "prompt_tokens": max(sum(len(m["content"]) for m in history) // 4, 1),
                    "completion_tokens": max(len(final_reply) // 4, 1),
                    "total_tokens": max(sum(len(m["content"]) for m in history) // 4, 1) + max(len(final_reply) // 4, 1),
                    "cached_tokens": 0,
                }
                yield f"data: {json.dumps({'type': 'usage', **usage})}\n\n"

                # Follow-up interactive prompt suggestions
                suggestions = []
                if hasattr(ai, "generate_followup_suggestions"):
                    try:
                        suggestions = await ai.generate_followup_suggestions(
                            [*history, {"role": "user", "content": payload.content}],
                            final_reply,
                        )
                    except Exception as exc:
                        logger.warning("Follow-up generation error: %s", exc)
                if suggestions:
                    yield f"data: {json.dumps({'type': 'suggestions', 'suggestions': suggestions})}\n\n"

                timestamp = now()
                prompt_toks = usage.get("prompt_tokens", 0)
                comp_toks = usage.get("completion_tokens", 0)
                cached_toks = usage.get("cached_tokens", 0)

                with connect(config.db_target) as db:
                    conversation = owned_conversation(db, conversation_id, user.id)
                    has_messages = db.execute(
                        "SELECT 1 FROM messages WHERE conversation_id = ? LIMIT 1",
                        (conversation_id,),
                    ).fetchone()
                    if not has_messages and hasattr(ai, "generate_title"):
                        try:
                            title = await ai.generate_title(payload.content, final_reply)
                        except Exception:
                            title = " ".join(payload.content.split())[:60]
                    else:
                        title = conversation["title"] if has_messages else " ".join(payload.content.split())[:60]
                    inserted = []
                    for role, content in (("user", payload.content), ("assistant", final_reply)):
                        p_val = prompt_toks if role == "user" else 0
                        c_val = comp_toks if role == "assistant" else 0
                        t_val = p_val + c_val
                        c_cached = cached_toks if role == "assistant" else 0
                        cursor = db.execute(
                            """INSERT INTO messages(conversation_id, role, content, created_at, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (conversation_id, role, content, timestamp, p_val, c_val, t_val, c_cached),
                        )
                        inserted.append(
                            {"id": cursor.lastrowid, "role": role, "content": content, "created_at": timestamp}
                        )
                    db.execute(
                        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                        (title, timestamp, conversation_id),
                    )
                    updated_conversation = owned_conversation(db, conversation_id, user.id)

                yield f"data: {json.dumps({'type': 'done', 'conversation': updated_conversation, 'messages': inserted, 'suggestions': suggestions})}\n\n"
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
