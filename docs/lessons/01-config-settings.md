# Bài 01 — Config & Settings

**Code**: [`backend/src/config.py`](../../backend/src/config.py)

---

## Vấn đề cần giải quyết

App cần biết: llama-server ở đâu? Qdrant ở đâu? JWT secret là gì?  
Nếu hardcode trong code → không thể đổi khi deploy khác môi trường.  
**Giải pháp**: đọc từ environment variables, validate ngay lúc start.

---

## Concept: pydantic-settings

`pydantic-settings` đọc env vars → parse → validate type → crash sớm nếu sai.

```python
# config.py:12
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",           # đọc từ file .env
        env_file_encoding="utf-8",
        case_sensitive=False,      # LLAMACPP_CHAT_URL == llamacpp_chat_url
    )
```

---

## Các field quan trọng

```python
# config.py:20-21 — URL của 2 llama-server instances
llamacpp_chat_url: str = "http://llamacpp-chat:8080/v1"
llamacpp_embed_url: str = "http://llamacpp-embed:8081/v1"
# Giá trị default dùng trong Docker (service name)
# Khi chạy local: đổi sang http://localhost:8080/v1
# → Trong .env: LLAMACPP_CHAT_URL=http://host.docker.internal:8080/v1

# config.py:28 — Qdrant URL
qdrant_url: str = "http://qdrant:6333"

# config.py:42-43 — RAG chunking params
chunk_size: int = 512     # ký tự/chunk
chunk_overlap: int = 50   # overlap giữa chunks
retriever_top_k: int = 5  # số kết quả retrieve
```

---

## Validator: xử lý list từ env string

pydantic-settings v2 không tự parse `"http://a,http://b"` thành list.  
Cần validator riêng:

```python
# config.py:46-50
@field_validator("cors_origins", mode="before")
@classmethod
def parse_cors_origins(cls, v):
    if isinstance(v, str):
        return [o.strip() for o in v.split(",") if o.strip()]
    return v
```

Trong `.env`:
```
# Cả 2 format đều work:
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]  # JSON array
CORS_ORIGINS=http://localhost:5173,http://localhost:3000       # comma-separated
```

---

## Property computed

```python
# config.py:55
@property
def is_development(self) -> bool:
    return self.app_env == "development"
```

Dùng trong `auth/middleware.py:20` để skip auth khi dev.

---

## Singleton pattern

```python
# config.py:58 — cuối file
settings = Settings()
```

Tất cả module import cùng 1 instance:
```python
from src.config import settings
print(settings.llamacpp_chat_url)
```

---

## Thử ngay

```bash
cd backend
# Xem settings hiện tại
python3 -c "from src.config import settings; print(settings.model_dump())"

# Thử override bằng env var
LLAMACPP_CHAT_URL=http://custom:9999/v1 python3 -c \
  "from src.config import settings; print(settings.llamacpp_chat_url)"
# → http://custom:9999/v1
```

---

**Bài tiếp theo**: [02 — LLM Client](./02-llm-client.md)
