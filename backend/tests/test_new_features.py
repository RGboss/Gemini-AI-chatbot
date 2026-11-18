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

    async def reply(self, messages, context=None, **kwargs):
        self.calls.append({"messages": messages, "context": context, **kwargs})
        return "I am Orbit, and this is a verified reply."

    async def generate_title(self, prompt: str, reply: str) -> str:
        return "RAG Architecture Analysis"

    async def generate_followup_suggestions(self, messages: list, last_reply: str) -> list[str]:
        return [
            "How does Qdrant handle high vector dimensions?",
            "What is the cost saving of chunk compression?",
            "Can we stream tokens directly to the frontend?",
        ]

    async def optimize_prompt(self, user_prompt: str) -> str:
        return f"Architectural breakdown and design pattern for: {user_prompt}"

    async def compact_history(self, messages_to_compress: list) -> str:
        return "User and assistant designed high-performance RAG pipeline and hybrid search vectors."

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


def test_token_tracking_and_analytics(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "charlie")
    conv_id = create_conversation(client)

    # Send a message to populate tokens
    res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "What is the token efficiency of RAG systems?"},
    )
    assert res.status_code == 200

    # Query token analytics endpoint
    analytics = client.get("/api/analytics/tokens")
    assert analytics.status_code == 200
    data = analytics.json()
    assert data["total_messages"] >= 2
    assert data["total_tokens"] > 0
    assert data["total_prompt_tokens"] > 0
    assert data["total_completion_tokens"] > 0
    assert "estimated_tokens_saved" in data
    assert "average_tokens_per_message" in data
    assert "estimated_cost_usd" in data
    assert "cost_saved_usd" in data
    assert "efficiency_ratio_percent" in data
    assert data["model_pricing"]["currency"] == "USD"


def test_autotitle_and_followup_suggestions(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "dan")
    conv_id = create_conversation(client)

    # 1. Send first message (should auto-title using generate_title)
    res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Can you explain vector search and embeddings in Orbit?"},
    )
    assert res.status_code == 200
    conv_data = res.json()["conversation"]
    assert conv_data["title"] == "RAG Architecture Analysis"

    # 2. Test explicit autotitle endpoint
    autotitle_res = client.post(f"/api/conversations/{conv_id}/autotitle")
    assert autotitle_res.status_code == 200
    assert autotitle_res.json()["title"] == "RAG Architecture Analysis"

    # 3. Test suggestions endpoint
    sugg_res = client.get(f"/api/conversations/{conv_id}/suggestions")
    assert sugg_res.status_code == 200
    suggestions = sugg_res.json()["suggestions"]
    assert len(suggestions) == 3
    assert "How does Qdrant handle high vector dimensions?" in suggestions


def test_session_persona_custom_instructions(feature_app):
    client, _, fake_ai = feature_app
    register_and_login(client, "eve")
    conv_id = create_conversation(client)

    # 1. Update session persona
    persona_prompt = "Adopt senior security auditor persona. Highlight vulnerabilities."
    res = client.patch(
        f"/api/conversations/{conv_id}/persona",
        json={"system_prompt": persona_prompt},
    )
    assert res.status_code == 200
    assert res.json()["system_prompt"] == persona_prompt

    # 2. Send message and verify directive injection in context
    msg_res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Check this endpoint logic."},
    )
    assert msg_res.status_code == 200
    # Last call to reply should contain the custom persona directive
    last_context = fake_ai.calls[-1]["context"]
    assert "Session Directive / Custom Persona" in last_context
    assert persona_prompt in last_context


def test_ai_prompt_optimizer(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "frank")

    res = client.post(
        "/api/prompt/optimize",
        json={"prompt": "build auth with jwt"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["original"] == "build auth with jwt"
    assert "Architectural breakdown" in data["optimized"]


def test_conversation_forking(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "grace")
    conv_id = create_conversation(client)

    # 1. Populate conversation with 2 messages
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Turn 1: Initial query."},
    )
    res2 = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Turn 2: Follow-up query."},
    )
    first_assistant_id = res2.json()["messages"][0]["id"]

    # 2. Fork the conversation
    fork_res = client.post(f"/api/conversations/{conv_id}/fork")
    assert fork_res.status_code == 201
    forked_data = fork_res.json()
    assert forked_data["id"] != conv_id
    assert "[Branch]" in forked_data["title"]
    assert len(forked_data["messages"]) == 4

    # 3. Test partial forking with message_id
    fork_partial_res = client.post(f"/api/conversations/{conv_id}/fork?message_id={first_assistant_id}")
    assert fork_partial_res.status_code == 201
    partial_data = fork_partial_res.json()
    assert len(partial_data["messages"]) <= 3


