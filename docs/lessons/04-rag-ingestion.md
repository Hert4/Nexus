# Bài 04 — RAG Ingestion

**Code**: [`backend/src/rag/ingestion.py`](../../backend/src/rag/ingestion.py)

---

## Vấn đề cần giải quyết

Khi user upload file PDF/DOCX/TXT, ta cần:
1. Parse text từ file
2. Chia thành chunks nhỏ (model có context limit)
3. Embed từng chunk → vector 768-dim
4. Lưu vectors + text vào Qdrant để search sau

---

## Flow tổng quan

```
ingest_file(bytes, filename)          ← ingestion.py:100
    │
    ├─► ensure_collection()           ← ingestion.py:46  — tạo Qdrant collection nếu chưa có
    ├─► _load_documents()             ← ingestion.py:65  — parse file → list[Document]
    ├─► _chunk_documents()            ← ingestion.py:85  — split → chunks 512 chars
    ├─► embed_client.embed() x batch  ← ingestion.py:138 — 32 chunks/request
    └─► qdrant_client.upsert()        ← ingestion.py:149 — lưu vào Qdrant
```

---

## Bước 1: Tạo Qdrant Collection

```python
# ingestion.py:46
async def ensure_collection(client: AsyncQdrantClient) -> None:
    exists = await client.collection_exists(settings.qdrant_collection)
    if exists:
        return   # idempotent — gọi nhiều lần không sao

    await client.create_collection(
        collection_name=settings.qdrant_collection,
        # ingestion.py:54 — dense vector config
        vectors_config=VectorParams(
            size=768,              # phải khớp EMBEDDING_DIM = 768
            distance=Distance.COSINE,
        ),
        # ingestion.py:59 — sparse vector cho BM25 hybrid search
        sparse_vectors_config={
            "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
        },
    )
```

Collection chứa **cả** dense và sparse vectors — cần thiết cho hybrid search ở bài 05.

---

## Bước 2: Parse file

```python
# ingestion.py:65
def _load_documents(file_path: Path, filename: str) -> list[Document]:
    match suffix:
        case ".pdf":
            loader = PyPDFLoader(str(file_path))       # pypdf
        case ".docx":
            loader = Docx2txtLoader(str(file_path))    # docx2txt
        case ".txt" | ".md":
            loader = TextLoader(str(file_path), encoding="utf-8")

    docs = loader.load()
    # Gắn filename vào metadata của mỗi Document
    for doc in docs:
        doc.metadata["source_filename"] = filename
    return docs
```

`Document` là LangChain object: `page_content: str` + `metadata: dict`.

---

## Bước 3: Chunking

```python
# ingestion.py:85
def _chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,    # settings.chunk_size — max ký tự/chunk
        chunk_overlap=50,  # settings.chunk_overlap — overlap giữa 2 chunk liền kề
    )
    chunks = splitter.split_documents(docs)

    # ingestion.py:92 — thêm metadata
    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = idx
        chunk.metadata["ingestion_timestamp"] = datetime.now(UTC).isoformat()
    return chunks
```

**Tại sao `overlap=50`?**  
Nếu 1 câu bị cắt đôi giữa chunk N và N+1, overlap đảm bảo 50 ký tự cuối của N lặp lại ở đầu N+1 — không mất context.

**`RecursiveCharacterTextSplitter`** ưu tiên split tại `\n\n` → `\n` → ` ` → ký tự, giữ semantic structure của văn bản.

---

## Bước 4: Batch Embed

```python
# ingestion.py:138
batch_size = 32  # 32 chunks/request → tránh request quá lớn

for i in range(0, len(chunks), batch_size):
    batch = chunks[i : i + batch_size]          # ingestion.py:140
    texts = [c.page_content for c in batch]
    vectors = await embed_client.embed(texts)   # → list[list[float]]
    all_vectors.extend(vectors)
```

---

## Bước 5: Tạo doc_id & Upsert

```python
# ingestion.py:147
doc_id = hashlib.md5(file_bytes).hexdigest()[:12]
# Hash nội dung file → ID duy nhất, dùng để DELETE sau
# e.g.: "a1b2c3d4e5f6"
```

```python
# ingestion.py:149
points = [
    PointStruct(
        id=str(uuid.uuid4()),   # mỗi chunk có UUID riêng
        vector=vec,             # 768-dim float list
        payload={
            "text": chunk.page_content,   # text gốc — trả về khi retrieve
            "doc_id": doc_id,             # để group/delete theo document
            **chunk.metadata,             # source_filename, chunk_index, ...
        },
    )
    for chunk, vec in zip(chunks, all_vectors, strict=True)
]

await qdrant_client.upsert(
    collection_name=settings.qdrant_collection,
    points=points,
)
```

---

## Thử ngay

```bash
# Upload file thật
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@docs/ARCHITECTURE.md"

# Xem kết quả
curl http://localhost:8000/v1/documents | python3 -m json.tool
# → [{"doc_id": "...", "filename": "ARCHITECTURE.md", "chunks_count": 18}]
```

Hoặc test trực tiếp bằng Python:
```bash
cd backend
python3 -c "
import asyncio
from src.rag.ingestion import ingest_file

async def test():
    with open('../docs/ARCHITECTURE.md', 'rb') as f:
        result = await ingest_file(f.read(), 'ARCHITECTURE.md')
    print(result)

asyncio.run(test())
"
```

---

**Bài trước**: [03 — Embeddings](./03-embeddings.md)
**Bài tiếp theo**: [05 — Hybrid Retriever](./05-hybrid-retriever.md)
