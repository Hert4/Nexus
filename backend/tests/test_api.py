"""Integration tests cho FastAPI routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


class TestHealthRoute:
    def test_health_returns_200(self, client):
        mock_ok = AsyncMock(return_value={"status": "ok"})
        with (
            patch("src.api.routes.health._check_llamacpp", new=mock_ok),
            patch("src.api.routes.health._check_qdrant", new=mock_ok),
        ):
            response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "services" in data


class TestDocumentsRoute:
    def test_upload_unsupported_type_returns_415(self, client):
        response = client.post(
            "/v1/documents",
            files={"file": ("test.xyz", b"content", "application/octet-stream")},
        )
        assert response.status_code == 415

    def test_upload_pdf_triggers_ingestion(self, client):
        mock_result = {"filename": "test.pdf", "chunks_count": 5, "doc_id": "abc123"}
        with patch("src.api.routes.documents.ingest_file", new=AsyncMock(return_value=mock_result)):
            response = client.post(
                "/v1/documents",
                files={"file": ("test.pdf", b"%PDF-fake-content", "application/pdf")},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["chunks_count"] == 5
        assert data["doc_id"] == "abc123"

    def test_list_documents_empty(self, client):
        with patch("src.api.routes.documents.AsyncQdrantClient") as mock_qdrant:
            mock_instance = AsyncMock()
            mock_instance.collection_exists.return_value = False
            mock_qdrant.return_value = mock_instance
            response = client.get("/v1/documents")
        assert response.status_code == 200
        assert response.json() == []


class TestChatRoute:
    def test_chat_non_streaming_returns_answer(self, client):
        mock_result = {"answer": "RAG is Retrieval Augmented Generation", "sources": []}
        with patch("src.api.routes.chat.RAGChain") as MockChain:
            instance = MockChain.return_value
            instance.retrieve_with_answer = AsyncMock(return_value=mock_result)
            response = client.post(
                "/v1/chat",
                json={"message": "What is RAG?", "stream": False, "use_rag": True},
            )
        assert response.status_code == 200
        data = response.json()
        assert "RAG" in data["answer"]
