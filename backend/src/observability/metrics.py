"""
observability/metrics.py — Prometheus metrics cho FastAPI.

Dùng prometheus-fastapi-instrumentator để auto-instrument tất cả routes,
thêm custom metrics cho LLM latency và RAG retrieval.

Endpoint: GET /metrics → Prometheus scrape format
"""

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# ── Custom metrics ─────────────────────────────────────────────────────────────

llm_requests_total = Counter(
    "nexus_llm_requests_total",
    "Total LLM requests",
    ["model", "type"],  # type: stream | complete
)

llm_latency_seconds = Histogram(
    "nexus_llm_latency_seconds",
    "LLM response latency",
    ["model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

rag_retrieval_latency_seconds = Histogram(
    "nexus_rag_retrieval_latency_seconds",
    "RAG retrieval latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

documents_ingested_total = Counter(
    "nexus_documents_ingested_total",
    "Total documents ingested",
)

chunks_ingested_total = Counter(
    "nexus_chunks_ingested_total",
    "Total chunks ingested into vector store",
)

active_requests = Gauge(
    "nexus_active_requests",
    "Currently active HTTP requests",
)

agent_task_duration_seconds = Histogram(
    "nexus_agent_task_duration_seconds",
    "Agent node execution duration",
    ["node"],  # node: planner, researcher, coder, reviewer
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120],
)

agent_tasks_total = Counter(
    "nexus_agent_tasks_total",
    "Total agent tasks run",
    ["status"],  # status: success, retry, error
)


def setup_metrics(app) -> None:
    """
    Instrument FastAPI app với Prometheus metrics.
    Expose /metrics endpoint cho Prometheus scrape.
    """
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/metrics"],
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
