"""
rag/ingestion.py — Document ingestion pipeline.

Flow:
  file upload → load & parse → chunk → embed → upsert vào Qdrant

Hỗ trợ: PDF, TXT, MD, DOCX
Chunking: RecursiveCharacterTextSplitter (chunk_size=512, overlap=50)
Metadata: filename, page_number, chunk_index, ingestion_timestamp

Usage:
    from src.rag.ingestion import ingest_file
    result = await ingest_file(file_bytes, filename="report.pdf")
"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
)
from langchain_core.documents import Document
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from src.config import settings
from src.core.embeddings import embed_client

logger = structlog.get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Tạo Qdrant collection nếu chưa tồn tại (idempotent)."""
    exists = await client.collection_exists(settings.qdrant_collection)
    if exists:
        return

    await client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(
            size=768,  # nomic-embed-text-v1.5 dim
            distance=Distance.COSINE,
        ),
        sparse_vectors_config={
            "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
        },
    )
    logger.info("Qdrant collection created", name=settings.qdrant_collection)


def _load_documents(file_path: Path, filename: str) -> list[Document]:
    """Load file thành list[Document] theo extension."""
    suffix = file_path.suffix.lower()
    match suffix:
        case ".pdf":
            loader = PyPDFLoader(str(file_path))
        case ".docx":
            loader = Docx2txtLoader(str(file_path))
        case ".txt" | ".md":
            loader = TextLoader(str(file_path), encoding="utf-8")
        case _:
            raise ValueError(f"Unsupported file type: {suffix}")

    docs = loader.load()
    # Gắn filename vào metadata
    for doc in docs:
        doc.metadata["source_filename"] = filename
    return docs


def _chunk_documents(docs: list[Document]) -> list[Document]:
    """Chunk documents với RecursiveCharacterTextSplitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
    )
    chunks = splitter.split_documents(docs)
    # Thêm chunk_index vào metadata
    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = idx
        chunk.metadata["ingestion_timestamp"] = datetime.now(UTC).isoformat()
    return chunks


async def ingest_file(
    file_bytes: bytes,
    filename: str,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict:
    """
    Ingest một file: parse → chunk → embed → upsert vào Qdrant.

    Args:
        file_bytes: Raw bytes của file upload
        filename: Tên file gốc (dùng để lưu metadata)
        qdrant_client: AsyncQdrantClient (optional, tạo mới nếu None)

    Returns:
        dict với keys: filename, chunks_count, doc_id
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file: {filename}. Supported: {SUPPORTED_EXTENSIONS}")

    # Tạo client nếu không truyền vào
    if qdrant_client is None:
        qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)

    await ensure_collection(qdrant_client)

    # Lưu tạm file ra disk để loader đọc
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        docs = _load_documents(tmp_path, filename)
        chunks = _chunk_documents(docs)
        logger.info("Chunking done", filename=filename, chunks=len(chunks))

        # Embed theo batch (tránh request quá lớn)
        batch_size = 32
        all_vectors: list[list[float]] = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.page_content for c in batch]
            vectors = await embed_client.embed(texts)
            all_vectors.extend(vectors)

        # Tạo unique doc_id dựa trên nội dung file
        doc_id = hashlib.md5(file_bytes).hexdigest()[:12]

        # Upsert points vào Qdrant
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "text": chunk.page_content,
                    "doc_id": doc_id,
                    **chunk.metadata,
                },
            )
            for chunk, vec in zip(chunks, all_vectors, strict=True)
        ]

        await qdrant_client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
        )
        logger.info("Upsert done", filename=filename, points=len(points))

        return {"filename": filename, "chunks_count": len(chunks), "doc_id": doc_id}

    finally:
        tmp_path.unlink(missing_ok=True)
