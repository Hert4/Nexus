# ARCHITECTURE — Nexus AI (Phase 1)

> **Quy tắc đọc tài liệu này**: Mỗi concept đều có link trực tiếp đến file và dòng code thực tế.
> Format: `backend/src/path/file.py:LINE` — bấm vào để xem đúng chỗ trong code.

---

## Luồng dữ liệu tổng quan

```
User
 │
 ▼
POST /v1/chat                          ← api/routes/chat.py:53
 │
 ├─[use_rag=true]──► RAGChain          ← rag/chain.py:67
 │                       │
 │                       ├─► HybridRetriever.retrieve()   ← rag/retriever.py:58
 │                       │       │
 │                       │       ├─► EmbeddingClient.embed_one()  ← core/embeddings.py:71
 │                       │       │       └─► llama-server :8081/v1/embeddings
 │                       │       │
 │                       │       └─► Qdrant hybrid query (RRF)   ← rag/retriever.py:82-104
 │                       │               └─► Qdrant :6333
 │                       │
 │                       └─► LLMClient.stream()           ← core/llm.py:75
 │                               └─► llama-server :8080/v1/chat/completions
 │
 └─[use_rag=false]─► LLMClient (direct)  ← core/llm.py:27
                         └─► llama-server :8080/v1/chat/completions
```

---

## 1. Config — `backend/src/config.py`

