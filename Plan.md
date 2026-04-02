# PLAN: Local AI Platform — “Nexus AI”

## Mục tiêu

Build một **production-grade AI Assistant platform** chạy hoàn toàn local trên RTX 4070 Super (12GB VRAM), sử dụng OpenAI-compatible API. Project này showcase toàn bộ skillset: LangChain, LangGraph, RAG, Vector DB, Docker, Kubernetes, MLOps, AI Agents, Evaluation.

-----

## HARDWARE & CONSTRAINTS

- GPU: RTX 4070 Super 12GB VRAM
- Model serving: Ollama (OpenAI-compatible endpoint tại `http://localhost:11434/v1`)
- Models: Qwen2.5-7B-Instruct (chính), Qwen2.5-3B (fallback nhẹ), nomic-embed-text (embedding)
- Tất cả service giao tiếp qua OpenAI-compatible API format (`/v1/chat/completions`, `/v1/embeddings`)

-----

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────┐
│                      FRONTEND                           │
│              React + Vite + TailwindCSS                 │
│         (Chat UI, Document Upload, Agent Status)        │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP/WebSocket
┌─────────────────▼───────────────────────────────────────┐
│                    API GATEWAY                           │
│              FastAPI + JWT Auth + Rate Limit             │
│              SSE Streaming + WebSocket                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  RAG Engine  │  │ Agent System │  │  Model Router │  │
│  │  LangChain   │  │  LangGraph   │  │  (Qwen 7B/3B) │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                │                   │          │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌───────▼───────┐  │
│  │  Qdrant     │  │  Tool Suite  │  │   Ollama      │  │
│  │  Vector DB  │  │  (Search,    │  │   (OpenAI     │  │
│  │  (Hybrid    │  │   Code Exec, │  │    Compatible)│  │
│  │   Search)   │  │   DB Query)  │  │               │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                   OBSERVABILITY                          │
│        Langfuse (LLM Tracing) + Prometheus + Grafana    │
└─────────────────────────────────────────────────────────┘
```

-----

## PROJECT STRUCTURE

```
nexus-ai/
├── docker-compose.yml          # Local dev: tất cả services
├── docker-compose.prod.yml     # Production-like setup
├── Makefile                    # Shortcuts: make up, make down, make test
├── .env.example
├── .github/
│   └── workflows/
│       └── ci.yml              # CI: lint, test, build images
│
├── k8s/                        # Kubernetes manifests
│   ├── namespace.yml
│   ├── ollama/
│   │   ├── deployment.yml
│   │   ├── service.yml
│   │   └── pvc.yml             # PersistentVolume cho models
│   ├── qdrant/
│   │   ├── statefulset.yml
│   │   └── service.yml
│   ├── api/
│   │   ├── deployment.yml
│   │   ├── service.yml
│   │   ├── hpa.yml             # HorizontalPodAutoscaler
│   │   └── ingress.yml
│   ├── worker/
│   │   └── deployment.yml      # Background jobs (ingestion)
│   ├── langfuse/
│   │   ├── deployment.yml
│   │   └── service.yml
│   ├── monitoring/
│   │   ├── prometheus-config.yml
│   │   └── grafana-deployment.yml
│   └── helm/
│       └── nexus-ai/
│           ├── Chart.yaml
│           ├── values.yaml
│           └── templates/
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml          # Dependencies (uv/poetry)
│   ├── src/
│   │   ├── main.py             # FastAPI app entry
│   │   ├── config.py           # Settings từ env vars
│   │   ├── auth/
│   │   │   ├── jwt.py
│   │   │   └── middleware.py
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── chat.py         # POST /v1/chat (streaming SSE)
│   │   │   │   ├── documents.py    # POST /v1/documents (upload & ingest)
│   │   │   │   ├── agents.py       # POST /v1/agents/run
│   │   │   │   └── health.py       # GET /health
│   │   │   └── deps.py
│   │   ├── core/
│   │   │   ├── llm.py             # OpenAI-compatible client wrapper
│   │   │   ├── model_router.py    # Route to Qwen-7B or Qwen-3B
│   │   │   └── embeddings.py      # Embedding via Ollama
│   │   ├── rag/
│   │   │   ├── ingestion.py       # Document chunking + embedding
│   │   │   ├── retriever.py       # Qdrant hybrid search (dense+sparse)
│   │   │   ├── chain.py           # LangChain RAG chain
│   │   │   └── reranker.py        # Cross-encoder reranking (optional)
│   │   ├── agents/
│   │   │   ├── graph.py           # LangGraph state machine
│   │   │   ├── nodes/
│   │   │   │   ├── planner.py     # Task decomposition
│   │   │   │   ├── researcher.py  # RAG + web search
│   │   │   │   ├── coder.py       # Code generation + sandbox exec
│   │   │   │   └── reviewer.py    # Self-review + correction
│   │   │   ├── tools/
│   │   │   │   ├── search.py      # DuckDuckGo search
│   │   │   │   ├── code_exec.py   # Sandboxed Python execution
│   │   │   │   ├── db_query.py    # SQLite/PostgreSQL query tool
│   │   │   │   └── calculator.py
│   │   │   └── state.py           # Agent state schema
│   │   ├── eval/
│   │   │   ├── evaluator.py       # Automated response scoring
│   │   │   ├── metrics.py         # Task completion, quality, relevance
│   │   │   └── dataset.py         # Eval dataset management
│   │   └── observability/
│   │       ├── langfuse_client.py  # LLM tracing
│   │       ├── metrics.py          # Prometheus metrics
│   │       └── logging.py
│   └── tests/
│       ├── test_rag.py
│       ├── test_agents.py
│       ├── test_model_router.py
│       └── test_api.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx      # Streaming chat UI
│   │   │   ├── DocumentUpload.tsx  # Drag-drop upload
│   │   │   ├── AgentStatus.tsx     # Real-time agent step display
│   │   │   └── ModelSelector.tsx   # Choose model
│   │   ├── hooks/
│   │   │   ├── useChat.ts          # SSE streaming hook
│   │   │   └── useWebSocket.ts
│   │   └── api/
│   │       └── client.ts
│   └── tailwind.config.js
│
├── scripts/
│   ├── setup.sh                # One-command setup
│   ├── pull-models.sh          # ollama pull qwen2.5:7b-instruct etc.
│   ├── seed-documents.sh       # Ingest sample docs
│   └── run-eval.sh             # Run evaluation suite
│
└── docs/
    ├── ARCHITECTURE.md
    ├── SETUP.md
    └── API.md
