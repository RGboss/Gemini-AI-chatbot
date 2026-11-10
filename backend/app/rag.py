import logging
import re
import uuid
from typing import Any

from google import genai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from rank_bm25 import BM25Okapi

from .config import Settings
from .processor import chunk_document_pages, extract_pages_from_file

logger = logging.getLogger(__name__)

COLLECTION_NAME = "client_documents"
VECTOR_DIMENSION = 3072


def tokenize(text: str) -> list[str]:
    """Lightweight clean tokenizer for BM25 and keyword search."""
    return [w.lower() for w in re.findall(r"\b\w+\b", text)]


class RAGService:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        self.embedding_model = settings.embedding_model
        self.worker_audit_model = getattr(settings, "worker_audit_model", "gemini-3.5-flash")
        self.worker_keys = settings.worker_keys
        self.worker_clients = (
            [genai.Client(api_key=k) for k in self.worker_keys]
            if not client and self.worker_keys
            else ([client] if client else [])
        )
        self.client = self.worker_clients[0] if self.worker_clients else None
        self.qdrant = QdrantClient(":memory:")
        # Store page-by-page document cache in memory for split-screen document viewer
        self.document_cache: dict[str, list[dict[str, Any]]] = {}
        self._init_collection()

    async def embed_with_failover(self, contents: list[str] | str):
        """Embeds contents using worker key with automatic failover."""
        if not self.worker_clients:
            raise ValueError("No Gemini API key configured for worker vector embeddings.")
        last_err = None
        for i, c in enumerate(self.worker_clients):
            try:
                return await c.aio.models.embed_content(
                    model=self.embedding_model,
                    contents=contents,
                )
            except Exception as e:
                last_err = e
                logger.warning("Worker key #%d embedding failed (%s), trying failover...", i + 1, e)
                continue
        raise last_err or ValueError("Failed to generate embeddings across all worker keys.")

    async def deep_technical_audit(
        self, document_text: str, criteria: str = "technical accuracy, architecture, risks"
    ) -> str:
        """
        Runs a heavy, deep-reasoning audit on a document chunk or codebase using Worker Key.
        Uses GEMINI_WORKER_KEY quota so heavy auditing tokens don't throttle the main chat.
        """
        if not self.worker_clients:
            raise ValueError("No worker Gemini API key configured for technical audit.")

        prompt = (
            f"You are Orbit Deep Technical Auditor. Audit the following text against these criteria:\n"
            f"CRITERIA: {criteria}\n\n"
            f"DOCUMENT TEXT:\n{document_text}\n\n"
            f"Deliver an expert, structured assessment with findings, security/architecture critique, ATS scoring, and prioritized fixes."
        )

        for i, c in enumerate(self.worker_clients):
            try:
                res = await c.aio.models.generate_content(
                    model=self.worker_audit_model,
                    contents=prompt,
                )
                if res.text:
                    return res.text.strip()
            except Exception as e:
                logger.warning("Worker key #%d audit failed (%s), trying failover...", i + 1, e)
                continue
        raise ValueError("Deep technical audit failed across all worker keys.")

    def _init_collection(self) -> None:
        try:
            self.qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_DIMENSION, distance=Distance.COSINE),
            )
            logger.info("Qdrant collection '%s' ready (dim=%d)", COLLECTION_NAME, VECTOR_DIMENSION)
        except Exception as exc:
            logger.info("Collection '%s' ready: %s", COLLECTION_NAME, exc)

    def should_retrieve_documents(self, query: str, conversation_id: str | None = None) -> bool:
        """
        Agentic Query Router:
        Decides if a query needs document retrieval or if it is purely conversational.
        Saves vector database lookups and reduces latency.
        """
        # If no documents are attached, skip retrieval
        docs = self.list_documents(conversation_id=conversation_id)
        if not docs:
            return False

        q = query.strip().lower()
        # Chit-chat and pure conversational greetings
        conversational_patterns = {
            "hi", "hello", "hey", "good morning", "good evening", "how are you",
            "who are you", "what can you do", "thanks", "thank you", "cool", "nice",
            "ok", "okay", "bye", "goodbye", "see ya", "help me"
        }
        if q in conversational_patterns or len(q.split()) <= 1 and q not in {"search", "find"}:
            return False

        # If user explicitly asks about documents, facts, summaries, or questions
        return True

    def expand_conversational_query(self, query: str, history: list[dict[str, str]] | None) -> str:
        """
        Conversational Memory Injection:
        When a user asks follow-up questions (e.g. 'Can you rewrite that first point?'),
        augments the search query with recent conversational context so vector retrieval
        doesn't search on isolated pronouns.
        """
        if not history:
            return query

        # Check if the query is a follow-up or contains pronouns
        follow_up_triggers = {"that", "it", "this", "they", "first", "second", "last", "more", "explain", "rewrite"}
        tokens = set(tokenize(query))
        if tokens & follow_up_triggers and len(history) >= 2:
            last_assistant_turn = history[-1]["content"] if history[-1]["role"] == "assistant" else ""
            last_user_turn = history[-2]["content"] if history[-2]["role"] == "user" else ""
            # Combine current query with context keywords from previous turn
            context_summary = " ".join(last_user_turn.split()[:20] + last_assistant_turn.split()[:20])
            return f"{query} {context_summary}".strip()

        return query

    async def ingest_document(
        self,
        filename: str,
        file_bytes: bytes,
        conversation_id: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Page-aware semantic ingestion:
        Extracts pages with page numbers, chunks them, generates embeddings,
        and saves into Qdrant vector DB and document cache.
        """
        if self.client is None:
            raise ValueError("Gemini API key is not configured for vector embeddings.")

        pages = extract_pages_from_file(filename, file_bytes)
        if not pages:
            raise ValueError(f"No extractable text found in '{filename}'. Ensure document has selectable text.")

        # Cache document pages for Split-Screen Document Viewer
        cache_key = f"{conversation_id or ''}:{filename}"
        self.document_cache[cache_key] = pages

        # Chunk pages while preserving exact page numbers
        chunks = chunk_document_pages(pages, chunk_size=800, chunk_overlap=100)
        if not chunks:
            raise ValueError(f"Unable to generate chunks from '{filename}'.")

        points: list[PointStruct] = []
        batch_size = 20
        safe_conv_id = conversation_id or ""
        safe_user_id = user_id or 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            contents = [item["text"] for item in batch]
            emb_res = await self.embed_with_failover(contents)
            for j, emb in enumerate(emb_res.embeddings):
                point_id = str(uuid.uuid4())
                chunk_item = batch[j]
                payload = {
                    "text": chunk_item["text"],
                    "source": filename,
                    "page": chunk_item["page"],
                    "chunk_index": chunk_item["chunk_index"],
                    "conversation_id": safe_conv_id,
                    "user_id": safe_user_id,
                }
                points.append(PointStruct(id=point_id, vector=emb.values, payload=payload))

        self.qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        total_chars = sum(len(p["text"]) for p in pages)
        logger.info(
            "Ingested '%s': %d pages, %d chunks indexed into Qdrant (conv=%s)",
            filename,
            len(pages),
            len(chunks),
            safe_conv_id,
        )
        return {
            "status": "success",
            "filename": filename,
            "pages_count": len(pages),
            "chunks_processed": len(chunks),
            "characters": total_chars,
            "conversation_id": conversation_id,
        }

    async def search_relevant_chunks(
        self,
        query: str,
        conversation_id: str | None = None,
        user_id: int | None = None,
        limit: int = 4,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Advanced RAG Pipeline:
        1. Agentic Routing: checks if retrieval is needed.
        2. Conversational Expansion: incorporates memory if follow-up.
        3. Hybrid Search: Dense Vector + BM25 Lexical with Reciprocal Rank Fusion (RRF).
        4. Cross-Encoder / Relevance Reranking: scores top candidates against query terms.
        """
        if not self.should_retrieve_documents(query, conversation_id=conversation_id):
            return []

        expanded_query = self.expand_conversational_query(query, history)

        try:
            query_res = await self.embed_with_failover(expanded_query)
            query_vector = query_res.embeddings[0].values
        except Exception as exc:
            logger.warning("Failed to embed query: %s", exc)
            return []

        # 1. Fetch Top-15 Dense Vector Candidates from Qdrant
        query_filter = None
        if conversation_id:
            query_filter = Filter(
                should=[
                    FieldCondition(key="conversation_id", match=MatchValue(value=conversation_id)),
                    FieldCondition(key="conversation_id", match=MatchValue(value="")),
                ]
            )
        elif user_id:
            query_filter = Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            )

        try:
            vector_results = self.qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=query_filter,
                limit=15,
            )
            candidate_points = [
                hit for hit in vector_results.points if hit.payload and "text" in hit.payload
            ]
        except Exception as exc:
            logger.warning("Vector search candidate fetch failed: %s", exc)
            return []

        if not candidate_points:
            return []

        # 2. BM25 Keyword Search across candidate chunks
        tokenized_query = tokenize(query)
        corpus = [p.payload["text"] for p in candidate_points]
        tokenized_corpus = [tokenize(doc) for doc in corpus]

        try:
            bm25 = BM25Okapi(tokenized_corpus)
            bm25_scores = bm25.get_scores(tokenized_query)
        except Exception as exc:
            logger.warning("BM25 scoring failed, falling back to dense: %s", exc)
            bm25_scores = [0.0] * len(candidate_points)

        # 3. Reciprocal Rank Fusion (RRF) combining Dense & BM25
        dense_ranked = sorted(range(len(candidate_points)), key=lambda i: candidate_points[i].score, reverse=True)
        bm25_ranked = sorted(range(len(candidate_points)), key=lambda i: bm25_scores[i], reverse=True)

        k_rrf = 60
        rrf_scores: dict[int, float] = {i: 0.0 for i in range(len(candidate_points))}
        for rank, idx in enumerate(dense_ranked):
            rrf_scores[idx] += 1.0 / (k_rrf + rank + 1)
        for rank, idx in enumerate(bm25_ranked):
            rrf_scores[idx] += 1.0 / (k_rrf + rank + 1)

        # 4. Cross-Encoder / Relevance Re-Scoring
        # Computes exact term coverage, phrase matches, and dense affinity
        scored_candidates = []
        query_words = set(tokenized_query)

        for idx, point in enumerate(candidate_points):
            payload = point.payload
            text = payload["text"]
            text_tokens = set(tokenize(text))

            # Keyword overlap ratio
            term_overlap = len(query_words & text_tokens) / max(len(query_words), 1)

            # Exact phrase match boost
            phrase_boost = 1.3 if query.lower() in text.lower() else 1.0

            # Final hybrid rerank score
            combined_score = (rrf_scores[idx] * 0.5 + point.score * 0.3 + term_overlap * 0.2) * phrase_boost

            scored_candidates.append({
                "text": text,
                "source": payload.get("source", "Unknown"),
                "page": payload.get("page", 1),
                "score": combined_score,
                "dense_score": point.score,
            })

        # Sort by rerank score and return top results
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        return scored_candidates[:limit]

    def list_documents(
        self, conversation_id: str | None = None, user_id: int | None = None
    ) -> list[str]:
        try:
            query_filter = None
            if conversation_id:
                query_filter = Filter(
                    should=[
                        FieldCondition(key="conversation_id", match=MatchValue(value=conversation_id)),
                        FieldCondition(key="conversation_id", match=MatchValue(value="")),
                    ]
                )
            elif user_id:
                query_filter = Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                )
            res, _ = self.qdrant.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=query_filter,
                limit=300,
                with_payload=True,
                with_vectors=False,
            )
            sources = sorted(
                {p.payload["source"] for p in res if p.payload and "source" in p.payload}
            )
            return sources
        except Exception as exc:
            logger.warning("Failed to list documents: %s", exc)
            return []

    def get_document_content(self, filename: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
        """Returns page-by-page content for Split-Screen Document Viewer."""
        cache_key = f"{conversation_id or ''}:{filename}"
        if cache_key in self.document_cache:
            return self.document_cache[cache_key]

        # Search any cache matching filename
        for key, pages in self.document_cache.items():
            if key.endswith(f":{filename}"):
                return pages

        return []
