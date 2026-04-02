# Nexus AI

**Local AI Assistant** chạy hoàn toàn offline trên GPU của bạn.  
RAG + LangGraph Agents + Kubernetes + Monitoring + React UI — production-grade từ local machine.

```
┌─────────────────────────────────┐
│  React UI :5173                 │
│  ├─ Chat (SSE streaming)        │
│  ├─ Document upload/manage      │
│  └─ Health status badge         │
├─────────────────────────────────┤
│  FastAPI :8000                  │
│  ├─ POST /v1/chat    (RAG+SSE)  │
│  ├─ POST /v1/agents/run         │
│  ├─ POST /v1/documents          │
│  └─ POST /v1/feedback           │
├─────────────────────────────────┤
│  llama.cpp (native GPU)         │
│  ├─ Chat  :8080  Qwen3.5-9B    │
│  └─ Embed :8081  nomic-embed   │
├─────────────────────────────────┤
│  Qdrant :6333  (vector DB)      │
└─────────────────────────────────┘
```

---

## Hardware yêu cầu

| Component | Minimum | Project này |
|-----------|---------|-------------|
| GPU | 8GB VRAM | RTX 4070 Super 12GB |
| RAM | 16GB | 32GB+ recommended |
| Disk | 20GB | ~15GB (models + data) |
| OS | Linux | Ubuntu 22.04+ |

---

## Cài đặt nhanh (5 phút)

### 1. Clone & chuẩn bị

```bash
git clone <repo-url>
cd Nexus

# Tạo symlinks đến GGUF models (không copy file)
mkdir -p models
ln -s /path/to/Qwen3.5-9B.Q6_K.gguf      models/
ln -s /path/to/nomic-embed-text-v1.5.Q4_K_M.gguf models/

# Copy .env
cp .env.example .env
```

### 2. Build llama.cpp với CUDA (nếu chưa có)

```bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DLLAMA_CUDA=ON
cmake --build build --config Release -j$(nproc)
# Binary tại: llama.cpp/build/bin/llama-server
```

### 3. Cập nhật đường dẫn trong `scripts/start-llamacpp.sh`

```bash
# Sửa dòng này trong scripts/start-llamacpp.sh:
LLAMA_SERVER="/path/to/llama.cpp/build/bin/llama-server"
```

### 4. Khởi động

```bash
# Terminal 1: Start llama-server (GPU)
make serve
# → Chat:  http://localhost:8080/v1  ✓
# → Embed: http://localhost:8081/v1  ✓

# Terminal 2: Start API + Qdrant + Frontend
make up
# → Frontend: http://localhost:5173    ✓  ← mở browser tại đây
# → API:      http://localhost:8000    ✓
# → Qdrant:   http://localhost:6333    ✓
```

### 5. Kiểm tra

```bash
curl http://localhost:8000/health
# {"status": "ok", "services": {"llamacpp_chat": "ok", ...}}
```

---

## Sử dụng

### Chat

```bash
# Streaming (SSE) — dùng -N để disable curl buffering
curl -N -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is RAG?", "stream": true}'
# data: {"chunk": "RAG"}
# data: {"chunk": " stands for..."}
# data: [DONE]

# Non-streaming + RAG
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain vector databases", "stream": false}'

# Plain chat (không RAG)
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi!", "use_rag": false, "stream": false}'
```

### Upload tài liệu vào RAG

```bash
# Upload PDF
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@your-document.pdf"

# Upload TXT/MD/DOCX cũng được
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@notes.md"

# List documents
curl http://localhost:8000/v1/documents
```

### Agent (multi-step reasoning)

```bash
# Non-streaming
curl -X POST http://localhost:8000/v1/agents/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Calculate fibonacci(15) with Python code"}' \
  | python3 -m json.tool

# WebSocket streaming
websocat ws://localhost:8000/v1/agents/ws \
  <<< '{"task": "Research and explain transformer architecture"}'
```

### Feedback

```bash
# Submit rating (message_id từ response header X-Message-ID)
curl -X POST http://localhost:8000/v1/feedback \
  -d '{"message_id": "abc123", "rating": 5, "comment": "Great answer!"}'
```

