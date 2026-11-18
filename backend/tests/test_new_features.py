import io
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rag import RAGService


class FakeEmbeddingClient:
    class Models:
        async def embed_content(self, model, contents, **kwargs):
            class Emb:
                values = [0.05] * 3072

            class Res:
                embeddings = [Emb() for _ in (contents if isinstance(contents, list) else [contents])]

            return Res()

        async def generate_content(self, model, contents, **kwargs):
            class GenRes:
                text = "## Executive Summary\nThis document describes system architecture and specifications."

            return GenRes()

    def __init__(self):
        self.aio = self
        self.models = self.Models()


class FakeChatReply:
    def __init__(self):
        self.calls = []

    async def reply(self, messages, context=None):
        self.calls.append({"messages": messages, "context": context})
        return "I am Orbit, and this is a verified reply."

    async def close(self):
        pass


@pytest.fixture
def feature_app(tmp_path):
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "test_features.db",
        google_api_key="test_key",
        gemini_orchestrator_key="test_key",
        gemini_worker_key="test_key",
    )
    fake_client = FakeEmbeddingClient()
    rag_service = RAGService(settings, client=fake_client)
    fake_ai = FakeChatReply()
    app = create_app(settings=settings, generator=fake_ai, rag_service=rag_service)
    with TestClient(app) as client:
        yield client, rag_service, fake_ai


def register_and_login(client, username="testuser"):
    client.post("/api/auth/register", json={"username": username, "password": "password-12345"})
    res = client.post("/api/auth/login", json={"username": username, "password": "password-12345"})
    assert res.status_code == 200
    return res.json()


def create_conversation(client):
    res = client.post("/api/conversations")
    assert res.status_code == 201
    return res.json()["id"]


def test_export_conversation_markdown_and_json(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "alice")
    conv_id = create_conversation(client)

    # Post a message to generate history
    msg_res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Explain quantum computing in simple terms."},
    )
    assert msg_res.status_code == 200

    # Test Markdown export
    md_res = client.get(f"/api/conversations/{conv_id}/export?format=markdown")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers["content-type"]
    assert "attachment;" in md_res.headers["content-disposition"]
    assert ".md" in md_res.headers["content-disposition"]
    assert "Explain quantum computing" in md_res.text
    assert "Orbit" in md_res.text

    # Test JSON export
    json_res = client.get(f"/api/conversations/{conv_id}/export?format=json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    assert ".json" in json_res.headers["content-disposition"]
    data = json_res.json()
    assert "conversation" in data
    assert "messages" in data
    assert len(data["messages"]) >= 2
    assert data["messages"][0]["content"] == "Explain quantum computing in simple terms."


def test_document_deletion_and_summarization(feature_app):
    client, rag_service, _ = feature_app
    register_and_login(client, "bob")
    conv_id = create_conversation(client)

    # 1. Ingest a document
    file_content = b"Orbit Architecture: high availability multi-region deployment with zero downtime."
    files = {"file": ("orbit_arch.txt", io.BytesIO(file_content), "text/plain")}
    upload_res = client.post(f"/api/conversations/{conv_id}/upload", files=files)
    assert upload_res.status_code == 200
    assert upload_res.json()["filename"] == "orbit_arch.txt"

    # Confirm it appears in document list
    docs_res = client.get(f"/api/conversations/{conv_id}/documents")
    assert "orbit_arch.txt" in docs_res.json()["documents"]

    # 2. Test Summarization
    summary_res = client.post(f"/api/conversations/{conv_id}/documents/orbit_arch.txt/summarize")
    assert summary_res.status_code == 200
    assert summary_res.json()["status"] == "success"
    assert "Executive Summary" in summary_res.json()["summary"]

    # 3. Test Deletion
    del_res = client.delete(f"/api/conversations/{conv_id}/documents/orbit_arch.txt")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Confirm it is no longer listed in active session documents
    docs_after = client.get(f"/api/conversations/{conv_id}/documents")
    assert "orbit_arch.txt" not in docs_after.json()["documents"]
