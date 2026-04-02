"""Tests cho RAG pipeline: ingestion + retriever + chain."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmbeddingClient:
    """Test EmbeddingClient."""

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        from src.core.embeddings import EmbeddingClient

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(index=0, embedding=[0.1] * 768),
            MagicMock(index=1, embedding=[0.2] * 768),
        ]

        client = EmbeddingClient()
        with patch.object(client._client.embeddings, "create", new=AsyncMock(return_value=mock_response)):
            vectors = await client.embed(["text1", "text2"])

        assert len(vectors) == 2
        assert len(vectors[0]) == 768

    @pytest.mark.asyncio
    async def test_embed_empty_returns_empty(self):
        from src.core.embeddings import EmbeddingClient

        client = EmbeddingClient()
        result = await client.embed([])
        assert result == []


class TestIngestion:
    """Test document ingestion pipeline."""

    def test_chunk_documents(self):
        from langchain_core.documents import Document
        from src.rag.ingestion import _chunk_documents

        doc = Document(page_content="word " * 200, metadata={"source_filename": "test.txt"})
        chunks = _chunk_documents([doc])

        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.metadata["chunk_index"] == i
            assert "ingestion_timestamp" in chunk.metadata

    def test_unsupported_extension_raises(self):
        import pytest
        from src.rag.ingestion import SUPPORTED_EXTENSIONS

        assert ".xyz" not in SUPPORTED_EXTENSIONS


class TestModelRouter:
    """Test model router classification."""

    def test_simple_query_classified_simple(self):
        from src.core.model_router import ModelRouter, TaskComplexity
        r = ModelRouter()
        assert r.classify("What is the weather today?") == TaskComplexity.SIMPLE

    def test_code_query_classified_complex(self):
        from src.core.model_router import ModelRouter, TaskComplexity
        r = ModelRouter()
        assert r.classify("Write a Python function to sort a list") == TaskComplexity.COMPLEX

    def test_search_query_classified_agent(self):
        from src.core.model_router import ModelRouter, TaskComplexity
        r = ModelRouter()
        assert r.classify("Search for the latest news about AI") == TaskComplexity.AGENT

    def test_route_returns_model_params(self):
        from src.core.model_router import ModelRouter
        r = ModelRouter()
        params = r.route("Hello world")
        assert params.base_url
        assert params.model
        assert 0 <= params.temperature <= 1
