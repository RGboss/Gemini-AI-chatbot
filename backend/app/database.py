import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path) -> None:
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
