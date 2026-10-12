import hashlib
import logging
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import connect, initialize
from .gemini import GeminiService, ReplyGenerator


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


def create_app(
    settings: Settings | None = None, generator: ReplyGenerator | None = None
) -> FastAPI:
    config = settings or Settings()
    ai = generator or GeminiService(config)
    inflight: set[str] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize(config.database_path)
        yield
        await ai.close()

    app = FastAPI(title="Gemini Chat API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
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

    @app.get("/api/health")
    def health():
        configured = ai.client is not None if isinstance(ai, GeminiService) else True
        return {"status": "ok", "model": config.gemini_model, "ai_configured": configured}

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
            # Run a hash even for unknown accounts to avoid a fast username probe.
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
                (conversation_id, user.id, "New conversation", timestamp, timestamp),
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
            # Trim whole turns so Gemini always receives a user-led history.
            while history and sum(len(item["content"]) for item in history) > 40_000:
                history = history[2:]
            reply = await ai.reply([*history, {"role": "user", "content": payload.content}])
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

    return app


app = create_app()
