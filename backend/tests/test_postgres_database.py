from pathlib import Path
from unittest.mock import MagicMock
import pytest
from app.database import (
    PostgresConnectionWrapper,
    SmartRow,
    is_postgres_target,
    IntegrityError,
    DatabaseError,
)


def test_is_postgres_target():
    assert is_postgres_target("postgresql://user:pass@localhost:5432/db") is True
    assert is_postgres_target("postgres://user:pass@localhost:5432/db") is True
    assert is_postgres_target(Path("chatbot.db")) is False
    assert is_postgres_target("chatbot.db") is False
    assert is_postgres_target("sqlite:///chatbot.db") is False


def test_smart_row():
    row = SmartRow({"id": 42, "username": "orbit_user"}, ["id", "username"])
    assert row["id"] == 42
    assert row["username"] == "orbit_user"
    assert row[0] == 42
    assert row[1] == "orbit_user"
    assert dict(row) == {"id": 42, "username": "orbit_user"}


def test_postgres_query_translation():
    mock_raw = MagicMock()
    wrapper = PostgresConnectionWrapper(mock_raw)

    translated = wrapper._translate_query("SELECT * FROM users WHERE username = ? AND id = ?")
    assert "%s" in translated
    assert "?" not in translated
    assert "LOWER(username) = LOWER(%s)" in translated


def test_postgres_insert_returning_injection():
    mock_raw = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (101,)
    mock_raw.cursor.return_value = mock_cursor

    wrapper = PostgresConnectionWrapper(mock_raw)
    res = wrapper.execute("INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)", ("alice", "hash", "now"))

    executed_query = mock_cursor.execute.call_args[0][0]
    assert "RETURNING id" in executed_query
    assert "%s" in executed_query
    assert res.lastrowid == 101