```

-----

## PHASE 1: RAG Pipeline + API (Tuần 1-2)

### Yêu cầu Claude Code:

```
Tạo project nexus-ai theo structure ở trên. Phase 1 focus vào:

1. **Ollama integration (OpenAI-compatible)**:
   - File: backend/src/core/llm.py
   - Dùng `openai` Python SDK trỏ đến Ollama endpoint
   - Wrapper class `LLMClient` với:
     - base_url = "http://ollama:11434/v1" (docker) hoặc "http://localhost:11434/v1"
     - Hỗ trợ streaming via SSE
     - Model selection: qwen2.5:7b-instruct (default), qwen2.5:3b (fallback)

   ```python
   from openai import OpenAI
   
   client = OpenAI(
       base_url="http://localhost:11434/v1",
       api_key="ollama"  # Ollama không cần key nhưng SDK require
   )
```

1. **Embedding service**:
- File: backend/src/core/embeddings.py
- Dùng Ollama endpoint cho nomic-embed-text
- LangChain `OllamaEmbeddings` hoặc OpenAI-compatible embeddings endpoint
- Output: 768-dim vectors
1. **Qdrant Vector DB**:
- Docker: qdrant/qdrant:latest, port 6333
- Collection config:
  - vectors: size=768, distance=Cosine
  - sparse_vectors: enable cho BM25 hybrid search
- File: backend/src/rag/retriever.py
- Implement hybrid search: dense (semantic) + sparse (keyword BM25)
- Dùng `qdrant-client` + `langchain-qdrant`
1. **Document Ingestion Pipeline**:
- File: backend/src/rag/ingestion.py
- Support: PDF, TXT, MD, DOCX
- Chunking: RecursiveCharacterTextSplitter (chunk_size=512, overlap=50)
- Metadata: filename, page_number, chunk_index, ingestion_timestamp
- Batch embedding + upsert vào Qdrant
1. **RAG Chain (LangChain)**:
- File: backend/src/rag/chain.py
- Flow: query → retrieve top-k (k=5) → rerank → format context → LLM generate
- Dùng LangChain LCEL:
  
  ```python
  chain = (
      {"context": retriever | format_docs, "question": RunnablePassthrough()}
      | prompt
      | llm
      | StrOutputParser()
  )
  ```
