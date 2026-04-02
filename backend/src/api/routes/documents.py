"""
api/routes/documents.py — Document upload và quản lý.

POST /v1/documents  — Upload file, trigger ingestion pipeline
GET  /v1/documents  — List các document đã ingest (từ Qdrant collection info)
DELETE /v1/documents/{doc_id} — Xóa document theo doc_id

File types hỗ trợ: PDF, TXT, MD, DOCX
"""

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from src.config import settings
from src.rag.ingestion import SUPPORTED_EXTENSIONS, ingest_file

logger = structlog.get_logger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


class IngestResponse(BaseModel):
    filename: str
    chunks_count: int
    doc_id: str
    message: str


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunks_count: int


@router.post(
    "/documents",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload và ingest document vào vector store.

    - Đọc file bytes
    - Validate extension và size
    - Chạy ingestion pipeline (parse → chunk → embed → upsert)
    - Trả về thông tin kết quả
    """
    from pathlib import Path

    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {MAX_FILE_SIZE // 1024 // 1024}MB",
        )

    logger.info("Document upload", filename=file.filename, size=len(file_bytes))

    try:
        result = await ingest_file(file_bytes, file.filename or "unknown")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Ingestion failed", filename=file.filename, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {e}",
        )

    return IngestResponse(
        **result,
        message=f"Successfully ingested {result['chunks_count']} chunks",
    )


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents():
    """
    List tất cả documents trong Qdrant collection.
    Scroll qua payloads và group theo doc_id.
    """
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        exists = await client.collection_exists(settings.qdrant_collection)
        if not exists:
            return []

        # Scroll tất cả points để lấy metadata (giới hạn 1000 để demo)
        results, _ = await client.scroll(
            collection_name=settings.qdrant_collection,
            limit=1000,
            with_payload=["doc_id", "source_filename"],
            with_vectors=False,
        )

        # Group theo doc_id
        docs: dict[str, DocumentInfo] = {}
        for pt in results:
            doc_id = pt.payload.get("doc_id", "unknown")
            filename = pt.payload.get("source_filename", "unknown")
            if doc_id not in docs:
                docs[doc_id] = DocumentInfo(doc_id=doc_id, filename=filename, chunks_count=0)
            docs[doc_id].chunks_count += 1

        return list(docs.values())
    except Exception as e:
        logger.error("List documents failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str):
    """Xóa tất cả chunks thuộc về doc_id."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        logger.info("Document deleted", doc_id=doc_id)
    except Exception as e:
        logger.error("Delete failed", doc_id=doc_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
