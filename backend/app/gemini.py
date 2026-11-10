from typing import Any
import logging
from collections.abc import AsyncIterator
from typing import Protocol

import httpx
from fastapi import HTTPException
from google import genai
from google.genai import errors, types

from .config import Settings


logger = logging.getLogger(__name__)


class ReplyGenerator(Protocol):
    async def reply(
        self, messages: list[dict[str, str]], context: str | None = None
    ) -> str: ...

    async def reply_stream(
        self, messages: list[dict[str, str]], context: str | None = None
    ) -> AsyncIterator[str]: ...

    async def close(self) -> None: ...


class GeminiService:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.gemini_model
        self.keys = settings.orchestrator_keys
        self.clients = [
            genai.Client(
                api_key=key,
                http_options=types.HttpOptions(timeout=60_000),
            )
            for key in self.keys
        ]
        self.client = self.clients[0] if self.clients else None

    @property
    def active_clients(self) -> list[Any]:
        """Returns the list of active clients; if client was mocked, preserves mock isolation."""
        if self.client and (not self.clients or self.client is not self.clients[0]):
            return [self.client]
        return self.clients

    def _build_system_instruction(self, context: str | None) -> str:
        base = (
            "You are Orbit, an autonomous, intelligent, and insightful AI workspace companion. "
            "Your tone is thoughtful, sharp, articulate, and helpful. Always identify yourself as Orbit.\n"
            "Format code, tables, and explanations cleanly using Markdown.\n"
        )
        if context:
            base += (
                f"\n--- VERIFIED DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                "INSTRUCTION:\n"
                "1. Use the verified document context above to answer the user's questions accurately.\n"
                "2. When extracting data or referencing facts, append a clickable citation like [Document: filename.pdf, Page X] or [Page X].\n"
                "3. If the user asks about specific information from the document that is NOT in the context, "
                "explicitly state: \"I cannot find the answer in the provided documents.\"\n"
                "4. Do not hallucinate data that is not in the context."
            )
        return base

    async def generate_with_failover(
        self,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
    ):
        """
        Automatic Key Failover (Rotation Wrapper):
        Tries primary GEMINI_ORCHESTRATOR_KEY first; on 429 quota exhaustion or 403 authorization
        failures, seamlessly rotates to backup worker / orchestrator keys.
        """
        candidate_clients = self.active_clients

        if not candidate_clients:
            raise HTTPException(
                status_code=503,
                detail="Orbit is not configured. Set GOOGLE_API_KEY in backend/.env.",
            )

        last_error = None
        for i, client in enumerate(candidate_clients):
            try:
                response = await client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                return response
            except errors.APIError as exc:
                last_error = exc
                logger.warning(
                    "Key #%d failed (code=%s). Attempting automatic failover...",
                    i + 1,
                    exc.code,
                )
                if i + 1 < len(candidate_clients) and exc.code in (429, 401, 403):
                    continue
                if exc.code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="Orbit request quota exceeded. Please try again later.",
                    ) from exc
                if exc.code in (401, 403):
                    raise HTTPException(
                        status_code=502,
                        detail="API key was denied. Check API key and permissions in backend/.env.",
                    ) from exc
                if exc.code in (400, 404):
                    raise HTTPException(
                        status_code=502,
                        detail="Request rejected. Check the server's API key and model configuration in backend/.env.",
                    ) from exc
                raise HTTPException(
                    status_code=502,
                    detail="Orbit service is temporarily unavailable. Please try again.",
                ) from exc
            except (httpx.TransportError, TimeoutError, OSError) as exc:
                last_error = exc
                logger.warning("Key #%d network error (%s). Trying failover...", i + 1, type(exc).__name__)
                if i + 1 < len(candidate_clients):
                    continue
                raise HTTPException(
                    status_code=504,
                    detail="Connection timed out. Please try again.",
                ) from exc

        if last_error:
            raise HTTPException(
                status_code=502,
                detail="Orbit service is temporarily unavailable. All failover attempts exhausted.",
            )
        raise HTTPException(
            status_code=503,
            detail="Orbit is not configured. Set GOOGLE_API_KEY in backend/.env.",
        )

    async def reply(
        self, messages: list[dict[str, str]], context: str | None = None
    ) -> str:
        contents = [
            types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part(text=message["content"])],
            )
            for message in messages
        ]

        system_instruction = self._build_system_instruction(context)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=4096,
        )

        response = await self.generate_with_failover(contents, config)
        if not response.text or not response.text.strip():
            raise HTTPException(
                status_code=502,
                detail="Orbit returned an empty reply. Please rephrase your message.",
            )
        return response.text.strip()

    async def reply_stream(
        self, messages: list[dict[str, str]], context: str | None = None
    ) -> AsyncIterator[str]:
        candidate_clients = self.active_clients

        if not candidate_clients:
            raise HTTPException(
                status_code=503,
                detail="Orbit is not configured. Set GOOGLE_API_KEY in backend/.env.",
            )

        contents = [
            types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part(text=message["content"])],
            )
            for message in messages
        ]

        system_instruction = self._build_system_instruction(context)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=4096,
        )

        # Attempt stream with failover across clients
        streamed_any = False
        for i, client in enumerate(candidate_clients):
            try:
                response_stream = await client.aio.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                async for chunk in response_stream:
                    if chunk.text:
                        streamed_any = True
                        yield chunk.text
                return
            except Exception as exc:
                logger.warning("Streaming with key #%d failed (%s)", i + 1, exc)
                if streamed_any:
                    # If tokens were already sent to client, don't restart full text stream
                    return
                continue

        # If streaming attempts failed before any token emitted, fall back to complete generation
        fallback = await self.reply(messages, context=context)
        yield fallback

    async def close(self) -> None:
        for client in self.clients:
            try:
                await client.aio.aclose()
                client.close()
            except Exception:
                pass
