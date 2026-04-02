# Lessons — Học Nexus AI từ đầu

Mỗi bài học giải thích **một concept**, trỏ thẳng đến đoạn code thực tế trong project.

## Thứ tự học đề xuất

| # | Bài | File code chính | Bạn sẽ hiểu |
|---|-----|-----------------|-------------|
| 01 | [Config & Settings](./01-config-settings.md) | `backend/src/config.py:12` | Pydantic-settings, env vars |
| 02 | [LLM Client](./02-llm-client.md) | `backend/src/core/llm.py:27` | OpenAI SDK, async, streaming |
| 03 | [Embeddings](./03-embeddings.md) | `backend/src/core/embeddings.py:25` | Vector, 768-dim, LangChain adapter |
| 04 | [RAG Ingestion](./04-rag-ingestion.md) | `backend/src/rag/ingestion.py:100` | Chunking, batch embed, Qdrant upsert |
| 05 | [Hybrid Retriever](./05-hybrid-retriever.md) | `backend/src/rag/retriever.py:49` | Dense, sparse, RRF fusion |
| 06 | [RAG Chain (LCEL)](./06-rag-chain.md) | `backend/src/rag/chain.py:67` | LCEL, prompt template, streaming |
| 07 | [Chat API & SSE](./07-chat-api-sse.md) | `backend/src/api/routes/chat.py:53` | FastAPI, SSE, StreamingResponse |
| 08 | [LangGraph Agents](./08-langgraph-agents.md) | `backend/src/agents/graph.py:56` | State machine, nodes, conditional edges, tools |
| 09 | [Kubernetes + k3s](./09-kubernetes.md) | `k8s/api/deployment.yml` | Manifests, StatefulSet, HPA, Helm chart |
| 10 | [Monitoring & Observability](./10-monitoring.md) | `backend/src/observability/metrics.py:49` | Prometheus, Grafana, Langfuse LLM tracing |

---

> Mỗi bài có: **Khái niệm → Code thực tế → Tại sao làm vậy → Thử nghiệm ngay**