- Prompt template có instruction rõ ràng: cite source, thừa nhận khi không biết
1. **FastAPI Backend**:
- File: backend/src/main.py
- Routes:
  - POST /v1/chat — streaming chat (SSE via StreamingResponse)
  - POST /v1/documents — upload file, trigger ingestion
  - GET /v1/documents — list ingested documents
  - GET /health — health check (Ollama + Qdrant status)
- Middleware: CORS, request logging
- Error handling: proper HTTP status codes
1. **Docker Compose** (docker-compose.yml):
   
   ```yaml
   services:
     ollama:
       image: ollama/ollama:latest
       ports: ["11434:11434"]
       volumes:
         - ollama_data:/root/.ollama
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
   
     qdrant:
       image: qdrant/qdrant:latest
       ports: ["6333:6333"]
       volumes:
         - qdrant_data:/qdrant/storage
   
     api:
       build: ./backend
       ports: ["8000:8000"]
       env_file: .env
       depends_on: [ollama, qdrant]
       volumes:
         - ./backend/src:/app/src  # Hot reload
   
   volumes:
     ollama_data:
     qdrant_data:
   ```
1. **Makefile**:
   
   ```makefile
   up:
       docker compose up -d
   down:
       docker compose down
   logs:
       docker compose logs -f api
   setup:
       docker compose up -d ollama
       docker exec ollama ollama pull qwen2.5:7b-instruct
       docker exec ollama ollama pull qwen2.5:3b
       docker exec ollama ollama pull nomic-embed-text
   test:
       cd backend && pytest tests/ -v
   ```

Dependencies (pyproject.toml):

- fastapi, uvicorn[standard]
- openai
- langchain, langchain-community, langchain-openai
- qdrant-client, langchain-qdrant
- python-multipart (file upload)
- python-jose[cryptography] (JWT)
- unstructured[pdf,docx] (document parsing)
- python-dotenv
- pytest, httpx (testing)

```
---

## PHASE 2: Agent System + LangGraph (Tuần 3-4)

### Yêu cầu Claude Code:
```

Thêm Agent System vào nexus-ai sử dụng LangGraph. Tất cả LLM call
đều qua OpenAI-compatible Ollama endpoint.

1. **LangGraph State Machine**:
- File: backend/src/agents/state.py
   
   ```python
   from typing import TypedDict, Annotated, Sequence
   from langgraph.graph.message import add_messages
   
   class AgentState(TypedDict):
       messages: Annotated[Sequence, add_messages]
       task: str
       plan: list[str]
       current_step: int
       tool_results: list[dict]
       final_answer: str
       needs_review: bool
   ```
- File: backend/src/agents/graph.py
- Graph structure:
   
   ```
   START → planner → researcher → coder (conditional) → reviewer → END
                ↑                                            │
                └────────── retry (if review fails) ─────────┘
   ```
- Conditional edges:
  - Nếu task cần code → route qua coder node
  - Nếu reviewer reject → loop lại researcher (max 2 retries)
  - Human-in-the-loop: interrupt_before=[“reviewer”] (optional)
1. **Agent Nodes**:
- planner.py: Nhận task → decompose thành steps → output plan
- researcher.py: Dùng RAG retriever + DuckDuckGo search tool
- coder.py: Generate Python code + execute trong sandbox
- reviewer.py: Self-critique, check quality, decide pass/retry
1. **Tools**:
- search.py: DuckDuckGo search via `duckduckgo-search` package
  
  ```python
  @tool
  def web_search(query: str) -> str:
      """Search the web for current information."""
      from duckduckgo_search import DDGS
      results = DDGS().text(query, max_results=5)
      return "\n".join([f"{r['title']}: {r['body']}" for r in results])
  ```
- code_exec.py: Sandboxed Python execution via subprocess + timeout
  
  ```python
  @tool
  def execute_python(code: str) -> str:
      """Execute Python code in a sandboxed environment."""
      # subprocess với timeout=30s, restricted imports
  ```
