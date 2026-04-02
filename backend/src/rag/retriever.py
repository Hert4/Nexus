"""
rag/retriever.py — Hybrid search retriever (dense + sparse BM25) trên Qdrant.

Dense search:  cosine similarity trên 768-dim nomic-embed vectors
Sparse search: BM25 keyword matching qua Qdrant sparse vectors
Fusion:        Reciprocal Rank Fusion (RRF) — Qdrant native

Usage:
    from src.rag.retriever import HybridRetriever
    retriever = HybridRetriever()
    docs = await retriever.retrieve("What is RAG?", top_k=5)
"""

import structlog
from langchain_core.documents import Document
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FusionQuery,
    Prefetch,
    SparseVector,
)

from src.config import settings
from src.core.embeddings import embed_client

logger = structlog.get_logger(__name__)


def _text_to_sparse(text: str) -> SparseVector:
    """
    Tạo sparse vector BM25-style từ text bằng cách tokenize và đếm TF.
    Trong production nên dùng fastembed SparseTextEmbedding,
    nhưng để đơn giản ta dùng simple term frequency.
    """
    import re
    from collections import Counter

    tokens = re.findall(r"\w+", text.lower())
    tf = Counter(tokens)
    # Hash token thành index trong khoảng [0, 30000)
    indices = [hash(tok) % 30000 for tok in tf]
    values = [float(v) for v in tf.values()]
    return SparseVector(indices=indices, values=values)


class HybridRetriever:
    """
    Hybrid retriever kết hợp dense và sparse search qua Qdrant Query API.
    Dùng Reciprocal Rank Fusion để merge kết quả.
    """

    def __init__(self, qdrant_client: AsyncQdrantClient | None = None) -> None:
        self._client = qdrant_client or AsyncQdrantClient(url=settings.qdrant_url)

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[Document]:
        """
        Hybrid search cho query string.

        Args:
            query: User query
            top_k: Số kết quả trả về (default từ settings)

        Returns:
            List[Document] với page_content và metadata
        """
        k = top_k or settings.retriever_top_k
        logger.debug("Retrieval request", query=query[:80], top_k=k)

        # 1. Tạo dense vector cho query
        dense_vec = await embed_client.embed_one(query)

        # 2. Tạo sparse vector
        sparse_vec = _text_to_sparse(query)

        # 3. Hybrid query với Qdrant Prefetch + Fusion
        results = await self._client.query_points(
            collection_name=settings.qdrant_collection,
            prefetch=[
                Prefetch(
                    query=dense_vec,  # raw list[float] — qdrant-client 1.17+ không nhận NamedVector
                    using="",  # "" = default unnamed vector
                    limit=k * 3,
                ),
                Prefetch(
                    query=sparse_vec,  # SparseVector — qdrant-client 1.17+ API
                    using="sparse",  # tên vector field sparse trong collection
                    limit=k * 3,
                ),
            ],
            query=FusionQuery(
                fusion="rrf"
            ),  # FusionQuery trực tiếp — Query là Union alias, không instantiate được
            limit=k,
            with_payload=True,
        )

        docs = [
            Document(
                page_content=pt.payload.get("text", ""),
                metadata={k: v for k, v in pt.payload.items() if k != "text"},
            )
            for pt in results.points
        ]
        logger.debug("Retrieval done", count=len(docs))
        return docs


# Singleton
hybrid_retriever = HybridRetriever()
