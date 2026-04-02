"""
core/embeddings.py — Embedding service via llama-server (nomic-embed-text).

llama-server chạy riêng với flag --embedding --pooling mean tại port 8081.
Expose endpoint /v1/embeddings theo chuẩn OpenAI.

nomic-embed-text-v1.5 cho ra vector 768 chiều.

Usage:
    from src.core.embeddings import EmbeddingClient
    client = EmbeddingClient()
    vectors = await client.embed(["text 1", "text 2"])
"""

import structlog
from openai import AsyncOpenAI, APIConnectionError

from src.config import settings

logger = structlog.get_logger(__name__)

EMBEDDING_DIM = 768  # nomic-embed-text-v1.5 output dimension


class EmbeddingClient:
    """
    Gọi llama-server embed endpoint để lấy dense vectors.
    Dùng openai SDK với base_url trỏ vào container llamacpp-embed:8081.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.llamacpp_embed_url
        self._model = model or settings.gguf_embed_model
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=settings.llm_api_key,
            timeout=60.0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed một danh sách text, trả về list[list[float]] (N x 768).

        Args:
            texts: Danh sách string cần embed (có thể là queries hoặc chunks)

        Returns:
            List vectors theo thứ tự input
        """
        if not texts:
            return []

        logger.debug("Embedding request", count=len(texts))
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                encoding_format="float",
            )
            vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            logger.debug("Embedding done", count=len(vectors), dim=len(vectors[0]) if vectors else 0)
            return vectors
        except APIConnectionError as e:
            logger.error("Embedding connection error", error=str(e))
            raise

    async def embed_one(self, text: str) -> list[float]:
        """Embed một string đơn, trả về vector."""
        vectors = await self.embed([text])
        return vectors[0]


# Singleton
embed_client = EmbeddingClient()


# ── LangChain-compatible wrapper ──────────────────────────────────────────────
# langchain-qdrant và RAG chain cần một object implement Embeddings interface.

from langchain_core.embeddings import Embeddings  # noqa: E402


class NexusEmbeddings(Embeddings):
    """
    LangChain Embeddings adapter dùng EmbeddingClient của Nexus.
    Được inject vào LangChain retriever và ingestion pipeline.
    """

    def __init__(self, client: EmbeddingClient | None = None) -> None:
        self._client = client or embed_client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Synchronous — LangChain yêu cầu. Dùng asyncio.run nếu cần."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._client.embed(texts))

    def embed_query(self, text: str) -> list[float]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._client.embed_one(text))

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._client.embed(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await self._client.embed_one(text)


nexus_embeddings = NexusEmbeddings()
