import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, Protocol

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
        self.last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }

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

        meta = getattr(response, "usage_metadata", None)
        if meta:
            self.last_usage = {
                "prompt_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                "completion_tokens": getattr(meta, "candidates_token_count", 0) or 0,
                "total_tokens": getattr(meta, "total_token_count", 0) or 0,
                "cached_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
            }
        else:
            prompt_chars = sum(len(m.get("content", "")) for m in messages) + (len(context or "") if context else 0)
            comp_chars = len(response.text.strip())
            self.last_usage = {
                "prompt_tokens": max(prompt_chars // 4, 1),
                "completion_tokens": max(comp_chars // 4, 1),
                "total_tokens": max((prompt_chars + comp_chars) // 4, 2),
                "cached_tokens": 0,
            }
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
        captured_meta = None
        for i, client in enumerate(candidate_clients):
            try:
                response_stream = await client.aio.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                async for chunk in response_stream:
                    chunk_meta = getattr(chunk, "usage_metadata", None)
                    if chunk_meta:
                        captured_meta = chunk_meta
                    if chunk.text:
                        streamed_any = True
                        yield chunk.text

                if captured_meta:
                    self.last_usage = {
                        "prompt_tokens": getattr(captured_meta, "prompt_token_count", 0) or 0,
                        "completion_tokens": getattr(captured_meta, "candidates_token_count", 0) or 0,
                        "total_tokens": getattr(captured_meta, "total_token_count", 0) or 0,
                        "cached_tokens": getattr(captured_meta, "cached_content_token_count", 0) or 0,
                    }
                else:
                    prompt_chars = sum(len(m.get("content", "")) for m in messages) + (len(context or "") if context else 0)
                    self.last_usage = {
                        "prompt_tokens": max(prompt_chars // 4, 1),
                        "completion_tokens": max(len(messages[-1]["content"]) // 4, 1),
                        "total_tokens": max(prompt_chars // 4, 1) + max(len(messages[-1]["content"]) // 4, 1),
                        "cached_tokens": 0,
                    }
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

    async def optimize_prompt(self, user_prompt: str) -> str:
        """Uses LLM to transform a raw user query into a structured, unambiguous prompt."""
        client = self.active_clients[0] if self.active_clients else None
        clean_fallback = f"Provide a detailed, step-by-step technical explanation and practical code examples for: {user_prompt}"
        if not client:
            return clean_fallback
        try:
            req = (
                "You are an expert prompt engineer. Rewrite the following user prompt to be crystal-clear, "
                "well-structured, and highly effective for an AI LLM, removing ambiguities without adding fluff. "
                "Return ONLY the rewritten prompt with no commentary.\n\n"
                f"Original Prompt: {user_prompt}"
            )
            res = await client.aio.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=req)])],
                config=types.GenerateContentConfig(max_output_tokens=300, temperature=0.4),
            )
            enhanced = res.text.strip().strip('"\'`') if res.text else ""
            return enhanced if enhanced else clean_fallback
        except Exception as e:
            logger.warning("Prompt optimization failed (%s)", e)
            return clean_fallback

    async def generate_title(self, prompt: str, reply: str) -> str:
        """Uses LLM to summarize conversation intent into a concise 3-5 word title."""
        client = self.active_clients[0] if self.active_clients else None
        clean_fallback = " ".join(prompt.split())[:35]
        if not client:
            return clean_fallback
        try:
            req = (
                "Summarize the topic of this exchange into a concise 3 to 5 word title. "
                "Output ONLY the plain title with no quotes, punctuation, or preamble.\n\n"
                f"User: {prompt[:300]}\nAssistant: {reply[:300]}"
            )
            res = await client.aio.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=req)])],
                config=types.GenerateContentConfig(max_output_tokens=30, temperature=0.3),
            )
            title = res.text.strip().strip('"\'`') if res.text else ""
            return title[:50] if title else clean_fallback
        except Exception as e:
            logger.warning("Auto-title generation failed (%s), using heuristic", e)
            return clean_fallback

    async def generate_followup_suggestions(
        self, messages: list[dict[str, str]], last_reply: str
    ) -> list[str]:
        """Generates 3 concise, highly relevant follow-up questions for dynamic interactive prompting."""
        client = self.active_clients[0] if self.active_clients else None
        fallback_suggestions = [
            "Can you provide a practical code example?",
            "What are the main advantages and trade-offs?",
            "How can this be optimized for performance?",
        ]
        if not client:
            return fallback_suggestions
        try:
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            prompt = (
                "Based on the following query and response, suggest exactly 3 short, insightful follow-up questions "
                "that the user might ask next. Return ONLY a valid JSON list of 3 strings, e.g. [\"Q1\", \"Q2\", \"Q3\"].\n\n"
                f"User Query: {last_user[:300]}\n"
                f"Assistant Response: {last_reply[:400]}"
            )
            res = await client.aio.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(max_output_tokens=150, temperature=0.7),
            )
            text = res.text.strip() if res.text else ""
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    return [q.strip() for q in parsed[:3] if q.strip()]
        except Exception as e:
            logger.warning("Follow-up suggestion generation failed (%s)", e)
        return fallback_suggestions

    async def close(self) -> None:
        for client in self.clients:
            try:
                await client.aio.aclose()
                client.close()
            except Exception:
                pass
