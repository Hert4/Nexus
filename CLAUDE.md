# Nexus AI — CLAUDE.md

## Project
Local AI Assistant platform chạy hoàn toàn local. Phase 1: RAG + FastAPI.

## Cấu trúc thư mục chính
```
backend/src/      — FastAPI app
  core/           — LLMClient, ModelRouter, Guardrails, ABTesting
  rag/            — Ingestion, Retriever, Chain
  agents/         — LangGraph state machine + nodes + tools
  eval/           — Evaluator (LLM-as-judge), Dataset (SQLite), Metrics
  api/routes/     — chat, documents, agents, feedback, health
  observability/  — Prometheus metrics, structlog, Langfuse
frontend/         — React + Vite + TypeScript UI
  src/api/        — API client (streamChat, uploadDocument, ...)
  src/components/ — ChatMessage, ChatInput, DocumentPanel, HealthBadge, FeedbackWidget
  src/hooks/      — useChat, useDocuments
models/           — Symlink → /home/dev/Develop_2026/gguf/ (GGUF files)
data/             — SQLite DBs (eval.db, ab_testing.db) + eval reports
scripts/          — start-llamacpp.sh, k8s-setup.sh, k8s-deploy.sh, run-eval.sh
monitoring/       — prometheus.yml, grafana provisioning + dashboards
k8s/              — Kubernetes manifests + Helm chart
.github/workflows/ — CI/CD (test, lint, docker build)
docs/             — Tài liệu học từ đầu cho mỗi module
```

## Commands
```bash
make up           # docker compose up -d (qdrant + api + frontend)
make down         # docker compose down
make logs         # logs api
make test         # pytest
make setup        # kiểm tra models/
make frontend-dev # Vite dev server :5173 (hot reload)
```

## Models
- Chat : `models/Qwen3.5-9B.Q6_K.gguf`  → llama-server :8080
- Embed: `models/nomic-embed-text-v1.5.Q4_K_M.gguf` → llama-server :8081

## Env vars quan trọng
| Var | Default |
|-----|---------|
| `LLAMACPP_CHAT_URL` | `http://llamacpp-chat:8080/v1` |
| `LLAMACPP_EMBED_URL` | `http://llamacpp-embed:8081/v1` |
| `LLM_API_KEY` | `llama-cpp` |
| `QDRANT_URL` | `http://qdrant:6333` |
| `GGUF_CHAT_MODEL` | `Qwen3.5-9B.Q6_K.gguf` |
| `GGUF_EMBED_MODEL` | `nomic-embed-text-v1.5.Q4_K_M.gguf` |

## Docs convention (QUAN TRỌNG)
- Mỗi doc trong `docs/` PHẢI có **code links** trỏ đúng file + line number
- Format: `[`backend/src/core/llm.py:42`](../backend/src/core/llm.py#L42)`
- **KHÔNG** chỉ viết hướng dẫn chung chung — phải giải thích *tại dòng đó làm gì*
- Khi thêm feature mới → chạy `grep -n` để lấy line numbers trước khi viết doc
- `docs/lessons/` — bài học từng concept theo thứ tự (01→11 hiện tại)
  - Mỗi bài: **Vấn đề → Code thực tế (có line) → Tại sao → Thử ngay**
  - Thêm bài mới → cập nhật `docs/lessons/README.md`
- Tất cả LLM call qua `openai.OpenAI` SDK (OpenAI-compatible)
- Async everywhere — FastAPI native async
- Pydantic v2 cho tất cả data models
- Mỗi module có docstring mô tả purpose
- Không bare `except` — log properly với structlog
- Mỗi implement mới → viết doc vào `docs/`
- Update file này (CLAUDE.md) mỗi khi có thay đổi lớn

## Phases
- [x] Phase 1: RAG Pipeline + FastAPI  ✅
- [x] Phase 2: Agent System (LangGraph) ✅ — tested, fibonacci(10)=55
- [x] Phase 3: Kubernetes + Monitoring  ✅ — k3s, Helm, Prometheus, Grafana, Langfuse, CI/CD
- [x] Phase 4: Evaluation + Guardrails  ✅ — LLM-as-judge, A/B testing, feedback loop, rate limiting
- [x] Phase 5: Frontend                 ✅ — React + Vite + TypeScript, SSE streaming, RAG UI