- db_query.py: Query SQLite database
- calculator.py: Math expressions via `numexpr`
1. **API Route cho Agents**:
- POST /v1/agents/run — start agent task
- WebSocket /v1/agents/stream — stream agent steps real-time
- Mỗi node completion → emit event qua WebSocket:
  
  ```json
  {"event": "node_complete", "node": "planner", "output": "..."}
  {"event": "tool_call", "tool": "web_search", "input": "..."}
  {"event": "final_answer", "content": "..."}
  ```
1. **Model Router**:
- File: backend/src/core/model_router.py
- Logic: estimate task complexity → chọn model
  - Simple Q&A, classification → qwen2.5:3b (nhanh, tiết kiệm VRAM)
  - Complex reasoning, code gen, agent tasks → qwen2.5:7b-instruct
- Fallback: nếu 7B OOM hoặc timeout → retry với 3B
- Tất cả đều qua OpenAI-compatible format

Thêm dependencies: langgraph, duckduckgo-search, numexpr, websockets

```
---

## PHASE 3: Kubernetes + Monitoring (Tuần 5-6)

### Yêu cầu Claude Code:
```

Migrate nexus-ai từ Docker Compose lên Kubernetes (local cluster
via minikube hoặc k3s). Thêm full monitoring stack.

1. **Kubernetes Manifests** (k8s/):
   
   a. Namespace: nexus-ai
   
   b. Ollama Deployment:
- GPU resource request: nvidia.com/gpu: 1
- PVC cho model storage (10Gi)
- Liveness probe: curl http://localhost:11434/api/tags
- Resource limits: memory 14Gi (12GB VRAM + system)
   
   c. Qdrant StatefulSet:
- PVC cho vector storage (20Gi)
- Readiness probe: GET /healthz
- Resource: 2Gi memory, 1 CPU
   
   d. API Deployment:
- Replicas: 2
- HPA: min=2, max=5, targetCPU=70%
- Readiness/Liveness probes: GET /health
- Resource: 512Mi-1Gi memory, 0.5-1 CPU
- ConfigMap cho env vars
- Secret cho API keys
   
   e. Worker Deployment:
- Cho background document ingestion
- 1 replica, không cần HPA
   
   f. Ingress:
