# Bài 07 — Chat API & SSE Streaming

**Code**: [`backend/src/api/routes/chat.py`](../../backend/src/api/routes/chat.py)

---

## Vấn đề cần giải quyết

LLM generate text chậm (vài giây). Nếu chờ hết rồi trả về → UX tệ.  
**Server-Sent Events (SSE)** cho phép server push từng token ngay khi có → user thấy text xuất hiện dần dần như ChatGPT.

---

## SSE là gì?

SSE là HTTP response dài, server liên tục gửi `data: ...\n\n`:

```
Client → POST /v1/chat
Server → HTTP 200, Content-Type: text/event-stream
         data: {"chunk": "Hello"}
         data: {"chunk": " world"}
         data: {"chunk": "!"}
         data: [DONE]
         [connection close]
```

Khác WebSocket ở chỗ: **1 chiều** (server → client), đơn giản hơn, đủ dùng cho streaming text.

---

## Request model

```python
# chat.py:32
class ChatRequest(BaseModel):
    message: str
    stream: bool = True      # True = SSE, False = JSON
    use_rag: bool = True     # True = RAG chain, False = plain LLM
    system: str = "You are a helpful assistant."
```

---

## SSE Generator

```python
# chat.py:44
async def _sse_generator(gen: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
    async for chunk in gen:
        data = json.dumps({"chunk": chunk})
        yield f"data: {data}\n\n".encode()   # chat.py:47 — SSE format
    yield b"data: [DONE]\n\n"               # chat.py:48 — signal kết thúc
```

**SSE format chuẩn**: mỗi message = `data: <content>\n\n` (2 newlines kết thúc event).  
Encode sang `bytes` vì `StreamingResponse` expect bytes generator.

---

## Main handler

```python
# chat.py:53
async def chat(req: ChatRequest):
```

### Nhánh RAG + streaming (default):
```python
# chat.py:63-70
if req.use_rag:
    chain = RAGChain()
    if req.stream:
        return StreamingResponse(
            _sse_generator(chain.stream(req.message)),  # chain.py:105
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},  # tắt nginx buffer
        )
```

`X-Accel-Buffering: no` — nginx mặc định buffer response. Header này tắt buffering để client nhận token ngay, không chờ nginx tích lũy.

### Nhánh RAG + non-streaming:
```python
# chat.py:71-73
    else:
        result = await chain.retrieve_with_answer(req.message)  # chain.py:111
        return ChatResponse(**result)  # {"answer": "...", "sources": [...]}
```

### Nhánh plain LLM (không RAG):
```python
# chat.py:75-83
else:
    params = model_router.route(req.message)   # model_router.py:64
    llm = LLMClient(base_url=params.base_url, model=params.model)
    if req.stream:
        return StreamingResponse(
            _sse_generator(
                llm.stream(req.message, temperature=params.temperature)  # llm.py:75
            ),
            media_type="text/event-stream",
        )
```

`model_router.route()` phân tích query → chọn temperature/max_tokens phù hợp (xem [Model Router](../ARCHITECTURE.md#4-model-router)).

---

## Đọc SSE từ client

### Dùng `curl`:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Count 1 to 5", "stream": true, "use_rag": false}' \
  --no-buffer   # tắt curl buffering để thấy streaming
```

### Dùng Python `httpx`:
```python
import httpx, json

async with httpx.AsyncClient() as client:
    async with client.stream("POST", "http://localhost:8000/v1/chat",
        json={"message": "Hello", "stream": True, "use_rag": False}
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = line[6:]               # bỏ "data: " prefix
                if data == "[DONE]":
                    break
                chunk = json.loads(data)["chunk"]
                print(chunk, end="", flush=True)
```

### Dùng JavaScript `EventSource` (Frontend):
```javascript
// EventSource chỉ hỗ trợ GET — với POST cần fetch + ReadableStream
const response = await fetch('/v1/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: "Hello", stream: true})
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    // parse "data: {...}\n\n"
    for (const line of text.split('\n')) {
        if (line.startsWith('data: ') && line !== 'data: [DONE]') {
            const {chunk} = JSON.parse(line.slice(6));
            output += chunk;
        }
    }
}
```

---

## Thử ngay

```bash
# Streaming RAG (cần đã seed docs)
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain the hybrid search in Nexus AI", "stream": true}' \
  --no-buffer

# Non-streaming plain chat
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?", "stream": false, "use_rag": false}' | python3 -m json.tool
```

---

**Bài trước**: [06 — RAG Chain](./06-rag-chain.md)

---

## Tổng kết Phase 1

Bạn đã học toàn bộ backend stack:

```
Config (01) → LLM Client (02) → Embeddings (03)
                                      ↓
                             RAG Ingestion (04)
                                      ↓
                           Hybrid Retriever (05)
                                      ↓
                            RAG Chain LCEL (06)
                                      ↓
                          Chat API + SSE (07)
```

**Tiếp theo**: Phase 2 — Agent System với LangGraph (`docs/lessons/08-langgraph-agents.md`)
