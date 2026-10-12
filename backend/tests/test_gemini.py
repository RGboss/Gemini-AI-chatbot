import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from google.genai import errors

from app.config import Settings
from app.gemini import GeminiService


def service_with_mock(response=None, error=None):
    service = GeminiService(Settings(_env_file=None, google_api_key=""))
    generate = AsyncMock(
        return_value=SimpleNamespace(text=response), side_effect=error
    )
    service.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    )
    return service, generate


def test_provider_roles_model_and_output():
    service, generate = service_with_mock("  A real formatted reply.  ")
    reply = asyncio.run(service.reply([
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Answer"},
        {"role": "user", "content": "Follow-up"},
    ]))
    assert reply == "A real formatted reply."
    arguments = generate.call_args.kwargs
    assert arguments["model"] == "gemini-2.5-flash"
    assert [content.role for content in arguments["contents"]] == ["user", "model", "user"]
    assert arguments["contents"][-1].parts[0].text == "Follow-up"
    assert arguments["config"].max_output_tokens == 4096


@pytest.mark.parametrize(
    "code, expected_status",
    [(400, 502), (401, 502), (403, 502), (404, 502), (429, 429), (500, 502)],
)
def test_provider_errors_are_safe_and_actionable(code, expected_status):
    service, _ = service_with_mock(
        error=errors.APIError(code, {"message": "private-provider-detail"})
    )
    with pytest.raises(HTTPException) as failure:
        asyncio.run(service.reply([{"role": "user", "content": "Hi"}]))
    assert failure.value.status_code == expected_status
    assert "private-provider-detail" not in failure.value.detail


@pytest.mark.parametrize("text", [None, "", "  "])
def test_empty_provider_response_is_not_a_success(text):
    service, _ = service_with_mock(text)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(service.reply([{"role": "user", "content": "Hi"}]))
    assert failure.value.status_code == 502


def test_network_timeout():
    service, _ = service_with_mock(error=httpx.ReadTimeout("private-provider-detail"))
    with pytest.raises(HTTPException) as failure:
        asyncio.run(service.reply([{"role": "user", "content": "Hi"}]))
    assert failure.value.status_code == 504
