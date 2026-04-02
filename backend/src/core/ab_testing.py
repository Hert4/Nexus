"""
core/ab_testing.py — A/B testing framework cho model parameters.

Randomly assigns requests vào variants, track outcomes cho comparison.
Dùng để compare temperature configs, system prompts, hay model params.

Usage:
    from src.core.ab_testing import ab_router

    # Trong chat endpoint:
    variant = ab_router.assign(session_id="user-123", experiment="temperature")
    params = variant.params
    # ... dùng params để gọi LLM ...
    ab_router.record_outcome(variant.assignment_id, score=0.85)

    # Xem results:
    report = ab_router.get_report("temperature")
"""

import os
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_DATA = Path(os.environ.get("NEXUS_DATA_DIR", "/app/data"))
DB_PATH = _DEFAULT_DATA / "ab_testing.db"


@dataclass
class Variant:
    """Một variant trong A/B experiment."""

    name: str  # "control" | "treatment_a" | ...
    params: dict  # LLM params override: {"temperature": 0.5, ...}
    weight: float = 0.5  # sampling weight (0–1)


@dataclass
class Assignment:
    """Kết quả phân công variant cho 1 request."""

    assignment_id: str
    experiment: str
    variant_name: str
    params: dict
    session_id: str


# Predefined experiments
EXPERIMENTS: dict[str, list[Variant]] = {
    # So sánh temperature cao vs thấp
    "temperature": [
        Variant("control", {"temperature": 0.7}, weight=0.5),
        Variant("low_temp", {"temperature": 0.3}, weight=0.5),
    ],
    # So sánh max_tokens
    "context_length": [
        Variant("control", {"max_tokens": 1024}, weight=0.5),
        Variant("extended", {"max_tokens": 2048}, weight=0.5),
    ],
    # System prompt variants
    "system_prompt": [
        Variant("default", {"system": "You are a helpful assistant."}, weight=0.5),
        Variant(
            "concise",
            {"system": "You are a concise, precise assistant. Give short answers."},
            weight=0.5,
        ),
    ],
}


class ABRouter:
    """
    A/B testing router — assign variants và track outcomes.

    Storage: SQLite (cùng data/ dir với eval dataset).
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS ab_assignments (
                    id           TEXT PRIMARY KEY,
                    experiment   TEXT NOT NULL,
                    variant      TEXT NOT NULL,
                    session_id   TEXT,
                    created_at   INTEGER
                );
                CREATE TABLE IF NOT EXISTS ab_outcomes (
                    assignment_id TEXT NOT NULL,
                    score         REAL,
                    feedback      INTEGER,  -- 1-5 rating nếu có
                    recorded_at   INTEGER,
                    PRIMARY KEY (assignment_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ab_exp ON ab_assignments(experiment);
            """)

    def assign(
        self,
        experiment: str,
        session_id: str = "",
    ) -> Assignment:
        """
        Assign variant cho 1 request.

        Nếu experiment không tồn tại → trả về control với empty params.
        Sticky assignment: cùng session_id → cùng variant (trong 24h).
        """
        variants = EXPERIMENTS.get(experiment)
        if not variants:
            logger.debug("Unknown experiment, using control", experiment=experiment)
            return Assignment(
                assignment_id=str(uuid.uuid4()),
                experiment=experiment,
                variant_name="control",
                params={},
                session_id=session_id,
            )

        # Sticky: check if session already assigned
        if session_id:
            with self._conn() as conn:
                row = conn.execute(
                    """SELECT variant FROM ab_assignments
                       WHERE experiment=? AND session_id=?
                         AND created_at > ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (experiment, session_id, int(time.time()) - 86400),
                ).fetchone()
                if row:
                    variant_name = row["variant"]
                    variant = next((v for v in variants if v.name == variant_name), variants[0])
                    return Assignment(
                        assignment_id=str(uuid.uuid4()),
                        experiment=experiment,
                        variant_name=variant.name,
                        params=variant.params,
                        session_id=session_id,
                    )

        # Weighted random assignment
        total = sum(v.weight for v in variants)
        r = random.random() * total  # noqa: S311
        cumulative = 0.0
        chosen = variants[0]
        for v in variants:
            cumulative += v.weight
            if r <= cumulative:
                chosen = v
                break

        assignment_id = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ab_assignments "
                "(id, experiment, variant, session_id, created_at) "
                "VALUES (?,?,?,?,?)",
                (assignment_id, experiment, chosen.name, session_id, int(time.time())),
            )

        logger.debug("AB assignment", experiment=experiment, variant=chosen.name)
        return Assignment(
            assignment_id=assignment_id,
            experiment=experiment,
            variant_name=chosen.name,
            params=chosen.params,
            session_id=session_id,
        )

    def record_outcome(
        self,
        assignment_id: str,
        score: float | None = None,
        feedback: int | None = None,
    ) -> None:
        """
        Record outcome cho 1 assignment.

        Args:
            assignment_id: Từ Assignment.assignment_id
            score: Eval score (0–1) nếu có
            feedback: User rating (1–5) nếu có
        """
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ab_outcomes "
                "(assignment_id, score, feedback, recorded_at) "
                "VALUES (?,?,?,?)",
                (assignment_id, score, feedback, int(time.time())),
            )

    def get_report(self, experiment: str) -> dict:
        """
        Báo cáo kết quả experiment: mean score + feedback per variant.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT a.variant,
                          COUNT(*) as n,
                          AVG(o.score) as avg_score,
                          AVG(o.feedback) as avg_feedback,
                          SUM(CASE WHEN o.score IS NOT NULL THEN 1 ELSE 0 END) as scored
                   FROM ab_assignments a
                   LEFT JOIN ab_outcomes o ON o.assignment_id = a.id
                   WHERE a.experiment = ?
                   GROUP BY a.variant""",
                (experiment,),
            ).fetchall()

        results = {}
        for row in rows:
            results[row["variant"]] = {
                "n": row["n"],
                "avg_score": round(row["avg_score"], 4) if row["avg_score"] else None,
                "avg_feedback": round(row["avg_feedback"], 2) if row["avg_feedback"] else None,
                "scored": row["scored"],
            }

        return {"experiment": experiment, "variants": results}


# Singleton
ab_router = ABRouter()
