import pymupdf  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter


def extract_pages_from_pdf(file_bytes: bytes) -> list[dict[str, any]]:
    """Extracts text page-by-page from a PDF, preserving page numbers for citation referencing."""
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text() or ""
        text = text.strip()
        if text:
            pages.append({"page": i + 1, "text": text})
    return pages


def extract_pages_from_file(filename: str, file_bytes: bytes) -> list[dict[str, any]]:
    """Extracts page-by-page structure from supported files."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return extract_pages_from_pdf(file_bytes)

    # For text-based files, decode text as Page 1
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            content = file_bytes.decode(encoding).strip()
            return [{"page": 1, "text": content}] if content else []
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to decode text content from {filename}")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Backward-compatible whole text extraction from PDF."""
    pages = extract_pages_from_pdf(file_bytes)
    return "\n\n".join(p["text"] for p in pages)


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """Backward-compatible whole text extraction from file."""
    pages = extract_pages_from_file(filename, file_bytes)
    return "\n\n".join(p["text"] for p in pages)


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
    """Splits text into smaller, overlapping chunks using structural separators."""
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


def chunk_document_pages(
    pages: list[dict[str, any]], chunk_size: int = 800, chunk_overlap: int = 100
) -> list[dict[str, any]]:
    """
    Semantic page-aware chunker.
    Breaks pages into chunks while attaching the exact page number to every chunk.
    Preserves structural headers and list boundaries.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    all_chunks: list[dict[str, any]] = []
    chunk_counter = 0

    for page_info in pages:
        page_num = page_info["page"]
        raw_text = page_info["text"]
        page_chunks = splitter.split_text(raw_text)

        for chunk in page_chunks:
            if chunk.strip():
                all_chunks.append({
                    "text": chunk.strip(),
                    "page": page_num,
                    "chunk_index": chunk_counter,
                })
                chunk_counter += 1

    return all_chunks
