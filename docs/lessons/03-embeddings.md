# Bài 03 — Embeddings

**Code**: [`backend/src/core/embeddings.py`](../../backend/src/core/embeddings.py)

---

## Vấn đề cần giải quyết

Để search document theo nghĩa (không phải exact keyword), ta cần chuyển text thành **vector số** — một điểm trong không gian 768 chiều. Các text có nghĩa gần nhau → vectors gần nhau (cosine similarity cao).

```
"machine learning" → [0.12, -0.34, 0.87, ..., 0.05]  (768 số)
"deep learning"    → [0.14, -0.31, 0.89, ..., 0.03]  (gần nhau)
"cooking recipe"   → [-0.45, 0.22, -0.11, ..., 0.67] (xa nhau)
```

---

## Model: nomic-embed-text-v1.5

```python
# embeddings.py:22
EMBEDDING_DIM = 768  # nomic-embed-text-v1.5 output dimension
```

Chạy qua llama-server port **8081** với flag `--embedding --pooling mean`.  
`--pooling mean` = lấy trung bình tất cả token vectors → 1 vector đại diện cho cả câu.

---

## EmbeddingClient

```python
# embeddings.py:25
class EmbeddingClient:
```

Khởi tạo giống `LLMClient` nhưng trỏ sang embed server:

```python
# embeddings.py:35-40
self._client = AsyncOpenAI(
    base_url=settings.llamacpp_embed_url,  # "http://host.docker.internal:8081/v1"
    api_key="llama-cpp",
    timeout=60.0,   # embed nhanh hơn generate, timeout ngắn hơn
)
```

---

## Batch embed: `embed()`

```python
# embeddings.py:44
async def embed(self, texts: list[str]) -> list[list[float]]:
    response = await self._client.embeddings.create(
        model=self._model,
        input=texts,               # list[str] — nhiều text 1 lần
        encoding_format="float",   # trả về float list, không phải base64
    )
    # embeddings.py:55 — sắp xếp theo index
    vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    return vectors  # list[list[float]], shape: (N, 768)
```

**Tại sao sort theo `index`?** API không đảm bảo thứ tự response khớp thứ tự input — sort để đảm bảo `vectors[i]` tương ứng `texts[i]`.

---

## Single embed: `embed_one()`

```python
# embeddings.py:71
async def embed_one(self, text: str) -> list[float]:
    vectors = await self.embed([text])  # wrap trong list rồi unwrap
    return vectors[0]
```

Dùng khi embed query (1 string) trong retriever.

---

## NexusEmbeddings — LangChain Adapter

LangChain's `Retriever` và các tool khác yêu cầu object implement interface `Embeddings`. `NexusEmbeddings` wrap `EmbeddingClient` để tương thích:

```python
# embeddings.py:87
class NexusEmbeddings(Embeddings):  # inherit từ langchain_core.embeddings.Embeddings

    # embeddings.py:95-96 — sync version (LangChain legacy requirement)
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self._client.embed(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self._client.embed_one(text))

    # embeddings.py:105-109 — async version (preferred trong FastAPI)
    async def aembed_documents(self, texts):
        return await self._client.embed(texts)

    async def aembed_query(self, text):
        return await self._client.embed_one(text)
```

**Tại sao cần 2 phiên bản sync/async?**
- LangChain internal code gọi sync methods
- FastAPI context gọi async methods → không block event loop

---

## Singleton

```python
# embeddings.py:112
nexus_embeddings = NexusEmbeddings()
```

Dùng trong `rag/ingestion.py` và `rag/retriever.py`.

---

## Thử ngay

```bash
cd backend
python3 -c "
import asyncio
from src.core.embeddings import EmbeddingClient, EMBEDDING_DIM

async def test():
    client = EmbeddingClient(base_url='http://localhost:8081/v1')

    # Embed 2 câu
    vecs = await client.embed(['hello world', 'machine learning'])
    print(f'Shape: {len(vecs)} vectors x {len(vecs[0])} dims')
    # → Shape: 2 vectors x 768 dims

    # Kiểm tra cosine similarity (câu giống nhau → sim cao)
    import numpy as np
    v1 = np.array(vecs[0])
    v2 = np.array(vecs[1])
    sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    print(f'Similarity: {sim:.4f}')

asyncio.run(test())
"
```

---

**Bài trước**: [02 — LLM Client](./02-llm-client.md)
**Bài tiếp theo**: [04 — RAG Ingestion](./04-rag-ingestion.md)
