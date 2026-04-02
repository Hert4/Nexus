# Bài 10 — Monitoring & Observability

**Code**: [`backend/src/observability/`](../../backend/src/observability/) | [`monitoring/`](../../monitoring/) | [`docker-compose.monitoring.yml`](../../docker-compose.monitoring.yml)

---

## Vấn đề cần giải quyết

Production AI system cần biết:
- **Request latency**: LLM call mất bao lâu? p50/p95 bao nhiêu?
- **Errors**: Agent có retry nhiều không? Retrieval có fail không?
- **LLM traces**: Prompt nào gây latency cao? Token count bao nhiêu?
- **Business metrics**: Bao nhiêu docs ingested? Bao nhiêu agent tasks/ngày?

3 layer observability: **Prometheus** (metrics) → **Grafana** (dashboards) → **Langfuse** (LLM traces).

---

## 1. Prometheus Metrics — [`observability/metrics.py`](../../backend/src/observability/metrics.py)

```python
# metrics.py:15 — LLM request counter (label: model, type)
llm_requests_total = Counter(
    "nexus_llm_requests_total", "Total LLM requests",
    ["model", "type"],   # type: stream | complete
)

# metrics.py:21 — LLM latency histogram
llm_latency_seconds = Histogram(
    "nexus_llm_latency_seconds", "LLM response latency",
    ["model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

# metrics.py:28 — RAG retrieval latency
rag_retrieval_latency_seconds = Histogram(
    "nexus_rag_retrieval_latency_seconds", "RAG retrieval latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

# metrics.py:49 — Agent node duration (mới thêm Phase 3)
agent_task_duration_seconds = Histogram(
    "nexus_agent_task_duration_seconds", "Agent node execution duration",
    ["node"],   # node: planner, researcher, coder, reviewer
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120],
)
```

Auto-expose `/metrics` endpoint qua `prometheus-fastapi-instrumentator`:
```python
# metrics.py:55
Instrumentator(...).instrument(app).expose(app, endpoint="/metrics")
```

---

## 2. Scrape config — [`monitoring/prometheus.yml`](../../monitoring/prometheus.yml)

```yaml
scrape_configs:
  - job_name: nexus-api          # monitoring/prometheus.yml:18
    static_configs:
      - targets: ["nexus-api:8000"]
    metrics_path: /metrics

  - job_name: qdrant             # monitoring/prometheus.yml:24
    static_configs:
      - targets: ["nexus-qdrant:6333"]
    metrics_path: /metrics
```

Trong K8s: Prometheus dùng `kubernetes_sd_configs` + annotations để **auto-discover** pods:
```yaml
# k8s/monitoring/prometheus-configmap.yml:16
kubernetes_sd_configs:
  - role: pod
relabel_configs:
  - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
    action: keep
    regex: "true"
```

---

## 3. Grafana Dashboard — [`monitoring/grafana/dashboards/nexus-overview.json`](../../monitoring/grafana/dashboards/nexus-overview.json)

Dashboard provisioned tự động — không cần config thủ công. 4 sections:

| Section | Panels |
|---------|--------|
| HTTP Requests | Request rate, latency p50/p95 |
| LLM Metrics | LLM latency p50/p95, request rate theo model |
| RAG & Agents | Retrieval latency, agent node duration |
| Documents & System | Docs ingested, chunks count, active requests |

Provisioning config:
```yaml
# monitoring/grafana/provisioning/dashboards/nexus.yml:7
providers:
  - name: nexus-ai
    type: file
    options:
      path: /var/lib/grafana/dashboards   # mount từ local directory
```

---

## 4. Chạy monitoring local — [`docker-compose.monitoring.yml`](../../docker-compose.monitoring.yml)

```bash
# Tạo shared network trước (nexus-api và qdrant cần cùng network)
make monitor-up
# → Prometheus: http://localhost:9090
# → Grafana:    http://localhost:3001  (admin/admin)
```

`docker-compose.monitoring.yml` dùng `nexus-network` — cùng network với `docker-compose.yml` để reach `nexus-api` và `nexus-qdrant` containers.

---

## 5. Langfuse LLM Tracing — [`observability/langfuse_client.py`](../../backend/src/observability/langfuse_client.py)

Langfuse trace từng LLM call: model, prompt, completion, token count, latency.

### get_langfuse_callback — [`langfuse_client.py:34`](../../backend/src/observability/langfuse_client.py#L34)

```python
def get_langfuse_callback():
    """Trả về LangChain callback handler nếu đã config, None nếu chưa."""
    host = getattr(settings, "langfuse_host", None)
    public_key = getattr(settings, "langfuse_public_key", None)
    # ...

    from langfuse.callback import CallbackHandler  # langfuse_client.py:50
    handler = CallbackHandler(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )
    return handler
```

**Graceful degradation** — nếu Langfuse chưa cài hoặc chưa config, hàm trả về `None` và app chạy bình thường.

### TraceContext — [`langfuse_client.py:66`](../../backend/src/observability/langfuse_client.py#L66)

```python
class TraceContext:
    """Context manager để trace agent run thủ công."""

    async def __aenter__(self):
        self._start = time.perf_counter()
        # Tạo Langfuse trace nếu đã config
        lf = Langfuse(...)              # langfuse_client.py:92
        self._trace = lf.trace(name=self.name, metadata=self.metadata)
        return self
```

Usage trong agent:
```python
async with TraceContext("agent_run", task=req.task) as ctx:
    result = await agent_graph.ainvoke(state)
    ctx.set_output(result)
```

---

## 6. Config Langfuse — [`config.py:50`](../../backend/src/config.py#L50)

```python
# config.py:50 — optional fields, để trống để disable
langfuse_host: str = ""
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
```

Thêm vào `.env` sau khi tạo account Langfuse:
```bash
LANGFUSE_HOST=http://localhost:3002   # hoặc cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

---

## 7. Prometheus queries hữu ích

```promql
# LLM latency p95 theo model (5 phút)
histogram_quantile(0.95,
  sum(rate(nexus_llm_latency_seconds_bucket[5m])) by (le, model)
)

# Request rate tổng
sum(rate(http_requests_total{job="nexus-api"}[2m]))

# Agent node chậm nhất
histogram_quantile(0.95,
  sum(rate(nexus_agent_task_duration_seconds_bucket[5m])) by (le, node)
)

# Số docs ingested theo thời gian
increase(nexus_documents_ingested_total[1h])
```

---

## Thử ngay

```bash
# 1. Khởi động monitoring
make monitor-up

# 2. Gửi vài requests để có data
curl -X POST http://localhost:8000/v1/agents/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Calculate fibonacci(15) with Python"}'

# 3. Xem Prometheus targets
open http://localhost:9090/targets
# → nexus-api (1/1 up), qdrant (1/1 up)

# 4. Query metrics
open http://localhost:9090/graph
# Thử: nexus_llm_requests_total

# 5. Grafana dashboard
open http://localhost:3001
# Login: admin/admin → Dashboards → Nexus AI → Nexus AI Overview

# 6. Langfuse (sau khi chạy k8s-deploy --langfuse)
open http://NODE_IP:30302
# Tạo project → lấy keys → thêm vào .env
```

---

**Bài trước**: [09 — Kubernetes + k3s](./09-kubernetes.md)

**Tiếp theo**: Phase 4 — Evaluation + Feedback loop (`docs/lessons/11-evaluation.md`)
