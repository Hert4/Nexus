"""
eval/evaluator.py — LLM-as-judge evaluation framework.

3-axis scoring:
  1. Task Completion  (0–1): Có trả lời đúng câu hỏi không?
  2. Quality          (0–1): Coherent, well-structured, cited sources?
  3. Faithfulness     (0–1): Response grounded trong retrieved context?

Multi-judge consensus: chạy LLM judge 3 lần, lấy mean scores.

Usage:
    from src.eval.evaluator import Evaluator
    ev = Evaluator()
    scores = await ev.judge(
        query="What is RAG?",
        expected="RAG stands for Retrieval-Augmented Generation",
        actual="RAG means Retrieval-Augmented Generation, a technique...",
    )
    # → {"completion": 0.9, "quality": 0.85, "faithfulness": 0.8}
"""

import asyncio
import re
import time
import uuid

import structlog

from src.core.llm import LLMClient
from src.eval.dataset import EvalDataset
from src.eval.metrics import summarize_scores

logger = structlog.get_logger(__name__)

# Số lần judge mỗi case (multi-judge consensus)
N_JUDGES = 3

JUDGE_PROMPT = """You are an expert evaluator for AI-generated answers. Score the response on three axes.

QUESTION: {query}
EXPECTED ANSWER (reference): {expected}
ACTUAL ANSWER (to evaluate): {actual}

Score each axis from 0.0 to 1.0:

1. COMPLETION: Does the actual answer directly address the question?
   - 1.0 = fully answers the question
   - 0.5 = partially answers
   - 0.0 = doesn't answer or completely wrong

2. QUALITY: Is the answer well-structured, clear, and appropriately detailed?
   - 1.0 = excellent clarity, structure, and depth
   - 0.5 = adequate but could be better
   - 0.0 = confusing, very poor quality

3. FAITHFULNESS: Is the answer factually consistent with the expected answer?
   - 1.0 = fully consistent, no contradictions
   - 0.5 = mostly consistent, minor deviations
   - 0.0 = contradicts the expected answer or hallucinates

Respond in EXACTLY this format (no other text):
COMPLETION: <score>
QUALITY: <score>
FAITHFULNESS: <score>"""


def _parse_scores(text: str) -> dict[str, float] | None:
    """Parse LLM judge output → scores dict. Returns None nếu parse fail."""
    scores = {}
    for key in ("completion", "quality", "faithfulness"):
        pattern = rf"{key.upper()}:\s*([0-9.]+)"
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return None
        try:
            val = float(m.group(1))
            scores[key] = max(0.0, min(1.0, val))  # clamp 0–1
        except ValueError:
            return None
    return scores


class Evaluator:
    """
    LLM-as-judge evaluator với multi-judge consensus.

    Chạy N_JUDGES=3 lần judge, lấy mean scores.
    Dùng temperature=0.1 cho deterministic scoring.
    """

    def __init__(self):
        self.llm = LLMClient()
        self.db = EvalDataset()

    async def judge_once(
        self,
        query: str,
        expected: str,
        actual: str,
    ) -> tuple[dict[str, float] | None, str]:
        """1 lần judge. Returns (scores_or_None, raw_text)."""
        prompt = JUDGE_PROMPT.format(
            query=query, expected=expected, actual=actual
        )
        try:
            raw = await self.llm.chat(
                prompt=prompt,
                system="You are a precise evaluator. Follow the format exactly.",
                temperature=0.1,
                max_tokens=100,
            )
            scores = _parse_scores(raw)
            return scores, raw
        except Exception as e:
            logger.warning("Judge call failed", error=str(e))
            return None, ""

    async def judge(
        self,
        query: str,
        expected: str,
        actual: str,
        n_judges: int = N_JUDGES,
    ) -> dict[str, float]:
        """
        Multi-judge consensus: chạy N judges song song, lấy mean.

        Returns:
            {"completion": float, "quality": float, "faithfulness": float}
        """
        tasks = [self.judge_once(query, expected, actual) for _ in range(n_judges)]
        results = await asyncio.gather(*tasks)

        valid_scores = [s for s, _ in results if s is not None]

        if not valid_scores:
            logger.warning("All judges failed, returning 0s")
            return {"completion": 0.0, "quality": 0.0, "faithfulness": 0.0}

        # Mean of valid scores
        consensus: dict[str, float] = {}
        for key in ("completion", "quality", "faithfulness"):
            vals = [s[key] for s in valid_scores]
            consensus[key] = sum(vals) / len(vals)

        return consensus

    async def run_case(
        self,
        case: dict,
        model: str,
        run_id: str,
    ) -> dict:
        """
        Eval 1 test case end-to-end: generate answer → judge → save.

        Args:
            case: Dict với keys: id, query, expected, category
            model: Model name (cho logging)
            run_id: Unique run identifier

        Returns:
            Result dict với scores + latency
        """
        from src.rag.chain import RAGChain  # local import để tránh circular

        query = case["query"]
        expected = case["expected"]

        t0 = time.perf_counter()

        # Generate actual answer
        try:
            chain = RAGChain()
            result = await chain.retrieve_with_answer(query)
            actual = result.get("answer", "")
        except Exception as e:
            logger.warning("RAG chain failed in eval", error=str(e))
            actual = ""

        latency = time.perf_counter() - t0

        # Judge
        scores = await self.judge(query=query, expected=expected, actual=actual)

        # Save
        self.db.save_result(
            case_id=case["id"],
            model=model,
            actual_answer=actual,
            scores=scores,
            latency_s=latency,
            run_id=run_id,
        )

        return {
            "case_id": case["id"],
            "category": case.get("category", ""),
            "query": query[:80],
            "score_completion":  scores["completion"],
            "score_quality":     scores["quality"],
            "score_faithful":    scores["faithfulness"],
            "score_avg": sum(scores.values()) / 3,
            "latency_s":         latency,
        }

    async def run_full_eval(
        self,
        category: str | None = None,
        limit: int = 0,
        model: str = "Qwen3.5-9B.Q6_K.gguf",
        concurrency: int = 3,
    ) -> dict:
        """
        Chạy full eval suite với concurrency limit.

        Args:
            category: Optional filter ("factual"|"reasoning"|"code")
            limit: Max cases (0 = all)
            model: Model name for logging
            concurrency: Max parallel cases

        Returns:
            Full summary dict
        """
        run_id = str(uuid.uuid4())[:8]
        cases = self.db.get_cases(category=category, limit=limit)

        logger.info("Starting eval run", run_id=run_id, n_cases=len(cases), model=model)

        results = []
        sem = asyncio.Semaphore(concurrency)

        async def run_with_sem(case):
            async with sem:
                return await self.run_case(case, model=model, run_id=run_id)

        tasks = [run_with_sem(c) for c in cases]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid = [r for r in results if isinstance(r, dict)]
        failed = len(results) - len(valid)
        if failed:
            logger.warning("Some eval cases failed", failed=failed)

        summary = summarize_scores(valid)
        summary["run_id"] = run_id
        summary["model"] = model
        summary["failed"] = failed

        logger.info("Eval run complete",
                    run_id=run_id,
                    n=len(valid),
                    avg=round(summary.get("overall", {}).get("mean", 0), 3))

        return summary
