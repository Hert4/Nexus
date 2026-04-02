# SETUP — Chạy Nexus AI từ đầu

> Code references trong tài liệu này trỏ trực tiếp đến file + dòng thực tế.

---

## Prerequisites

- Docker + Docker Compose với NVIDIA Container Toolkit
- `llama-server` đã cài (Homebrew: `brew install llama.cpp`)
- GGUF model files symlinked tại `models/`

---

## Bước 1: Kiểm tra models

```bash
make setup
# Script: scripts/setup.sh:28-40
# Kiểm tra models/Qwen3.5-9B.Q6_K.gguf và nomic-embed-text-v1.5.Q4_K_M.gguf
```

**Tại sao symlink thay vì copy?**
File GGUF nặng 6.9GB — symlink trỏ về `/home/dev/Develop_2026/gguf/` không tốn thêm disk.
Docker mount: `docker-compose.yml:16` — `./models:/models:ro`

---

## Bước 2: Start llama-server (native trên host)

```bash
make serve
# → scripts/start-llamacpp.sh start
```

Script `scripts/start-llamacpp.sh` khởi động 2 process:

**Chat server** (`:8080`):
```bash
# start-llamacpp.sh:36-46
llama-server \
  --model models/Qwen3.5-9B.Q6_K.gguf \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 8192 \
  --n-gpu-layers 99 \       # offload tất cả layers lên GPU
  --parallel 4 \            # xử lý 4 request song song
  --flash-attn on           # Flash Attention 2 — giảm VRAM, tăng tốc
```

**Embed server** (`:8081`):
```bash
# start-llamacpp.sh:57-65
llama-server \
  --model models/nomic-embed-text-v1.5.Q4_K_M.gguf \
  --host 0.0.0.0 --port 8081 \
  --n-gpu-layers 99 \
  --embedding \             # bật embedding mode
  --pooling mean            # mean pooling → 768-dim vector
```

**Tại sao chạy native thay vì Docker?**
Docker image `ghcr.io/ggerganov/llama.cpp:server-cuda` không pull được (manifest unknown).
`llama-server` đã cài sẵn qua Homebrew tại `/home/linuxbrew/.linuxbrew/bin/llama-server`.

**API container reach llama-server qua** `host.docker.internal` ([`.env.example:2`](../.env.example#L2)):
```
LLAMACPP_CHAT_URL=http://host.docker.internal:8080/v1
LLAMACPP_EMBED_URL=http://host.docker.internal:8081/v1
```
Docker compose inject `host-gateway` ([`docker-compose.yml:22`](../docker-compose.yml#L22)):
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

---

## Bước 3: Start Docker services

```bash
make up
# docker-compose.yml: qdrant + api
```

**Qdrant** ([`docker-compose.yml:8`](../docker-compose.yml#L8)):
- Port 6333 (HTTP), 6334 (gRPC)
- Volume: `qdrant_data` (persistent)
- Healthcheck: `bash -c "echo > /dev/tcp/localhost/6333"` — Qdrant image không có `curl`/`wget`

**API** ([`docker-compose.yml:20`](../docker-compose.yml#L20)):
- Build từ `backend/Dockerfile`
- Volume mount `./backend/src:/app/src` → hot reload khi sửa code
- `env_file: .env` → inject tất cả env vars

---

## Bước 4: Verify

```bash
curl http://localhost:8000/health
```

Health check logic tại [`api/routes/health.py:29`](../backend/src/api/routes/health.py#L29):
```python
base = url.removesuffix("/v1").removesuffix("/")  # health.py:34
r = await client.get(f"{base}/health")             # → llama-server /health
```

**Kỳ vọng:**
```json
{
  "status": "ok",
  "services": {
    "llamacpp_chat": {"status": "ok"},
    "llamacpp_embed": {"status": "ok"},
    "qdrant": {"status": "ok"}
  }
}
```

---

## Bước 5: Seed documents và test RAG

```bash
bash scripts/seed-documents.sh
# Upload tất cả docs/*.md vào Qdrant
# API: POST /v1/documents → ingestion.py:100
```

Sau khi seed, test RAG:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the Nexus AI architecture?", "stream": false, "use_rag": true}'
```

---

## Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `llamacpp_embed: error` | health.py dùng `rstrip` sai | Đã fix sang `.removesuffix()` tại [`health.py:34`](../backend/src/api/routes/health.py#L34) |
| `SettingsError: cors_origins` | pydantic-settings v2 cần JSON array | `.env`: `CORS_ORIGINS=["http://..."]` — validator tại [`config.py:46`](../backend/src/config.py#L46) |
| `ModuleNotFoundError: langchain.text_splitter` | LangChain v0.3+ move package | Import từ `langchain_text_splitters` — [`ingestion.py:22`](../backend/src/rag/ingestion.py#L22) |
| Qdrant healthcheck fail | Qdrant image không có `curl` | Dùng bash TCP check — [`docker-compose.yml:15`](../docker-compose.yml#L15) |

---

## Dev workflow

```bash
# Sửa code → uvicorn tự reload (volume mount)
# Xem logs realtime
make logs           # API logs
make logs-chat      # llama-server chat logs (.pids/chat.log)
make logs-embed     # llama-server embed logs (.pids/embed.log)

# Chạy tests
make test           # cd backend && pytest tests/ -v
# Tests tại: backend/tests/test_api.py, test_rag.py, test_auth.py

# Lint
make lint           # ruff check src/
```