- nginx ingress controller
- Route: /api/* → api-service, /* → frontend-service
   
   g. Langfuse:
- Deployment + PostgreSQL (bitnami/postgresql)
- Service internal-only
1. **Helm Chart** (k8s/helm/nexus-ai/):
- values.yaml configurable:
  - ollama.model: “qwen2.5:7b-instruct”
  - qdrant.storage: “20Gi”
  - api.replicas: 2
  - monitoring.enabled: true
- Templates cho tất cả resources ở trên
1. **Monitoring Stack**:
   
   a. Prometheus:
- Scrape targets: api (port 8000/metrics), qdrant, ollama
- Custom metrics từ FastAPI:
  - request_duration_seconds (histogram)
  - llm_tokens_total (counter, label: model)
  - llm_latency_seconds (histogram, label: model)
  - rag_retrieval_latency_seconds
  - agent_task_duration_seconds
  - active_requests (gauge)
   
   b. Grafana:
- Dashboard “Nexus AI Overview”:
  - Request rate & latency (p50, p95, p99)
  - LLM token throughput per model
  - RAG retrieval latency
  - Agent task completion rate
  - Qdrant collection stats
  - GPU memory usage (nvidia-smi exporter)
- Dashboard “Agent Analytics”:
  - Tasks per agent node
  - Retry rate
  - Tool usage frequency
   
   c. Langfuse (LLM Observability):
- Trace mỗi LLM call: model, prompt, completion, tokens, latency
- Trace mỗi chain/agent run: steps, tools used, total cost
- File: backend/src/observability/langfuse_client.py
- Integrate với LangChain callback handler
1. **Backend metrics endpoint**:
- File: backend/src/observability/metrics.py
- Dùng `prometheus-fastapi-instrumentator`
- Custom metrics via `prometheus_client`
1. **CI/CD** (.github/workflows/ci.yml):
   
   ```yaml
   name: CI
   on: [push, pull_request]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with: {python-version: "3.11"}
         - run: pip install -e ".[test]"
         - run: pytest tests/ -v --cov=src
     
     lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - run: pip install ruff
         - run: ruff check src/
     
     docker:
       needs: [test, lint]
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: docker/build-push-action@v5
           with:
             context: ./backend
             tags: nexus-ai-api:${{ github.sha }}
   ```

Scripts:

- scripts/k8s-setup.sh: Install minikube/k3s, enable nvidia plugin, deploy
- scripts/k8s-deploy.sh: helm upgrade –install nexus-ai ./k8s/helm/nexus-ai

```
---

## PHASE 4: Evaluation + Fine-tuning Loop (Tuần 7-8, Optional)

### Yêu cầu Claude Code:
```

Thêm evaluation pipeline và feedback-driven improvement vào nexus-ai.

1. **Eval Framework** (tận dụng kinh nghiệm crab-eval):
- File: backend/src/eval/evaluator.py
- Three-axis scoring:
  a. Task Completion (0-1): Có trả lời đúng câu hỏi không?
  b. Quality (0-1): Coherent, well-structured, cited sources?
  c. Faithfulness (0-1): Response grounded in retrieved context?
- Dùng LLM-as-judge (Qwen-7B judge chính nó hoặc dùng external API)
- Multi-judge consensus: 3 lần judge, lấy majority vote
- Bootstrap confidence intervals cho mỗi metric
1. **Eval Dataset**:
- File: backend/src/eval/dataset.py
- Format: JSON lines
  
  ```json
  {"query": "...", "expected_answer": "...", "category": "factual|reasoning|code"}
  ```
- Seed 50 test cases across categories
- Auto-expand dataset từ user interactions (with consent flag)
1. **Eval Runner**:
- scripts/run-eval.sh
- Output: JSON report + markdown summary
- Compare across models: qwen-7b vs qwen-3b
- Track metrics over time (store in SQLite)
1. **User Feedback Loop**:
- API: POST /v1/feedback — {message_id, rating: 1-5, comment}
- Store feedback in PostgreSQL
- Weekly report: top failures, common patterns
- Export training data format cho potential fine-tuning
1. **A/B Testing**:
- Model router randomly assigns model variant (with logging)
- Compare user satisfaction scores between variants
- File: backend/src/core/ab_testing.py
1. **Guardrails & Safety**:
- Input validation: detect prompt injection attempts
- Output filtering: check for hallucination markers
- Rate limiting per user
- File: backend/src/core/guardrails.py

```
---

## QUICK START COMMANDS

```bash
# Clone & setup
git clone <repo>
cd nexus-ai

# Phase 1: Docker Compose
make setup          # Pull Ollama models
make up             # Start all services
make test           # Run tests

# Seed sample documents
bash scripts/seed-documents.sh

# Test chat
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is RAG?", "stream": true}'

# Phase 3: Kubernetes
bash scripts/k8s-setup.sh
bash scripts/k8s-deploy.sh
kubectl -n nexus-ai get pods

# Phase 4: Eval
bash scripts/run-eval.sh
```

-----

## KEY DESIGN DECISIONS

|Decision     |Choice          |Reason                                                 |
|-------------|----------------|-------------------------------------------------------|
|LLM Serving  |Ollama          |OpenAI-compatible API, easy GPU setup, model management|
|Vector DB    |Qdrant          |Hybrid search native, lightweight, Rust-based          |
|Orchestration|LangGraph       |State machine cho agent, hơn LangChain AgentExecutor   |
|Embedding    |nomic-embed-text|768-dim, chạy local qua Ollama, quality tốt cho size   |
|Observability|Langfuse        |Self-hosted, LangChain native integration              |
|API          |FastAPI         |Async native, streaming support, auto-docs             |
|Container    |Docker + K8s    |Industry standard, portfolio-worthy                    |

-----

## NOTES CHO CLAUDE CODE

- Tất cả LLM calls phải qua OpenAI SDK format → dễ swap model provider sau này
- Không hardcode model name → dùng env var `DEFAULT_MODEL=qwen2.5:7b-instruct`
- Mọi async operation dùng `asyncio` — FastAPI native async
- Type hints everywhere — dùng Pydantic v2 cho data models
- Mỗi module có docstring giải thích purpose
- Error handling: không bare except, log properly
- Tests: mỗi module có unit test, integration test cho API routes
