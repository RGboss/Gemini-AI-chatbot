import logging
from typing import Protocol

import httpx
from fastapi import HTTPException
from google import genai
from google.genai import errors, types

from .config import Settings


logger = logging.getLogger(__name__)


class ReplyGenerator(Protocol):
    async def reply(self, messages: list[dict[str, str]]) -> str: ...

    async def close(self) -> None: ...


class GeminiService:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.gemini_model
        self.client = (
            genai.Client(
                api_key=settings.google_api_key,
                http_options=types.HttpOptions(timeout=60_000),
            )
            if settings.google_api_key
            and settings.google_api_key != "replace_with_your_google_ai_studio_key"
            else None
        )

    async def reply(self, messages: list[dict[str, str]]) -> str:
        if self.client is None:
            raise HTTPException(
                status_code=503,
                detail="Gemini is not configured. Set GOOGLE_API_KEY in backend/.env.",
            )
        contents = [
            types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part(text=message["content"])],
            )
            for message in messages
        ]
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are a helpful AI assistant. Give accurate, clear, "
                        "friendly answers. Use Markdown when it improves readability. "
                        "Be honest when you are uncertain."
                    ),
                    max_output_tokens=4096,
                ),
            )
        except errors.APIError as exc:
            logger.warning("Gemini API request failed (status %s)", exc.code)
            if exc.code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Google API quota exceeded. Please try again later.",
                ) from exc
            if exc.code in (401, 403):
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Google denied the API key. Create or select a Gemini API key "
                        "in Google AI Studio, confirm the Generative Language API is "
                        "enabled for its project, and check API-key restrictions."
                    ),
                ) from exc
            if exc.code in (400, 404):
                raise HTTPException(
                    status_code=502,
                    detail="Google rejected the request. Check the server's API key and model configuration.",
                ) from exc
            raise HTTPException(
                status_code=502, detail="Google is unavailable. Please try again."
            ) from exc
        except (httpx.TransportError, TimeoutError, OSError) as exc:
            logger.warning("Gemini connection failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=504,
                detail="The Google request timed out or could not connect. Please try again.",
            ) from exc
        if not response.text or not response.text.strip():
            raise HTTPException(
                status_code=502,
                detail="Google returned no text (the response may have been blocked). Try rephrasing your message.",
            )
        return response.text.strip()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aio.aclose()
            self.client.close()
