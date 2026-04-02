# Bài 05 — Hybrid Retriever

**Code**: [`backend/src/rag/retriever.py`](../../backend/src/rag/retriever.py)

---

## Vấn đề cần giải quyết

Khi user hỏi, ta cần tìm các chunks liên quan trong Qdrant.  
Có 2 cách tìm kiếm, mỗi cách có điểm mạnh riêng:

| | Dense (semantic) | Sparse (keyword) |
|---|---|---|
| Cách hoạt động | So sánh vectors cosine | Đếm từ khớp (BM25) |
| Tốt cho | Paraphrase, đồng nghĩa | Tên riêng, số liệu, exact match |
| Ví dụ query | "làm thế nào RAG hoạt động" | "LangGraph v0.3 release notes" |

**Hybrid search** = kết hợp cả hai → kết quả tốt hơn mỗi cách riêng lẻ.

---

## Bước 1: Dense vector (semantic)

```python
# retriever.py:77
dense_vec = await embed_client.embed_one(query)
# → list[float] 768-dim, dùng model nomic-embed-text-v1.5
```

---

## Bước 2: Sparse vector (keyword)

```python
# retriever.py:32
def _text_to_sparse(text: str) -> SparseVector:
    tokens = re.findall(r"\w+", text.lower())  # tokenize
    tf = Counter(tokens)                        # đếm term frequency

    indices = [hash(tok) % 30000 for tok in tf]  # hash token → index [0, 30000)
    values  = [float(v) for v in tf.values()]     # TF score
    return SparseVector(indices=indices, values=values)
```

**Ví dụ**: query `"RAG pipeline"` → `{indices: [hash("rag")%30000, hash("pipeline")%30000], values: [1.0, 1.0]}`

> **Note**: Production nên dùng `fastembed SparseTextEmbedding` (BM25 chuẩn hơn). Implementation đơn giản này đủ để demo hybrid search hoạt động.

---

## Bước 3: Qdrant Query API với RRF Fusion

```python
# retriever.py:82
results = await self._client.query_points(
    collection_name=settings.qdrant_collection,

    # retriever.py:85-97 — 2 prefetch queries chạy song song
    prefetch=[
        Prefetch(
            query=dense_vec,   # raw list[float] — qdrant-client ≥1.17 API
            using="",          # tên vector field ("" = default unnamed vector)
            limit=k * 3,       # lấy top 15 (k=5 → 15) để có pool lớn cho fusion
        ),
        Prefetch(
            query=NamedSparseVector(name="sparse", vector=sparse_vec),  # sparse search
            limit=k * 3,
        ),
    ],

    # retriever.py:98 — merge 2 lists bằng RRF
    query=Query(fusion=FusionQuery(fusion="rrf")),
    limit=k,  # trả về top 5 sau fusion
    with_payload=True,
)
```

---

## Reciprocal Rank Fusion (RRF) là gì?

Thuật toán merge nhiều ranked lists không cần normalize scores:

```
Dense results:   [doc_A rank=1, doc_C rank=2, doc_B rank=3, ...]
Sparse results:  [doc_B rank=1, doc_A rank=2, doc_D rank=3, ...]

RRF score = Σ 1/(rank + 60)

doc_A: 1/(1+60) + 1/(2+60) = 0.0164 + 0.0161 = 0.0325  ← winner
doc_B: 1/(3+60) + 1/(1+60) = 0.0159 + 0.0164 = 0.0323
doc_C: 1/(2+60) + 0         = 0.0161
doc_D: 0         + 1/(3+60) = 0.0159
```

Constant `60` giảm ảnh hưởng của rank rất cao (top 1 không quá dominant).

---

## Convert kết quả → LangChain Documents

```python
# retriever.py:106-112
docs = [
    Document(
        page_content=pt.payload.get("text", ""),   # text chunk gốc
        metadata={k: v for k, v in pt.payload.items() if k != "text"},
        # metadata: source_filename, chunk_index, doc_id, ingestion_timestamp
    )
    for pt in results.points
]
```

---

## Thử ngay

