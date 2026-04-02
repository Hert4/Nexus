"""
api/routes/feedback.py — User feedback + eval endpoints.

POST /v1/feedback           — Submit rating/comment cho 1 response
GET  /v1/feedback/stats     — Tổng hợp feedback stats
POST /v1/eval/run           — Trigger eval run (async)
GET  /v1/eval/results/{id}  — Xem kết quả eval run
GET  /v1/ab/report/{exp}    — A/B experiment report
"""

import asyncio
import time
import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.core.ab_testing import ab_router
from src.eval.dataset import EvalDataset

logger = structlog.get_logger(__name__)
router = APIRouter()

# In-memory store cho eval run results (production → Redis/DB)
_eval_runs: dict[str, dict] = {}


# ── Pydantic models ────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="ID của message cần feedback")
    rating: int = Field(..., ge=1, le=5, description="Rating 1–5")
    comment: str = Field("", max_length=1000, description="Optional comment")
    query: str = Field("", description="Original query — để auto-expand eval dataset")
    response: str = Field("", description="LLM response được rated")
    assignment_id: str = Field("", description="A/B assignment ID nếu có")


class FeedbackResponse(BaseModel):
    feedback_id: str
    message: str = "Feedback recorded"


class EvalRunRequest(BaseModel):
    category: str | None = Field(None, description="factual|reasoning|code hoặc None cho tất cả")
    limit: int = Field(0, ge=0, le=50, description="Max cases (0 = all)")
    concurrency: int = Field(3, ge=1, le=5)


class EvalRunResponse(BaseModel):
    run_id: str
    status: str = "started"
    n_cases: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(req: FeedbackRequest):
    """
    Submit user feedback cho 1 LLM response.

    - Lưu vào SQLite feedback table
    - Nếu rating <= 2 + có query/response → auto-add vào eval dataset
    - Nếu có assignment_id → record A/B outcome
    """
    feedback_id = str(uuid.uuid4())[:8]
    db = EvalDataset()

    logger.info("Feedback received",
                feedback_id=feedback_id,
                rating=req.rating,
                message_id=req.message_id[:20])

    # Record A/B outcome nếu có
    if req.assignment_id:
        # Convert rating 1-5 → score 0-1
        score = (req.rating - 1) / 4.0
        ab_router.record_outcome(
            assignment_id=req.assignment_id,
            feedback=req.rating,
            score=score,
        )

    # Auto-expand eval dataset từ bad responses (rating <= 2)
    if req.rating <= 2 and req.query and req.response:
        logger.info("Low-rating response added to eval dataset",
                    rating=req.rating, query=req.query[:60])
        db.add_case(
            query=req.query,
            expected="[From user feedback — needs review]",
            category="feedback",
        )

    return FeedbackResponse(feedback_id=feedback_id)


@router.get("/feedback/stats")
async def feedback_stats():
    """
    Tổng hợp feedback statistics từ A/B experiments.
    """
    reports = {}
    for exp in ("temperature", "context_length", "system_prompt"):
        reports[exp] = ab_router.get_report(exp)

    db = EvalDataset()
    cases = db.get_cases()
    feedback_cases = [c for c in cases if c.get("category") == "feedback"]

    return {
        "total_eval_cases": len(cases),
        "feedback_cases": len(feedback_cases),
        "ab_experiments": reports,
    }


@router.post("/eval/run", response_model=EvalRunResponse)
async def run_eval(req: EvalRunRequest, background_tasks: BackgroundTasks):
    """
    Trigger eval run trong background.
    Trả về run_id ngay để poll status.
    """
    from src.config import settings
    from src.eval.evaluator import Evaluator

    db = EvalDataset()
    cases = db.get_cases(category=req.category, limit=req.limit)

    if not cases:
        raise HTTPException(404, "No eval cases found")

    run_id = str(uuid.uuid4())[:8]
    _eval_runs[run_id] = {"status": "running", "started_at": time.time()}

    async def _run():
        try:
            ev = Evaluator()
            result = await ev.run_full_eval(
                category=req.category,
                limit=req.limit,
                model=settings.gguf_chat_model,
                concurrency=req.concurrency,
            )
            _eval_runs[run_id] = {
                "status": "done",
                "result": result,
                "finished_at": time.time(),
            }
        except Exception as e:
            logger.error("Eval run failed", run_id=run_id, error=str(e))
            _eval_runs[run_id] = {"status": "error", "error": str(e)}

    background_tasks.add_task(asyncio.create_task, _run())

    return EvalRunResponse(run_id=run_id, n_cases=len(cases))


@router.get("/eval/results/{run_id}")
async def get_eval_results(run_id: str):
    """Poll kết quả eval run."""
    result = _eval_runs.get(run_id)
    if not result:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return result


@router.get("/ab/report/{experiment}")
async def ab_report(experiment: str):
    """A/B experiment report."""
    return ab_router.get_report(experiment)
