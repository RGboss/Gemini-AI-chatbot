import pytest
from app.config import Settings
from app.gemini import GeminiService
from app.rag import RAGService
import orbit_mcp_server


def test_config_dual_key_properties():
    settings = Settings(
        _env_file=None,
        gemini_orchestrator_key="key_orch",
        gemini_worker_key="key_work",
        google_api_key="key_default",
    )
    # Orchestrator candidates order
    assert settings.orchestrator_keys == ["key_orch", "key_default", "key_work"]
    # Worker candidates order
    assert settings.worker_keys == ["key_work", "key_default", "key_orch"]


def test_dual_key_service_initialization():
    settings = Settings(
        _env_file=None,
        gemini_orchestrator_key="key_orch",
        gemini_worker_key="key_work",
    )
    ai = GeminiService(settings)
    rag = RAGService(settings)

    assert len(ai.clients) >= 1
    assert len(rag.worker_clients) >= 1
    assert rag.worker_audit_model == "gemini-3.5-flash"


def test_mcp_server_tools_registered():
    import asyncio
    tools = asyncio.run(orbit_mcp_server.mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "search_uploaded_documents" in tool_names
    assert "deep_technical_audit" in tool_names