```bash
cd backend
python3 -c "
import asyncio
from src.rag.retriever import HybridRetriever

async def test():
    r = HybridRetriever()
    docs = await r.retrieve('What is RAG?', top_k=3)
    for i, d in enumerate(docs):
        print(f'--- Result {i+1} ---')
        print(f'File: {d.metadata.get(\"source_filename\")}')
        print(f'Text: {d.page_content[:150]}...')
        print()

asyncio.run(test())
"
# Cần đã seed documents trước: bash scripts/seed-documents.sh
```

---

## ⚠️ Lỗi thực tế gặp phải

### `NamedVector` và `NamedSparseVector` bị reject trong `Prefetch.query` (qdrant-client ≥ 1.17)

**Triệu chứng**:
- `curl -N -X POST http://localhost:8000/v1/chat -d '{"message":"...", "stream":true}'`
- → `curl: (18) transfer closed with outstanding read data remaining`
- API logs: `ValidationError: 23 validation errors for Prefetch` với message như:
  `Input should be a valid dictionary or instance of OrderByQuery [input_value=NamedVector(...)]`

**Root cause**: qdrant-client 1.17.1 đổi type signature của `Prefetch.query`.  
Trước đây `Prefetch.query` nhận `NamedVector`/`NamedSparseVector` để chỉ định cả vector lẫn tên field.  
Từ 1.17+, `Prefetch` tách riêng thành 2 fields:
- `query`: raw `list[float]` hoặc `SparseVector` (không bọc trong Named*)
- `using`: `str` — tên của vector field trong collection

**Fix** ([`retriever.py:84`](../../backend/src/rag/retriever.py#L84)):
```python
# ❌ Cũ — qdrant-client < 1.17:
Prefetch(
    query=NamedVector(name="", vector=dense_vec),      # bị reject
    limit=k * 3,
),
Prefetch(
    query=NamedSparseVector(name="sparse", vector=sparse_vec),  # bị reject
    limit=k * 3,
),

# ✅ Mới — qdrant-client ≥ 1.17:
Prefetch(
    query=dense_vec,   # raw list[float]
    using="",          # "" = default unnamed vector field
    limit=k * 3,
),
Prefetch(
    query=sparse_vec,  # SparseVector object trực tiếp
    using="sparse",    # tên vector field sparse
    limit=k * 3,
),
```

**Tại sao curl báo lỗi 18 thay vì 500?**  
SSE stream đã bắt đầu gửi (`HTTP 200 + headers`), nhưng khi exception xảy ra bên trong async generator,  
FastAPI đóng connection giữa chừng → curl thấy "transfer closed with outstanding read data remaining".  
Không phải lỗi curl hay buffering — là unhandled exception trong streaming generator.

### `Query(fusion=...)` TypeError: Cannot instantiate typing.Union (qdrant-client ≥ 1.17)

**Triệu chứng**:
```
TypeError: Cannot instantiate typing.Union
  File ".../retriever.py", line 95, in retrieve
    query=Query(fusion=FusionQuery(fusion="rrf")),
```

**Root cause**: `Query` trong qdrant-client 1.17+ là **type alias** (`Union[NearestQuery, RecommendQuery, ..., FusionQuery, ...]`),  
không phải class — không thể gọi `Query(...)`.

**Fix** ([`retriever.py:94`](../../backend/src/rag/retriever.py#L94)):
```python
# ❌ Cũ:
query=Query(fusion=FusionQuery(fusion="rrf")),

# ✅ Mới — dùng FusionQuery trực tiếp:
query=FusionQuery(fusion="rrf"),
```

### Collection không tồn tại khi chưa upload documents

**Triệu chứng**:
```
qdrant_client.http.exceptions.UnexpectedResponse: 404 (Not Found)
{"status":{"error":"Not found: Collection `nexus_docs` doesn't exist!"}}
```

**Root cause**: Collection chỉ được tạo khi document đầu tiên được ingest (trong `ingestion.py`).  
Nếu chạy RAG query trước khi upload document, collection chưa tồn tại.

**Fix**: Upload ít nhất 1 document trước khi dùng RAG:
```bash
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@your-document.pdf"
```

---

**Bài trước**: [04 — RAG Ingestion](./04-rag-ingestion.md)
**Bài tiếp theo**: [06 — RAG Chain (LCEL)](./06-rag-chain.md)
