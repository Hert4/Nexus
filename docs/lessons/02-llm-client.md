# Bài 02 — LLM Client

**Code**: [`backend/src/core/llm.py`](../../backend/src/core/llm.py)

---

## Vấn đề cần giải quyết

Cần gọi LLM (llama-server) để generate text. Có 2 mode:
- **Non-streaming**: chờ hết rồi trả về full string
- **Streaming**: nhận từng token ngay khi model generate → UX tốt hơn

---

## Tại sao dùng `openai` SDK thay vì `httpx` trực tiếp?

llama-server expose `/v1/chat/completions` giống hệt OpenAI API.  
Dùng `openai.AsyncOpenAI` với `base_url` trỏ vào llama-server:

```python
# llm.py:20
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError
```

**Lợi ích**: type-safe responses, retry logic, streaming built-in, dễ swap sang OpenAI thật sau này chỉ cần đổi `base_url` + `api_key`.

---

## Khởi tạo client

```python
# llm.py:27 — class definition
class LLMClient:

# llm.py:42-46 — tạo AsyncOpenAI instance
self._client = AsyncOpenAI(
    base_url=self._base_url,   # "http://host.docker.internal:8080/v1"
    api_key="llama-cpp",       # llama-server không cần key, nhưng SDK require non-empty string
    timeout=120.0,             # 2 phút — model lớn generate chậm
)
```

`AsyncOpenAI` (async) thay vì `OpenAI` (sync) vì FastAPI là async framework — không được block event loop.

---

## Non-streaming: `chat()`

```python
# llm.py:48
async def chat(self, prompt, system, temperature=0.7, max_tokens=2048) -> str:
    response = await self._client.chat.completions.create(
        model=self._model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,  # 0=deterministic, 1=creative
        max_tokens=max_tokens,
        stream=False,             # ← chờ hết rồi trả về
    )
    return response.choices[0].message.content or ""
    # llm.py:68 — choices[0] vì request 1 completion, message.content là string
```

---

## Streaming: `stream()`

```python
# llm.py:75
async def stream(self, prompt, ...) -> AsyncGenerator[str, None]:
    stream = await self._client.chat.completions.create(
        ...,
        stream=True,   # ← trả về AsyncStream[ChatCompletionChunk]
    )
    async for chunk in stream:                          # llm.py:92
        delta = chunk.choices[0].delta.content         # llm.py:93
        if delta:                                      # có thể None ở chunk đầu/cuối
            yield delta                                # yield từng token
```

`AsyncGenerator[str, None]` — caller dùng `async for token in llm.stream(...)`.

---

## Error handling

```python
# llm.py:71 và llm.py:99
except (APIConnectionError, APITimeoutError) as e:
    logger.error("LLM connection error", error=str(e))
    raise
```

Không catch `Exception` chung — chỉ bắt lỗi network cụ thể, log rồi re-raise để caller xử lý.

---

## Singleton & custom instance

```python
# llm.py:133 — singleton dùng chung
llm_client = LLMClient()

# Hoặc tạo instance với params khác (dùng trong model_router)
custom = LLMClient(
    base_url="http://localhost:8080/v1",  # local, không qua Docker
    model="Qwen3.5-9B.Q6_K.gguf",
)
```

---

## Thử ngay

```bash
cd backend
python3 -c "
import asyncio
from src.core.llm import LLMClient

async def test():
    client = LLMClient(base_url='http://localhost:8080/v1')
    # Non-streaming
    result = await client.chat('Say hello in one word')
    print('Non-stream:', result)
    # Streaming
    print('Stream: ', end='')
    async for chunk in client.stream('Count 1 to 5'):
        print(chunk, end='', flush=True)
    print()

asyncio.run(test())
"
```

---

**Bài trước**: [01 — Config](./01-config-settings.md)  
**Bài tiếp theo**: [03 — Embeddings](./03-embeddings.md)
