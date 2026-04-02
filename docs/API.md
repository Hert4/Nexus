# API Reference — Nexus AI

> Route handlers: `backend/src/api/routes/`
> Request/Response models dùng Pydantic v2.

Base URL: `http://localhost:8000`

---

## GET /health

**Handler**: [`api/routes/health.py:62`](../backend/src/api/routes/health.py#L62)

Ping tất cả downstream services. Trả về `200` kể cả khi `status: "degraded"` (để K8s không restart liên tục).

Check logic:
- llama-server: [`health.py:29`](../backend/src/api/routes/health.py#L29) — GET `{base_url}/health`
- Qdrant: [`health.py:43`](../backend/src/api/routes/health.py#L43) — GET `{qdrant_url}/healthz`

**Response:**
```json
{
  "status": "ok",
  "services": {
    "llamacpp_chat": {"status": "ok", "detail": ""},
    "llamacpp_embed": {"status": "ok", "detail": ""},
    "qdrant": {"status": "ok", "detail": ""}
  }
}
```

---

## POST /v1/chat

**Handler**: [`api/routes/chat.py:53`](../backend/src/api/routes/chat.py#L53)

**Request model** ([`chat.py:32`](../backend/src/api/routes/chat.py#L32)):
```json
{
  "message": "string (required)",
  "stream": true,
  "use_rag": true,
  "system": "You are a helpful assistant."
}
```

### Mode: `use_rag=true, stream=true` (default)

Flow: `chat.py:66` → `RAGChain.stream()` ([`chain.py:105`](../backend/src/rag/chain.py#L105)) → `_sse_generator()` ([`chat.py:44`](../backend/src/api/routes/chat.py#L44))

Response: `text/event-stream`
```
data: {"chunk": "Based"}
data: {"chunk": " on"}
data: {"chunk": " the context..."}
data: [DONE]
```

### Mode: `use_rag=true, stream=false`

Flow: `chat.py:70` → `RAGChain.retrieve_with_answer()` ([`chain.py:111`](../backend/src/rag/chain.py#L111))

Response:
```json
{
  "answer": "Nexus AI is a local RAG platform...",
  "sources": [
    {
      "filename": "ARCHITECTURE.md",
      "page": "",
      "chunk_index": 3,
      "snippet": "first 200 chars of the chunk..."
    }
  ]
}
```

### Mode: `use_rag=false`

Flow: `chat.py:75` → `ModelRouter.route()` ([`model_router.py:64`](../backend/src/core/model_router.py#L64)) → `LLMClient.stream/chat()` ([`llm.py:48`](../backend/src/core/llm.py#L48))

**curl examples:**
```bash
# RAG + streaming
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain the architecture", "stream": true}' \
  --no-buffer

# Plain chat, non-streaming
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "stream": false, "use_rag": false}'
```

---

## POST /v1/documents

**Handler**: [`api/routes/documents.py:42`](../backend/src/api/routes/documents.py#L42)

Upload và ingest file vào Qdrant. Triggers pipeline tại [`rag/ingestion.py:100`](../backend/src/rag/ingestion.py#L100).

**Request**: `multipart/form-data`
- `file`: attachment (PDF, TXT, MD, DOCX — max 50MB, check tại [`documents.py:52`](../backend/src/api/routes/documents.py#L52))

**Response 201:**
```json
{
  "filename": "report.pdf",
  "chunks_count": 42,
  "doc_id": "a1b2c3d4e5f6",
  "message": "Successfully ingested 42 chunks"
}
```

`doc_id` = MD5 hash của file bytes ([`ingestion.py:152`](../backend/src/rag/ingestion.py#L152)) — dùng để xóa sau.

**Errors:**
- `415` — extension không trong `SUPPORTED_EXTENSIONS` ([`ingestion.py:16`](../backend/src/rag/ingestion.py#L16)): `{".pdf", ".txt", ".md", ".docx"}`
- `413` — file > 50MB ([`documents.py:52`](../backend/src/api/routes/documents.py#L52))

```bash
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@/path/to/report.pdf"
```

---

## GET /v1/documents

**Handler**: [`api/routes/documents.py:82`](../backend/src/api/routes/documents.py#L82)

List tất cả documents — scroll Qdrant payloads, group theo `doc_id`.

**Response:**
```json
[
  {"doc_id": "a1b2c3d4e5f6", "filename": "report.pdf", "chunks_count": 42},
  {"doc_id": "b2c3d4e5f6a1", "filename": "notes.md", "chunks_count": 8}
]
```

---

## DELETE /v1/documents/{doc_id}

**Handler**: [`api/routes/documents.py:112`](../backend/src/api/routes/documents.py#L112)

Xóa tất cả Qdrant points có `payload.doc_id == doc_id` bằng `Filter`:
```python
# documents.py:120
await client.delete(
    collection_name=settings.qdrant_collection,
    points_selector=Filter(
        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
    ),
)
```

**Response**: `204 No Content`

```bash
curl -X DELETE http://localhost:8000/v1/documents/a1b2c3d4e5f6
```

---

## GET /metrics

Prometheus scrape endpoint — setup tại [`observability/metrics.py:50`](../backend/src/observability/metrics.py#L50).

**Custom metrics** ([`metrics.py:21-38`](../backend/src/observability/metrics.py#L21)):

| Metric | Type | Labels |
|--------|------|--------|
| `nexus_llm_latency_seconds` | Histogram | `model` |
| `nexus_rag_retrieval_latency_seconds` | Histogram | — |
| `nexus_documents_ingested_total` | Counter | — |
| `nexus_chunks_ingested_total` | Counter | — |
| `nexus_active_requests` | Gauge | — |

**Auto-instrumented** (tất cả routes): request count, latency p50/p95/p99.

```bash
curl http://localhost:8000/metrics | grep nexus_
```