**`Settings` class** ([`config.py:12`](../backend/src/config.py#L12)) dùng `pydantic-settings` để load tất cả config từ env vars (file `.env`).

```python
# config.py:20 — URL llama-server chat
llamacpp_chat_url: str = "http://llamacpp-chat:8080/v1"

# config.py:28 — URL Qdrant
qdrant_url: str = "http://qdrant:6333"

# config.py:42 — chunk size cho RAG ingestion
chunk_size: int = 512
```

**Tại sao dùng pydantic-settings?**
- Type-safe: nếu thiếu env var bắt buộc → crash sớm khi start, không crash lúc runtime
- Validator tự động: [`config.py:46-50`](../backend/src/config.py#L46) — `parse_cors_origins` chuyển string `"http://a,http://b"` thành `list`

**Import ở bất kỳ module nào:**
```python
from src.config import settings
print(settings.llamacpp_chat_url)  # → "http://host.docker.internal:8080/v1"
```

---

## 2. LLM Client — `backend/src/core/llm.py`

**`LLMClient` class** ([`llm.py:27`](../backend/src/core/llm.py#L27)) — wrapper duy nhất cho tất cả LLM calls trong project.

### Tại sao dùng `openai` SDK thay vì `httpx` trực tiếp?

llama-server expose API giống hệt OpenAI format. Bằng cách dùng `openai.AsyncOpenAI` với `base_url` khác, ta được:
- Streaming built-in
- Retry logic
- Type-safe response objects
- Dễ swap sang OpenAI thật sau này chỉ cần đổi `base_url`

### Khởi tạo client ([`llm.py:42-46`](../backend/src/core/llm.py#L42)):

```python
self._client = AsyncOpenAI(
    base_url=self._base_url,    # "http://host.docker.internal:8080/v1"
    api_key="llama-cpp",        # llama-server không cần key, nhưng SDK require non-empty
    timeout=120.0,
)
```

### Non-streaming ([`llm.py:48`](../backend/src/core/llm.py#L48)):
```python
response = await self._client.chat.completions.create(
    model=self._model,
    messages=[...],
    stream=False,
)
return response.choices[0].message.content
```

### Streaming ([`llm.py:75`](../backend/src/core/llm.py#L75)):
```python
stream = await self._client.chat.completions.create(..., stream=True)
async for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        yield delta   # yield từng token
```

> **Lưu ý**: `stream=True` trả về `AsyncStream[ChatCompletionChunk]` — phải dùng `async for`.

---

## 3. Embedding Client — `backend/src/core/embeddings.py`

**`EmbeddingClient`** ([`embeddings.py:25`](../backend/src/core/embeddings.py#L25)) — gọi llama-server embed (port 8081) lấy 768-dim vectors.

**`EMBEDDING_DIM = 768`** ([`embeddings.py:22`](../backend/src/core/embeddings.py#L22)) — kích thước vector của `nomic-embed-text-v1.5`. Phải khớp với Qdrant collection config.

### Batch embed ([`embeddings.py:44`](../backend/src/core/embeddings.py#L44)):
```python
response = await self._client.embeddings.create(
    model=self._model,
    input=texts,           # list[str] — nhiều text cùng lúc
    encoding_format="float",
)
# Sắp xếp theo index vì API không đảm bảo thứ tự
vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
```

### LangChain adapter — `NexusEmbeddings` ([`embeddings.py:87`](../backend/src/core/embeddings.py#L87)):

LangChain `Retriever` yêu cầu object implement interface `Embeddings`. `NexusEmbeddings` wrap `EmbeddingClient` để tương thích:

```python
class NexusEmbeddings(Embeddings):          # embeddings.py:87
    def embed_documents(self, texts):       # sync wrapper cho LangChain
        return asyncio.get_event_loop().run_until_complete(...)

    async def aembed_query(self, text):     # async — preferred trong FastAPI
        return await self._client.embed_one(text)
```

---

## 4. Model Router — `backend/src/core/model_router.py`

**`ModelRouter`** ([`model_router.py`](../backend/src/core/model_router.py)) — phân loại complexity của prompt để điều chỉnh inference params.

Vì chỉ có 1 model, router không swap model mà thay đổi `temperature` + `max_tokens`:

| Complexity | Trigger keywords | temperature | max_tokens |
|-----------|-----------------|-------------|------------|
| `SIMPLE`  | (default)       | 0.7         | 1024       |
| `COMPLEX` | code, function, explain, analyze | 0.2 | 4096 |
| `AGENT`   | search, find, execute, calculate | 0.1 | 4096 |

```python
# model_router.py:64 — route() trả về ModelParams
params = router.route("Write a Python function to sort")
# → ModelParams(temperature=0.2, max_tokens=4096, ctx_hint="complex")
```

---

## 5. RAG Ingestion — `backend/src/rag/ingestion.py`

### Flow khi upload file ([`ingestion.py:100`](../backend/src/rag/ingestion.py#L100)):

```
ingest_file(bytes, filename)
    │
    ├─► ensure_collection()        ← ingestion.py:46 — tạo Qdrant collection nếu chưa có
    ├─► _load_documents()          ← ingestion.py:65 — parse file → list[Document]
    ├─► _chunk_documents()         ← ingestion.py:85 — split thành chunks 512 chars
    ├─► embed_client.embed()       ← core/embeddings.py:44 — batch embed, 32 chunks/batch
    └─► qdrant_client.upsert()     — upsert vectors vào Qdrant
```

### Chunking strategy ([`ingestion.py:85`](../backend/src/rag/ingestion.py#L85)):
```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,    # từ settings.chunk_size
    chunk_overlap=50,  # overlap để không mất context ở ranh giới chunk
)
```
`overlap=50`: 50 ký tự cuối chunk N sẽ lặp lại ở đầu chunk N+1 — tránh mất thông tin khi câu bị cắt đôi.

### Metadata mỗi chunk ([`ingestion.py:92-96`](../backend/src/rag/ingestion.py#L92)):
```python
chunk.metadata["chunk_index"] = idx               # vị trí trong document
chunk.metadata["ingestion_timestamp"] = "..."     # ISO datetime
chunk.metadata["source_filename"] = "report.pdf"  # từ _load_documents:72
```

### Batch embedding ([`ingestion.py:138`](../backend/src/rag/ingestion.py#L138)):
```python
batch_size = 32   # gửi 32 chunks/request để tránh request quá lớn
for i in range(0, len(chunks), batch_size):
    vectors = await embed_client.embed(texts[i:i+32])
```

### doc_id ([`ingestion.py:152`](../backend/src/rag/ingestion.py#L152)):
```python
doc_id = hashlib.md5(file_bytes).hexdigest()[:12]  # hash nội dung file
```
Dùng để xóa tất cả chunks của một document: `DELETE /v1/documents/{doc_id}`.

---

## 6. Hybrid Retriever — `backend/src/rag/retriever.py`

**Hybrid search** = dense (semantic) + sparse (keyword) + RRF fusion.

### Dense vector (semantic search):
- Query được embed thành 768-dim vector
- Qdrant tìm các vectors gần nhất bằng **cosine similarity**
- Tốt cho: tìm ý nghĩa, paraphrase, câu hỏi khác cách nói

### Sparse vector (keyword search) ([`retriever.py:32`](../backend/src/rag/retriever.py#L32)):
```python
def _text_to_sparse(text: str) -> SparseVector:
    tokens = re.findall(r"\w+", text.lower())
    tf = Counter(tokens)
    indices = [hash(tok) % 30000 for tok in tf]  # hash token → index
    values = [float(v) for v in tf.values()]      # term frequency
```
- Tốt cho: tìm exact keywords, tên riêng, số liệu

### Qdrant Query API với RRF ([`retriever.py:82`](../backend/src/rag/retriever.py#L82)):
```python
results = await self._client.query_points(
    collection_name=settings.qdrant_collection,
    prefetch=[
        Prefetch(query=dense_vec, limit=k*3),   # retriever.py:86 — lấy top 15 dense
        Prefetch(query=sparse_vec, limit=k*3),  # retriever.py:90 — lấy top 15 sparse
    ],
    query=Query(fusion=FusionQuery(fusion="rrf")),  # retriever.py:98 — merge bằng RRF
    limit=k,   # trả về top 5 sau fusion
)
```

**Reciprocal Rank Fusion (RRF)**: mỗi result được score = `1/(rank + 60)`, cộng scores từ cả 2 lists. Không cần normalize, hoạt động tốt ngay cả khi score scales khác nhau.

---

## 7. RAG Chain — `backend/src/rag/chain.py`

**LCEL chain** ([`chain.py:83`](../backend/src/rag/chain.py#L83)) — LangChain Expression Language:

```python
self._chain = (
    {
        "context": self._retrieve_and_format,  # chain.py:86 — async retrieve + format
        "question": RunnablePassthrough(),      # pass question thẳng
    }
    | RAG_PROMPT    # chain.py:50 — inject context + question vào prompt template
    | self._llm     # chain.py:73 — ChatOpenAI trỏ vào llama-server
    | StrOutputParser()  # extract .content từ AIMessage
)
```

### System prompt ([`chain.py:38`](../backend/src/rag/chain.py#L38)):
```
Rules:
1. Answer ONLY based on the context below. Do NOT use outside knowledge.
2. Always cite your sources using [filename, page X] format.
3. If the context doesn't contain enough information, say "I don't have enough information..."
```
→ Prompt buộc model cite source và không hallucinate.

### Format docs ([`chain.py:56`](../backend/src/rag/chain.py#L56)):
```python
def _format_docs(docs: list[Document]) -> str:
    # Mỗi chunk được format: [report.pdf, page 3]\nchunk content...
    # Ngăn cách bằng "---" để model biết ranh giới giữa các source
```

---

## 8. Chat Route — `backend/src/api/routes/chat.py`

### SSE Streaming ([`chat.py:44`](../backend/src/api/routes/chat.py#L44)):
```python
async def _sse_generator(gen):
    async for chunk in gen:
        data = json.dumps({"chunk": chunk})
        yield f"data: {data}\n\n".encode()  # SSE format: "data: ...\n\n"
    yield b"data: [DONE]\n\n"
```

Client đọc SSE:
```javascript
const source = new EventSource('/v1/chat');
source.onmessage = (e) => {
    if (e.data === '[DONE]') return;
    const { chunk } = JSON.parse(e.data);
    output += chunk;
}
```

### StreamingResponse ([`chat.py:66`](../backend/src/api/routes/chat.py#L66)):
```python
return StreamingResponse(
    _sse_generator(chain.stream(req.message)),
    media_type="text/event-stream",
    headers={"X-Accel-Buffering": "no"},  # tắt nginx buffer → client nhận ngay
)
```

---

## 9. Observability — `backend/src/observability/`

### Prometheus metrics ([`metrics.py:50`](../backend/src/observability/metrics.py#L50)):
```python
Instrumentator(...).instrument(app).expose(app, endpoint="/metrics")
```
→ Auto-instrument tất cả routes: request count, latency histogram.

### Custom metrics ([`metrics.py:21-38`](../backend/src/observability/metrics.py#L21)):
```python
llm_latency_seconds     # histogram: LLM response time
rag_retrieval_latency_seconds  # histogram: Qdrant query time
documents_ingested_total       # counter: số documents đã ingest
```

Scrape tại: `GET http://localhost:8000/metrics`

---

## File map — đọc theo thứ tự học

```
1. config.py:12          — Settings, env vars
2. core/llm.py:27        — LLMClient, openai SDK
3. core/embeddings.py:25 — EmbeddingClient, 768-dim vectors
4. core/model_router.py  — Complexity classification
5. rag/ingestion.py:100  — ingest_file(), chunking, batch embed
6. rag/retriever.py:49   — HybridRetriever, dense+sparse+RRF
7. rag/chain.py:67       — RAGChain, LCEL, prompt template
8. api/routes/chat.py:53 — SSE streaming endpoint
9. api/routes/documents.py — upload/list/delete
10. observability/metrics.py:50 — Prometheus
```