---

## Monitoring local

```bash
make monitor-up
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001  (admin/admin)
#   → Dashboard: Nexus AI Overview
```

---

## Evaluation

```bash
# Quick sanity check (10 cases, ~5 phút)
make eval-quick

# Full eval suite (50 cases, ~25 phút)
make eval

# Report:
cat data/eval-reports/eval-*.md
```

---

## Kubernetes (production)

```bash
# Setup k3s + tools (1 lần, cần sudo + terminal thật)
sudo make k8s-setup

# Deploy
make k8s-deploy

# Với monitoring
make k8s-deploy-all

# Status
make k8s-status
```

Xem chi tiết: [`docs/lessons/09-kubernetes.md`](docs/lessons/09-kubernetes.md)

---

## Cấu trúc project

```
Nexus/
├── backend/src/
│   ├── core/          # LLMClient, ModelRouter, Guardrails, A/B testing
│   ├── rag/           # Ingestion, HybridRetriever, RAGChain
│   ├── agents/        # LangGraph state machine + nodes + tools
│   ├── eval/          # Evaluator, Dataset, Metrics
│   └── api/routes/    # chat, documents, agents, feedback, health
├── k8s/               # Kubernetes manifests + Helm chart
├── monitoring/        # Prometheus + Grafana config
├── scripts/           # start-llamacpp.sh, k8s-setup.sh, run-eval.sh
├── models/            # Symlinks → GGUF files (không commit)
├── data/              # SQLite DBs + eval reports (không commit)
└── docs/lessons/      # 11 bài học từng module (có code links)
```

---

## API Reference

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/health` | GET | Health check tất cả services |
| `/v1/chat` | POST | Streaming/non-streaming chat với RAG |
| `/v1/documents` | POST | Upload + ingest tài liệu |
| `/v1/documents` | GET | List ingested documents |
| `/v1/agents/run` | POST | Chạy agent task |
| `/v1/agents/ws` | WS | Stream agent steps real-time |
| `/v1/feedback` | POST | Submit rating (1-5) |
| `/v1/eval/run` | POST | Trigger eval run |
| `/v1/eval/results/{id}` | GET | Poll eval results |
| `/v1/ab/report/{exp}` | GET | A/B experiment report |
| `/metrics` | GET | Prometheus metrics |
| `/docs` | GET | Swagger UI |

---

## Env vars

Xem `.env.example` để biết tất cả options.

Quan trọng nhất:

```bash
LLAMACPP_CHAT_URL=http://host.docker.internal:8080/v1
LLAMACPP_EMBED_URL=http://host.docker.internal:8081/v1
LLM_API_KEY=llama-cpp          # "llama-cpp" cho local, real key cho OpenAI/Groq
QDRANT_URL=http://qdrant:6333
```

Để swap sang OpenAI cloud:
```bash
LLAMACPP_CHAT_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
GGUF_CHAT_MODEL=gpt-4o-mini
```

---

## Tài liệu học

[`docs/lessons/`](docs/lessons/) — 11 bài học từng module, mỗi bài có code links:

| Bài | Chủ đề |
|-----|--------|
| 01 | Config & Settings |
| 02 | LLM Client |
| 03 | Embeddings |
| 04 | RAG Ingestion |
| 05 | Hybrid Retriever |
| 06 | RAG Chain (LCEL) |
| 07 | Chat API & SSE |
| 08 | LangGraph Agents |
| 09 | Kubernetes + k3s |
| 10 | Monitoring & Observability |
| 11 | Evaluation + Guardrails |

---

## Phases hoàn thành

- ✅ Phase 1: RAG Pipeline + FastAPI
- ✅ Phase 2: Agent System (LangGraph)
- ✅ Phase 3: Kubernetes + Monitoring (k3s, Helm, Prometheus, Grafana, Langfuse)
- ✅ Phase 4: Evaluation + Guardrails + A/B Testing + Feedback loop
- ✅ Phase 5: Frontend (React + Vite + TypeScript, SSE streaming, Document management)
