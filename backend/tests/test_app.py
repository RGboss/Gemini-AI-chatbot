import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import connect
from app.main import COOKIE_NAME, create_app


class FakeGemini:
    def __init__(self):
        self.calls = []
        self.failure = None

    async def reply(self, messages):
        self.calls.append(messages)
        if self.failure:
            raise self.failure
        return "Here is a **helpful** reply."

    async def close(self):
        pass


@pytest.fixture
def setup(tmp_path):
    settings = Settings(
        _env_file=None, database_path=tmp_path / "test.db", google_api_key=""
    )
    gemini = FakeGemini()
    with TestClient(create_app(settings, gemini)) as client:
        yield client, settings, gemini


def register(client, username="alice"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "test-password-123"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def new_conversation(client):
    response = client.post("/api/conversations")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client, conversation_id, content="Hello Gemini"):
    return client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": content}
    )


def test_registration_session_and_logout(setup):
    client, settings, _ = setup
    user = register(client, "Alice")
    assert user == {"id": 1, "username": "alice"}
    assert client.get("/api/auth/me").json() == user
    assert client.cookies.get(COOKIE_NAME)
    with connect(settings.database_path) as db:
        session = db.execute("SELECT * FROM sessions").fetchone()
        account = db.execute("SELECT * FROM users").fetchone()
    assert session["token_hash"] != client.cookies.get(COOKIE_NAME)
    assert account["password_hash"].startswith("$argon2")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    with connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_cookie_security_attributes(setup):
    client, _, _ = setup
    response = client.post(
        "/api/auth/register", json={"username": "alice", "password": "test-password-123"}
    )
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api" in cookie


def test_login_and_duplicate_username(setup):
    client, _, _ = setup
    register(client)
    duplicate = client.post(
        "/api/auth/register", json={"username": "ALICE", "password": "test-password-123"}
    )
    assert duplicate.status_code == 409
    client.post("/api/auth/logout")
    for username in ("alice", "missing"):
        response = client.post(
            "/api/auth/login", json={"username": username, "password": "wrong-password"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid username or password."
    assert client.post(
        "/api/auth/login", json={"username": "ALICE", "password": "test-password-123"}
    ).status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "a", "password": "test-password"},
        {"username": "bad name", "password": "test-password"},
        {"username": "alice", "password": "short"},
        {"username": "alice", "password": "a" * 129},
    ],
)
def test_invalid_credentials(setup, payload):
    client, _, _ = setup
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_expired_session(setup):
    client, settings, _ = setup
    register(client)
    with connect(settings.database_path) as db:
        db.execute("UPDATE sessions SET expires_at = ?", (int(time.time()) - 1,))
    assert client.get("/api/auth/me").status_code == 401


def test_routes_require_login(setup):
    client, _, _ = setup
    assert client.get("/api/conversations").status_code == 401
    assert client.post("/api/conversations").status_code == 401
    assert client.get("/api/conversations/missing").status_code == 401
    assert client.delete("/api/conversations/missing").status_code == 401
    assert send(client, "missing").status_code == 401


def test_chat_history_title_and_deletion(setup):
    client, settings, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    result = send(client, conversation_id, "  Explain Python  ")
    assert result.status_code == 200, result.text
    assert result.json()["conversation"]["title"] == "Explain Python"
    assert [m["role"] for m in result.json()["messages"]] == ["user", "assistant"]
    assert gemini.calls[0] == [{"role": "user", "content": "Explain Python"}]
    assert send(client, conversation_id, "Give an example").status_code == 200
    assert [m["role"] for m in gemini.calls[1]] == ["user", "assistant", "user"]
    history = client.get(f"/api/conversations/{conversation_id}").json()
    assert len(history["messages"]) == 4
    assert history["title"] == "Explain Python"
    assert client.get("/api/conversations").json()[0]["id"] == conversation_id
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    with connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_user_data_isolation(setup):
    client, _, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    send(client, conversation_id)
    client.post("/api/auth/logout")
    register(client, "bob")
    assert client.get("/api/conversations").json() == []
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 404
    assert send(client, conversation_id).status_code == 404
    assert len(gemini.calls) == 1


@pytest.mark.parametrize("content", ["", "   ", "a" * 8001])
def test_invalid_message(setup, content):
    client, _, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    assert send(client, conversation_id, content).status_code == 422
    assert not gemini.calls


def test_api_failure_does_not_save_partial_turn_and_retry_works(setup):
    client, _, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    gemini.failure = HTTPException(status_code=429, detail="Quota exceeded")
    assert send(client, conversation_id).status_code == 429
    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []
    gemini.failure = None
    assert send(client, conversation_id).status_code == 200


def test_missing_google_key_returns_actionable_error(tmp_path):
    settings = Settings(_env_file=None, google_api_key="", database_path=tmp_path / "test.db")
    with TestClient(create_app(settings)) as client:
        register(client)
        conversation_id = new_conversation(client)
        assert client.get("/api/health").json()["ai_configured"] is False
        response = send(client, conversation_id)
        assert response.status_code == 503
        assert "GOOGLE_API_KEY" in response.json()["detail"]
        assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []


def test_origin_check(setup):
    client, _, _ = setup
    assert client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "test-password"},
        headers={"Origin": "https://untrusted.example"},
    ).status_code == 403
    response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "test-password"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_history_survives_app_restart(setup):
    client, settings, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    send(client, conversation_id)
    token = client.cookies.get(COOKIE_NAME)
    with TestClient(create_app(settings, gemini)) as restarted:
        restarted.cookies.set(COOKIE_NAME, token, path="/api")
        assert restarted.get("/api/auth/me").status_code == 200
        assert len(restarted.get(f"/api/conversations/{conversation_id}").json()["messages"]) == 2


def test_bounded_history_preserves_whole_turns(setup):
    client, settings, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    with connect(settings.database_path) as db:
        for index in range(50):
            db.execute(
                "INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, "user" if index % 2 == 0 else "assistant", f"{index}:" + "a" * 3000, "now"),
            )
    assert send(client, conversation_id).status_code == 200
    history = gemini.calls[0][:-1]
    assert len(history) % 2 == 0
    assert len(history) <= 40
    assert sum(len(m["content"]) for m in history) <= 40000
    assert history[0]["role"] == "user"
    assert history[-1]["content"].startswith("49:")


def test_concurrent_send_and_delete_are_rejected(setup):
    client, _, gemini = setup
    register(client)
    conversation_id = new_conversation(client)
    entered, release = threading.Event(), threading.Event()

    async def delayed_reply(messages):
        entered.set()
        await asyncio.to_thread(release.wait, 10)
        return "Finished"

    gemini.reply = delayed_reply
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(send, client, conversation_id)
        try:
            assert entered.wait(5)
            assert send(client, conversation_id).status_code == 409
            assert client.delete(f"/api/conversations/{conversation_id}").status_code == 409
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert len(client.get(f"/api/conversations/{conversation_id}").json()["messages"]) == 2