def test_context_cache_analytics_and_savings(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "heidi")
    conv_id = create_conversation(client)

    # Send message with dynamic model selection
    res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Testing Gemini caching metrics.", "model": "gemini-3.5-pro"},
    )
    assert res.status_code == 200

    # Verify analytics contains cached token tracking
    analytics_res = client.get("/api/analytics/tokens")
    assert analytics_res.status_code == 200
    adata = analytics_res.json()
    assert "total_cached_tokens" in adata
    assert "cache_savings_usd" in adata
    assert adata["model_pricing"]["cached_discount"] == "75%"


def test_model_selection_streaming(feature_app):
    client, _, ai = feature_app
    register_and_login(client, "ivan")
    conv_id = create_conversation(client)

    # Test SSE streaming with explicit model parameter
    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "Streaming with Pro model.", "model": "gemini-3.5-pro"},
    ) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]
        assert any("data: " in line for line in lines)


def test_fork_with_rag_document_cache(feature_app):
    client, rag, _ = feature_app
    register_and_login(client, "judy")
    conv_id = create_conversation(client)

    # Ingest document
    file_bytes = b"Orbit Architecture Manual.\nPage 1: System utilizes reciprocal rank fusion.\nPage 2: Vector search with 3072 dimensions."
    upload_res = client.post(
        f"/api/conversations/{conv_id}/upload",
        files={"file": ("manual.txt", io.BytesIO(file_bytes), "text/plain")},
    )
    assert upload_res.status_code == 200

    # Fork conversation
    fork_res = client.post(f"/api/conversations/{conv_id}/fork")
    assert fork_res.status_code == 201
    forked_id = fork_res.json()["id"]

    # Verify document cache cloned
    assert f"{forked_id}:manual.txt" in rag.document_cache
    cached_content = rag.get_document_content("manual.txt", conversation_id=forked_id)
    assert len(cached_content) > 0


def test_rename_and_pin_conversation(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "karl")
    conv1 = create_conversation(client)
    conv2 = create_conversation(client)

    # 1. Rename conversation
    rename_res = client.patch(
        f"/api/conversations/{conv1}",
        json={"title": "Custom Architecture Spec"},
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["title"] == "Custom Architecture Spec"

    # 2. Pin conversation 1
    pin_res = client.patch(
        f"/api/conversations/{conv1}",
        json={"is_pinned": True},
    )
    assert pin_res.status_code == 200
    assert pin_res.json()["is_pinned"] is True

    # 3. Check list: pinned conversation must appear first
    list_res = client.get("/api/conversations")
    assert list_res.status_code == 200
    conversations = list_res.json()
    assert conversations[0]["id"] == conv1
    assert conversations[0]["is_pinned"] is True


def test_conversation_compaction_token_savings(feature_app):
    client, _, _ = feature_app
    register_and_login(client, "leo")
    conv_id = create_conversation(client)

    # Populate with 6 messages (3 turns)
    for i in range(1, 4):
        client.post(f"/api/conversations/{conv_id}/messages", json={"content": f"Turn {i}: Query"})

    # Check message count
    detail = client.get(f"/api/conversations/{conv_id}").json()
    assert len(detail["messages"]) == 6

    # Call compact
    compact_res = client.post(f"/api/conversations/{conv_id}/compact")
    assert compact_res.status_code == 200
    compact_data = compact_res.json()

    # Message count should be reduced to 4: turn 1 user, compact memory, and turn 3 user+assistant
    assert len(compact_data["messages"]) == 4
    compact_msg = next(m for m in compact_data["messages"] if "Compacted Prior Context" in m["content"])
    assert compact_msg["role"] == "assistant"
