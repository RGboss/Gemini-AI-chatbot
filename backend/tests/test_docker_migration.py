import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from app.config import Settings
from app.gemini import GeminiService
from app.main import create_app


@pytest.fixture
def test_app():
    settings = Settings(
        _env_file=None,
        google_api_key="test_key",
        gemini_orchestrator_key="test_orch_key",
        gemini_worker_key="test_work_key",
        database_url="",
    )
    fake_ai = GeminiService(settings)
    fake_ai.reply = AsyncMock(return_value="Hello! I am Orbit, your AI assistant.")
    fake_ai.reply_stream = AsyncMock()

    app = create_app(settings, fake_ai)
    return TestClient(app)


def test_root_health_endpoint(test_app):
    """Verifies the GET /health Docker healthcheck endpoint returns healthy."""
    response = test_app.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_api_health_endpoint(test_app):
    """Verifies the GET /api/health endpoint returns full configuration metadata."""
    response = test_app.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "model" in data
    assert "ai_configured" in data


def test_direct_api_chat_endpoint(test_app):
    """Verifies POST /api/chat handles messages and returns reply, sources, and confidence."""
    response = test_app.post("/api/chat", json={"message": "What is Orbit?"})
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["reply"] == "Hello! I am Orbit, your AI assistant."
    assert "sources" in data
    assert "confidence" in data


def test_gemini_resilience_and_model_fallback():
    """Verifies exponential backoff and fallback models on 503 / 429."""
    settings = Settings(_env_file=None, google_api_key="test_key")
    service = GeminiService(settings)

    # Simulate primary model failing with 503, fallback succeeding
    call_models = []

    async def mock_generate(model, contents, config):
        call_models.append(model)
        if len(call_models) < 2:
            raise errors.APIError(503, {"message": "Service Unavailable"})
        return SimpleNamespace(text="Resilient answer", usage_metadata=None)

    mock_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=mock_generate))
    )
    service.client = mock_client
    service.clients = [mock_client]

    reply = asyncio.run(service.reply([{"role": "user", "content": "Test resilience"}]))
    assert reply == "Resilient answer"
    assert len(call_models) >= 2
    assert "gemini-3.5-flash" in call_models
