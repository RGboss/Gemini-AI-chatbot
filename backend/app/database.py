from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence, Union

try:
    import psycopg
    from psycopg import errors as pg_errors
except ImportError:
    psycopg = None
    pg_errors = None


class DatabaseError(Exception):
    """Base database exception."""


class IntegrityError(DatabaseError, sqlite3.IntegrityError):
    """Raised on unique constraint or foreign key integrity violation."""


class SmartRow(dict):
    """Dict-like row wrapper that supports integer indexing, column names, and dict(row)."""

    def __init__(self, data: dict[str, Any], column_names: Sequence[str]):
        super().__init__(data)
        self._keys = list(column_names)

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, int):
            return super().__getitem__(self._keys[item])
        return super().__getitem__(item)


class PostgresCursorWrapper:
    def __init__(self, cursor: Any, lastrowid: int | None = None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount

    def fetchone(self) -> SmartRow | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        col_names = [desc[0] for desc in self._cursor.description]
        return SmartRow(dict(zip(col_names, row)), col_names)

    def fetchall(self) -> list[SmartRow]:
        rows = self._cursor.fetchall()
        if not rows:
            return []
        col_names = [desc[0] for desc in self._cursor.description]
        return [SmartRow(dict(zip(col_names, r)), col_names) for r in rows]

    def __iter__(self):
        for row in self.fetchall():
            yield row


class PostgresConnectionWrapper:
    def __init__(self, connection: Any):
        self._conn = connection

    def execute(self, query: str, params: Sequence[Any] | None = None) -> PostgresCursorWrapper:
        translated_query = self._translate_query(query)
        cursor = self._conn.cursor()
        lastrowid = None

        # Check if INSERT without RETURNING into users or messages
        is_insert = translated_query.strip().upper().startswith("INSERT INTO")
        needs_returning = is_insert and "RETURNING" not in translated_query.upper()
        if needs_returning and ("users(" in translated_query.lower() or "messages(" in translated_query.lower()):
            translated_query += " RETURNING id"

        try:
            if params is not None:
                cursor.execute(translated_query, tuple(params))
            else:
                cursor.execute(translated_query)

            if is_insert and "RETURNING id" in translated_query:
                ret = cursor.fetchone()
                if ret:
                    lastrowid = ret[0]
        except Exception as exc:
            if pg_errors and isinstance(exc, (pg_errors.IntegrityError, pg_errors.UniqueViolation)):
                raise IntegrityError(str(exc)) from exc
            raise DatabaseError(str(exc)) from exc

        return PostgresCursorWrapper(cursor, lastrowid=lastrowid)

    def executescript(self, script: str) -> None:
        cursor = self._conn.cursor()
        try:
            cursor.execute(script)
        except Exception as exc:
            if pg_errors and isinstance(exc, (pg_errors.IntegrityError, pg_errors.UniqueViolation)):
                raise IntegrityError(str(exc)) from exc
            raise DatabaseError(str(exc)) from exc

    def _translate_query(self, query: str) -> str:
        # Translate case-insensitive username comparison
        q = re.sub(r"(?i)\bWHERE\s+username\s*=\s*\?", "WHERE LOWER(username) = LOWER(?)", query)
        # Translate ? to %s for PostgreSQL
        return q.replace("?", "%s")

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def is_postgres_target(target: Union[str, Path]) -> bool:
    if isinstance(target, Path):
        return False
    t = str(target).strip().lower()
    return t.startswith("postgresql://") or t.startswith("postgres://")


@contextmanager
def connect(target: Union[str, Path]) -> Iterator[Any]:
    if is_postgres_target(target):
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL requested (via database_url), but 'psycopg' is not installed. "
                "Install with 'pip install \"psycopg[binary]\"'."
            )
        raw_conn = psycopg.connect(str(target), autocommit=False)
        wrapper = PostgresConnectionWrapper(raw_conn)
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            wrapper.rollback()
            raise
        finally:
            wrapper.close()
    else:
        path = Path(target) if isinstance(target, str) else target
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def initialize(target: Union[str, Path]) -> None:
    if is_postgres_target(target):
        with connect(target) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at BIGINT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS conversations (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    system_prompt TEXT DEFAULT '',
                    is_pinned INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS conversations_owner
                    ON conversations(user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id VARCHAR(255) NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role VARCHAR(32) NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    cached_tokens INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS messages_conversation
                    ON messages(conversation_id, id);
                """
            )
    else:
        path = Path(target) if isinstance(target, str) else target
        path.parent.mkdir(parents=True, exist_ok=True)
        with connect(path) as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversations_owner
                    ON conversations(user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conversation
                    ON messages(conversation_id, id);
                """
            )

            # Migration: Ensure token tracking columns exist on messages table
            cursor = db.execute("PRAGMA table_info(messages)")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if "prompt_tokens" not in existing_cols:
                db.execute("ALTER TABLE messages ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
            if "completion_tokens" not in existing_cols:
                db.execute("ALTER TABLE messages ADD COLUMN completion_tokens INTEGER DEFAULT 0")
            if "total_tokens" not in existing_cols:
                db.execute("ALTER TABLE messages ADD COLUMN total_tokens INTEGER DEFAULT 0")
            if "cached_tokens" not in existing_cols:
                db.execute("ALTER TABLE messages ADD COLUMN cached_tokens INTEGER DEFAULT 0")

            # Migration: Ensure system_prompt persona and is_pinned columns exist on conversations table
            cursor_conv = db.execute("PRAGMA table_info(conversations)")
            existing_conv_cols = {row["name"] for row in cursor_conv.fetchall()}
            if "system_prompt" not in existing_conv_cols:
                db.execute("ALTER TABLE conversations ADD COLUMN system_prompt TEXT DEFAULT ''")
            if "is_pinned" not in existing_conv_cols:
                db.execute("ALTER TABLE conversations ADD COLUMN is_pinned INTEGER DEFAULT 0")
