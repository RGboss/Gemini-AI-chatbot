import pytest
import pymupdf
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.processor import chunk_text, extract_text_from_pdf
from app.rag import RAGService


def create_sample_pdf(text: str = "Orbit is an autonomous AI system designed for high velocity research and coding.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    rect = pymupdf.Rect(50, 50, 550, 750)
    page.insert_textbox(rect, text)
    return doc.tobytes()


def test_pdf_extraction_and_chunking():
    paragraphs = [
        "Paragraph 1: Orbit Document Processing Engine handles enterprise PDF and document parsing.",
        "Paragraph 2: The chunking module breaks massive legal and compliance documents into smaller paragraphs.",
        "Paragraph 3: Vectors are indexed into Qdrant for semantic similarity search with cosine distance metric.",
        "Paragraph 4: Orbit retrieves relevant context and answers strictly from verified document sources.",
    ]
    full_text = "\n\n".join(paragraphs * 4)
    pdf_bytes = create_sample_pdf(full_text)
    extracted = extract_text_from_pdf(pdf_bytes)
    assert "Orbit Document Processing Engine" in extracted

    chunks = chunk_text(extracted, chunk_size=200, chunk_overlap=30)
    assert len(chunks) > 1


class FakeEmbeddingClient:
    class Models:
        async def embed_content(self, model, contents, **kwargs):
            class Emb:
                values = [0.05] * 3072

            class Res:
                embeddings = [Emb() for _ in (contents if isinstance(contents, list) else [contents])]

            return Res()

    def __init__(self):
        self.aio = self
        self.models = self.Models()


class FakeChatReply:
    def __init__(self):
        self.calls = []

    async def reply(self, messages, context=None):
        self.calls.append({"messages": messages, "context": context})
        return f"Based on the context, here is the answer: {context[:40] if context else 'No context'}"

    async def close(self):
        pass


@pytest.fixture
def rag_app(tmp_path):
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        google_api_key="test_key",
    )
    fake_client = FakeEmbeddingClient()
    rag_service = RAGService(settings, client=fake_client)
    fake_ai = FakeChatReply()
    app = create_app(settings=settings, generator=fake_ai, rag_service=rag_service)
    with TestClient(app) as client:
        yield client, rag_service, fake_ai


def test_upload_and_chat_endpoints(rag_app):
    client, rag_service, fake_ai = rag_app

    # Test PDF upload to /upload
    pdf_content = create_sample_pdf("The secret revenue number is 42 million dollars for Q3.")
    files = {"file": ("revenue_report.pdf", pdf_content, "application/pdf")}
    res = client.post("/upload", files=files)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "success"
    assert res.json()["filename"] == "revenue_report.pdf"
    assert res.json()["chunks_processed"] >= 1

    # Test Phase 3 /chat endpoint
    chat_res = client.post("/chat", json={"message": "What is the secret revenue number?"})
    assert chat_res.status_code == 200, chat_res.text
    data = chat_res.json()
    assert "revenue_report.pdf" in data["sources"]
    assert "reply" in data
