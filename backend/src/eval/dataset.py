"""
eval/dataset.py — Eval dataset management dùng SQLite.

Lưu trữ test cases và kết quả evaluation theo thời gian.
Schema: eval_cases, eval_results

Usage:
    from src.eval.dataset import EvalDataset
    db = EvalDataset()
    cases = db.get_cases(category="factual")
    db.save_result(case_id=1, scores={...}, model="Qwen3.5-9B")
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import structlog

logger = structlog.get_logger(__name__)

# SQLite file — /app/data trong container, hoặc project root trên host
# NEXUS_DATA_DIR env var để override (K8s dùng PVC)
_DEFAULT_DATA = Path(os.environ.get("NEXUS_DATA_DIR", "/app/data"))
DB_PATH = _DEFAULT_DATA / "eval.db"


SEED_CASES = [
    # ── Factual ────────────────────────────────────────────────────────────────
    {"query": "What is RAG in the context of LLMs?",
     "expected": "RAG stands for Retrieval-Augmented Generation",
     "category": "factual"},
    {"query": "What is the difference between dense and sparse retrieval?",
     "expected": "Dense retrieval uses vector embeddings; sparse uses keyword matching like BM25",
     "category": "factual"},
    {"query": "What is LangGraph used for?",
     "expected": "LangGraph is a library for building stateful, multi-step LLM applications as graphs",
     "category": "factual"},
    {"query": "What does GGUF stand for?",
     "expected": "GGUF is a file format for LLM weights used by llama.cpp",
     "category": "factual"},
    {"query": "What is a vector database?",
     "expected": "A vector database stores and retrieves high-dimensional vectors for similarity search",
     "category": "factual"},
    {"query": "What is Qdrant?",
     "expected": "Qdrant is an open-source vector database with hybrid search support",
     "category": "factual"},
    {"query": "What is the purpose of embeddings in NLP?",
     "expected": "Embeddings convert text into dense numerical vectors capturing semantic meaning",
     "category": "factual"},
    {"query": "What is prompt injection?",
     "expected": "Prompt injection is an attack where malicious input hijacks LLM behavior",
     "category": "factual"},
    {"query": "What is quantization in LLMs?",
     "expected": "Quantization reduces model weight precision to decrease memory usage and increase speed",
     "category": "factual"},
    {"query": "What is the context window in LLMs?",
     "expected": "The context window is the maximum number of tokens an LLM can process at once",
     "category": "factual"},
    {"query": "What is Kubernetes?",
     "expected": "Kubernetes is an open-source container orchestration platform",
     "category": "factual"},
    {"query": "What is Helm in Kubernetes?",
     "expected": "Helm is a package manager for Kubernetes that manages chart deployments",
     "category": "factual"},
    {"query": "What is a StatefulSet in Kubernetes?",
     "expected": "A StatefulSet manages pods with persistent identity and stable storage",
     "category": "factual"},
    {"query": "What is Prometheus?",
     "expected": "Prometheus is an open-source monitoring and alerting toolkit",
     "category": "factual"},
    {"query": "What is Grafana?",
     "expected": "Grafana is an open-source platform for monitoring and observability dashboards",
     "category": "factual"},

    # ── Reasoning ─────────────────────────────────────────────────────────────
    {"query": "Why use hybrid search instead of dense-only retrieval?",
     "expected": "Hybrid search combines semantic and keyword matching for better coverage of both meaning and exact terms",
     "category": "reasoning"},
    {"query": "Why run LLMs locally instead of using cloud APIs?",
     "expected": "Local LLMs offer privacy, no API costs, no latency from network, and full control",
     "category": "reasoning"},
    {"query": "What are the tradeoffs of chunking documents into smaller pieces?",
     "expected": "Smaller chunks improve precision but lose context; larger chunks keep context but reduce precision",
     "category": "reasoning"},
    {"query": "Why use StatefulSet instead of Deployment for databases in Kubernetes?",
     "expected": "StatefulSet provides stable network identity and persistent storage order, essential for databases",
     "category": "reasoning"},
    {"query": "Why is temperature set lower for code generation?",
     "expected": "Lower temperature makes output more deterministic, reducing random syntax errors in generated code",
     "category": "reasoning"},
    {"query": "What are the benefits of using LangGraph over simple LLM chains?",
     "expected": "LangGraph enables stateful multi-step workflows with branching, loops, and conditional logic",
     "category": "reasoning"},
    {"query": "Why use RRF (Reciprocal Rank Fusion) for combining search results?",
     "expected": "RRF combines rankings from multiple sources without requiring score normalization",
     "category": "reasoning"},
    {"query": "When should you use streaming responses vs. batch responses?",
     "expected": "Streaming provides faster time-to-first-token UX; batch is simpler for programmatic use",
     "category": "reasoning"},
    {"query": "Why use pydantic-settings for configuration instead of os.environ?",
     "expected": "pydantic-settings provides type validation, default values, and structured config objects",
     "category": "reasoning"},
    {"query": "What is the purpose of the reviewer node in the agent graph?",
     "expected": "The reviewer evaluates output quality and decides whether to accept or retry with more research",
     "category": "reasoning"},
    {"query": "Why use nomic-embed-text for embeddings instead of OpenAI embeddings?",
     "expected": "nomic-embed-text runs locally with no API costs and produces 768-dim vectors suitable for semantic search",
     "category": "reasoning"},
    {"query": "What is the advantage of using SSE over WebSockets for streaming chat?",
     "expected": "SSE is simpler (HTTP), unidirectional, automatic reconnect, works through proxies; WebSocket needed for bi-directional",
     "category": "reasoning"},
    {"query": "Why use structlog instead of Python's built-in logging?",
     "expected": "structlog provides structured JSON logging with context binding, better for observability pipelines",
     "category": "reasoning"},
    {"query": "What is the benefit of LLM-as-judge for evaluation?",
     "expected": "LLM-as-judge scales evaluation without expensive human annotation, though it has its own biases",
     "category": "reasoning"},
    {"query": "Why store eval results in SQLite instead of a file?",
     "expected": "SQLite enables querying, filtering by date/category, and tracking metrics over time without a separate DB server",
     "category": "reasoning"},

    # ── Code ──────────────────────────────────────────────────────────────────
    {"query": "Write a Python function to calculate fibonacci(n) iteratively",
     "expected": "def fibonacci(n):\\n    a, b = 0, 1\\n    for _ in range(n): a, b = b, a+b\\n    return a",
     "category": "code"},
    {"query": "Write a Python async function to fetch JSON from a URL using httpx",
     "expected": "async def fetch_json(url): async with httpx.AsyncClient() as c: r = await c.get(url); return r.json()",
     "category": "code"},
    {"query": "Write a Python context manager that measures execution time",
     "expected": "import time; class Timer: def __enter__(self): self.start=time.perf_counter(); return self; def __exit__(self,...): self.elapsed=time.perf_counter()-self.start",
     "category": "code"},
    {"query": "Write a Python function to chunk a list into batches of size n",
     "expected": "def batch(lst, n): return [lst[i:i+n] for i in range(0, len(lst), n)]",
     "category": "code"},
    {"query": "Write a Python decorator that retries a function up to 3 times on exception",
     "expected": "def retry(fn): def wrapper(*a,**k): for i in range(3):\\n    try: return fn(*a,**k)\\n    except Exception: if i==2: raise; return wrapper",
     "category": "code"},
    {"query": "Write a Python dataclass for a document with title, content, and metadata fields",
     "expected": "@dataclass class Document: title: str; content: str; metadata: dict = field(default_factory=dict)",
     "category": "code"},
    {"query": "Write a Python function to flatten a nested list",
     "expected": "def flatten(lst): return [x for sub in lst for x in (flatten(sub) if isinstance(sub, list) else [sub])]",
     "category": "code"},
    {"query": "Write Python code to read a JSONL file line by line",
     "expected": "with open('file.jsonl') as f: records = [json.loads(line) for line in f]",
     "category": "code"},
    {"query": "Write a FastAPI endpoint that returns a list of items",
     "expected": "@app.get('/items') async def list_items() -> list[dict]: return [{'id': 1, 'name': 'item'}]",
     "category": "code"},
    {"query": "Write Python code to compute cosine similarity between two vectors",
     "expected": "import numpy as np; def cosine_sim(a, b): return np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b))",
     "category": "code"},
    {"query": "Write a Python generator that yields chunks of a string",
     "expected": "def chunks(s, n): yield from (s[i:i+n] for i in range(0, len(s), n))",
     "category": "code"},
    {"query": "Write Python code to parse command-line arguments with argparse",
     "expected": "import argparse; p = argparse.ArgumentParser(); p.add_argument('--input'); args = p.parse_args()",
     "category": "code"},

    # ── Mixed / Edge cases ────────────────────────────────────────────────────
    {"query": "What is 2 to the power of 10?",
     "expected": "1024",
     "category": "factual"},
    {"query": "What is the capital of France?",
     "expected": "Paris",
     "category": "factual"},
    {"query": "How many bytes in a megabyte?",
     "expected": "1048576 bytes (2^20) or 1000000 bytes (SI definition)",
     "category": "factual"},
    {"query": "Explain what Docker does in one sentence",
     "expected": "Docker packages applications and dependencies into containers for consistent, portable deployment",
     "category": "factual"},
    {"query": "What is the time complexity of binary search?",
     "expected": "O(log n)",
     "category": "factual"},
    {"query": "What is a p99 latency?",
     "expected": "p99 latency is the 99th percentile response time — 99% of requests complete within this duration",
     "category": "factual"},
    {"query": "What does REST stand for?",
     "expected": "Representational State Transfer",
     "category": "factual"},
    {"query": "What is the difference between async and sync in Python?",
     "expected": "Async uses an event loop for non-blocking I/O; sync blocks execution until each operation completes",
     "category": "reasoning"},
]


class EvalDataset:
    """
    SQLite-backed eval dataset.

    Tables:
      eval_cases   — test cases (query, expected, category)
      eval_results — scored results per run (case_id, model, scores, timestamp)
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and seed if empty."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS eval_cases (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    query    TEXT NOT NULL,
                    expected TEXT NOT NULL,
                    category TEXT NOT NULL,
                    active   INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS eval_results (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id         INTEGER NOT NULL,
                    model           TEXT NOT NULL,
                    actual_answer   TEXT,
                    score_completion REAL,
                    score_quality    REAL,
                    score_faithful   REAL,
                    score_avg        REAL,
                    latency_s        REAL,
                    judge_raw        TEXT,
                    run_id          TEXT,
                    created_at      INTEGER,
                    FOREIGN KEY (case_id) REFERENCES eval_cases(id)
                );

                CREATE INDEX IF NOT EXISTS idx_results_run ON eval_results(run_id);
                CREATE INDEX IF NOT EXISTS idx_results_model ON eval_results(model);
                CREATE INDEX IF NOT EXISTS idx_results_ts ON eval_results(created_at);
            """)
            # Seed nếu chưa có cases
            count = conn.execute("SELECT COUNT(*) FROM eval_cases").fetchone()[0]
            if count == 0:
                conn.executemany(
                    "INSERT INTO eval_cases (query, expected, category) VALUES (?,?,?)",
                    [(c["query"], c["expected"], c["category"]) for c in SEED_CASES],
                )
                logger.info("Seeded eval dataset", count=len(SEED_CASES))

    def get_cases(self, category: str | None = None, limit: int = 0) -> list[dict]:
        """Lấy test cases, optionally filtered by category."""
        with self._conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM eval_cases WHERE active=1 AND category=? ORDER BY id",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM eval_cases WHERE active=1 ORDER BY id"
                ).fetchall()
        result = [dict(r) for r in rows]
        return result[:limit] if limit else result

    def add_case(self, query: str, expected: str, category: str) -> int:
        """Thêm test case mới (từ user interaction)."""
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO eval_cases (query, expected, category) VALUES (?,?,?)",
                (query, expected, category),
            )
            case_id = cur.lastrowid
        logger.info("Added eval case", id=case_id, category=category)
        return case_id

    def save_result(
        self,
        case_id: int,
        model: str,
        actual_answer: str,
        scores: dict[str, float],
        latency_s: float,
        judge_raw: str = "",
        run_id: str = "",
    ) -> None:
        """Lưu kết quả 1 eval run."""
        avg = sum(scores.values()) / len(scores) if scores else 0.0
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO eval_results
                   (case_id, model, actual_answer,
                    score_completion, score_quality, score_faithful, score_avg,
                    latency_s, judge_raw, run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case_id, model, actual_answer,
                    scores.get("completion", 0.0),
                    scores.get("quality", 0.0),
                    scores.get("faithfulness", 0.0),
                    avg,
                    latency_s, judge_raw, run_id,
                    int(time.time()),
                ),
            )

    def get_run_summary(self, run_id: str) -> dict:
        """Tổng hợp kết quả 1 run_id."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ec.category,
                          AVG(er.score_completion) as completion,
                          AVG(er.score_quality)    as quality,
                          AVG(er.score_faithful)   as faithfulness,
                          AVG(er.score_avg)        as avg,
                          AVG(er.latency_s)        as latency,
                          COUNT(*)                 as n
                   FROM eval_results er
                   JOIN eval_cases ec ON ec.id = er.case_id
                   WHERE er.run_id = ?
                   GROUP BY ec.category""",
                (run_id,),
            ).fetchall()
        return {"run_id": run_id, "by_category": [dict(r) for r in rows]}

    def get_trend(self, model: str, days: int = 30) -> list[dict]:
        """Lấy avg scores theo ngày trong N ngày gần nhất."""
        since = int(time.time()) - days * 86400
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT date(created_at, 'unixepoch', 'localtime') as day,
                          AVG(score_avg) as avg_score,
                          COUNT(*) as n
                   FROM eval_results
                   WHERE model=? AND created_at >= ?
                   GROUP BY day ORDER BY day""",
                (model, since),
            ).fetchall()
        return [dict(r) for r in rows]
