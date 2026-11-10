"""Orbit Worker MCP Server (Project B Task Isolation).

Dedicated to heavy background tasks:
1. High-volume PDF chunk embedding and vector search.
2. Deep technical audits, architecture critiques, and ATS scoring.
Runs with GEMINI_WORKER_KEY to prevent exhausting user chat quota on Project A.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP
from google import genai
from qdrant_client import QdrantClient

# Load environment configuration from .env if present
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

mcp = FastMCP("Orbit_Worker_Server")

WORKER_KEY = (
    os.environ.get("GEMINI_WORKER_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GEMINI_ORCHESTRATOR_KEY")
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
AUDIT_MODEL = os.environ.get("WORKER_AUDIT_MODEL", "gemini-3.5-flash")

worker_gemini = genai.Client(api_key=WORKER_KEY) if WORKER_KEY else None
qdrant = QdrantClient(":memory:")
COLLECTION_NAME = "client_documents"


def _embed_query(query: str):
    """Embeds query using worker key with model fallback."""
    if not worker_gemini:
        raise ValueError("GEMINI_WORKER_KEY is not configured.")
    models_to_try = [EMBEDDING_MODEL, "gemini-embedding-001", "text-embedding-004"]
    for m in models_to_try:
        try:
            res = worker_gemini.models.embed_content(model=m, contents=query)
            return res.embeddings[0].values
        except Exception:
            continue
    raise RuntimeError("Worker embedding failed across all supported embedding models.")


@mcp.tool()
def search_uploaded_documents(query: str, top_k: int = 4) -> str:
    """
    Embeds the query using the Worker API key (Project B) and retrieves matching document chunks.
    """
    if not worker_gemini:
        return "Worker Gemini key is not configured in environment."

    try:
        query_vector = _embed_query(query)
    except Exception as exc:
        return f"Embedding failed: {exc}"

    # Search in Qdrant (supports query_points in 1.20+ and legacy search)
    try:
        if hasattr(qdrant, "query_points"):
            res = qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=top_k,
            )
            hits = getattr(res, "points", [])
        else:
            hits = qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=top_k,
            )

        if not hits:
            return "No matching documents found in vector store."

        parts = []
        for hit in hits:
            payload = getattr(hit, "payload", {}) or {}
            text = payload.get("text", "")
            source = payload.get("source", "document")
            page = payload.get("page", 1)
            parts.append(f"[{source} - Page {page}]\n{text}")

        return "\n\n---\n\n".join(parts)
    except Exception as exc:
        return f"Vector retrieval note: {exc}"


@mcp.tool()
def deep_technical_audit(document_text: str, criteria: str = "technical accuracy, architecture, risks") -> str:
    """
    Runs a heavy, deep-reasoning audit on a document chunk, resume, or architecture using Gemini.
    Uses GEMINI_WORKER_KEY quota so heavy audit tokens don't throttle the main chat.
    """
    if not worker_gemini:
        return "Worker Gemini key is not configured in environment."

    models_to_try = [AUDIT_MODEL, "gemini-3.5-flash", "gemini-3.1-pro-preview"]
    prompt = (
        f"You are Orbit Deep Technical Auditor (Project B Worker).\n"
        f"Audit the following text strictly against these criteria: ({criteria})\n\n"
        f"DOCUMENT TEXT:\n{document_text}\n\n"
        f"Provide an expert critique with strengths, architecture risks, ATS/code quality scoring, and concrete fixes."
    )

    for m in models_to_try:
        try:
            res = worker_gemini.models.generate_content(
                model=m,
                contents=prompt,
            )
            if res.text:
                return res.text.strip()
        except Exception:
            continue

    return "Audit failed to generate content with available worker models."


if __name__ == "__main__":
    mcp.run()

