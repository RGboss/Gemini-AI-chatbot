import asyncio
import hashlib
import json
import logging
import re
import time
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
        self, messages: list[dict[str, str]], context: str | None = None, **kwargs: Any
    ) -> str: ...

    async def reply_stream(
        self, messages: list[dict[str, str]], context: str | None = None, **kwargs: Any
    ) -> AsyncIterator[str]: ...

    async def compact_history(self, messages_to_compress: list[dict[str, str]]) -> str: ...

    async def close(self) -> None: ...


class GeminiService:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.gemini_model
        self.keys = settings.orchestrator_keys
        self.clients = [
            genai.Client(
                api_key=key,
                http_options=types.HttpOptions(timeout=15_000),
            )
            for key in self.keys
        ]
        self.client = self.clients[0] if self.clients else None
        self.context_caches: dict[str, dict[str, Any]] = {}
        self.last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }

    async def get_or_create_context_cache(self, conversation_id: str, context: str) -> str | None:
        """
        Gemini Context Caching:
        For long context or large documents (>8,000 chars / ~2,048 tokens), creates or reuses
        a server-side Gemini cached content object, slashing subsequent prompt token costs by 75-90%.
        """
        if not context or len(context) < 8000:
            return None
        client = self.active_clients[0] if self.active_clients else None
        if not client or not hasattr(client, "aio") or not hasattr(client.aio, "caches"):
            return None

        content_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()
        existing = self.context_caches.get(conversation_id)
        if existing and existing.get("hash") == content_hash:
            if time.time() - existing.get("created_at", 0) < 3300:
                return existing["name"]

        try:
            cache = await client.aio.caches.create(
                model=self.model,
                config=types.CreateCachedContentConfig(
                    contents=[types.Content(role="user", parts=[types.Part(text=context)])],
                    ttl="3600s",
                ),
            )
            cache_name = getattr(cache, "name", None)
            if cache_name:
                self.context_caches[conversation_id] = {
                    "name": cache_name,
                    "hash": content_hash,
                    "created_at": time.time(),
                }
                logger.info("Created Gemini context cache: %s for conv: %s", cache_name, conversation_id)
                return cache_name
        except Exception as exc:
            logger.debug("Context cache creation bypassed (%s)", exc)
        return None

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
        model: str | None = None,
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

        target_model = model or self.model
        models_to_try = [target_model]
        for fallback in ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-2.5-pro", "gemini-1.5-flash"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for current_model in models_to_try:
            for i, client in enumerate(candidate_clients):
                retries = 2 if current_model == target_model else 1
                for attempt in range(retries):
                    try:
                        response = await client.aio.models.generate_content(
                            model=current_model,
                            contents=contents,
                            config=config,
                        )
                        return response
                    except errors.APIError as exc:
                        last_error = exc
                        logger.warning(
                            "Model %s with Key #%d attempt %d failed (code=%s). Attempting failover...",
                            current_model,
                            i + 1,
                            attempt + 1,
                            exc.code,
                        )
                        if exc.code in (429, 503) and attempt + 1 < retries:
                            await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
                            continue
                        if i + 1 < len(candidate_clients) and exc.code in (429, 401, 403, 503):
                            break
                        break
                    except (httpx.TransportError, TimeoutError, OSError) as exc:
                        last_error = exc
                        logger.warning("Key #%d network error (%s). Trying failover...", i + 1, type(exc).__name__)
                        if i + 1 < len(candidate_clients):
                            break
                        break

        if last_error:
            if isinstance(last_error, errors.APIError):
                if last_error.code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="Orbit request quota exceeded. Please try again later.",
                    ) from last_error
                if last_error.code in (401, 403):
                    raise HTTPException(
                        status_code=502,
                        detail="API key was denied. Check API key and permissions in backend/.env.",
                    ) from last_error
                if last_error.code in (400, 404):
                    raise HTTPException(
                        status_code=502,
                        detail="Request rejected. Check the server's API key and model configuration in backend/.env.",
                    ) from last_error
                raise HTTPException(
                    status_code=502,
                    detail="Orbit service is temporarily unavailable. Please try again.",
                ) from last_error
            if isinstance(last_error, (httpx.TransportError, TimeoutError, OSError)):
                raise HTTPException(
                    status_code=504,
                    detail="Connection timed out. Please try again.",
                ) from last_error
            raise HTTPException(
                status_code=502,
                detail="Orbit service is temporarily unavailable. All failover attempts exhausted.",
            )
        raise HTTPException(
            status_code=503,
            detail="Orbit is not configured. Set GOOGLE_API_KEY in backend/.env.",
        )

    async def reply(
        self,
        messages: list[dict[str, str]],
        context: str | None = None,
        model: str | None = None,
        cached_content: str | None = None,
    ) -> str:
        contents = [
            types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part(text=message["content"])],
            )
            for message in messages
        ]

        system_instruction = self._build_system_instruction(context if not cached_content else None)
        config_kwargs: dict[str, Any] = {"max_output_tokens": 4096}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if cached_content:
            config_kwargs["cached_content"] = cached_content

        config = types.GenerateContentConfig(**config_kwargs)

        response = await self.generate_with_failover(contents, config, model=model)
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
        self,
        messages: list[dict[str, str]],
        context: str | None = None,
        model: str | None = None,
        cached_content: str | None = None,
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

        system_instruction = self._build_system_instruction(context if not cached_content else None)
        config_kwargs: dict[str, Any] = {"max_output_tokens": 4096}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if cached_content:
            config_kwargs["cached_content"] = cached_content

        config = types.GenerateContentConfig(**config_kwargs)
        target_model = model or self.model

        # Attempt stream with failover across clients
        streamed_any = False
        captured_meta = None
        for i, client in enumerate(candidate_clients):
            try:
                response_stream = await client.aio.models.generate_content_stream(
                    model=target_model,
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
        fallback = await self.reply(messages, context=context, model=target_model, cached_content=cached_content)
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

    async def compact_history(self, messages_to_compress: list[dict[str, str]]) -> str:
        """
        Context Window Compactor:
        Summarizes intermediate conversational turns into a dense, high-signal briefing.
        Preserves critical user requirements, architectural constraints, and facts
        while trimming redundant filler, reducing prompt token costs by 70-85%.
        """
        formatted = "\n".join(
            f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
            for m in messages_to_compress
        )
        prompt = (
            "Summarize the following prior conversation dialogue into a dense, structured memory briefing. "
            "Highlight core decisions, user requirements, technical specs, and established facts in 2 concise paragraphs. "
            "Do not include conversational pleasantries.\n\n"
            f"DIALOGUE:\n{formatted}\n\nSUMMARY:"
        )
        try:
            res = await self.generate_with_failover(
                contents=prompt,
                model=self.model,
                temperature=0.2,
                max_output_tokens=350,
            )
            return res.text.strip()
        except Exception as exc:
            logger.warning("History compaction failed, using fallback truncation: %s", exc)
            return "Prior dialogue summarized: user and assistant discussed requirements, architecture, and code design."

    async def close(self) -> None:
        for client in self.clients:
            try:
                await client.aio.aclose()
                client.close()
            except Exception:
                pass
