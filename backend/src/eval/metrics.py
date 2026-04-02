"""
eval/metrics.py — Statistical metrics cho eval results.

Bootstrap confidence intervals, category summaries, trend analysis.

Usage:
    from src.eval.metrics import bootstrap_ci, summarize_scores
    lo, hi = bootstrap_ci([0.8, 0.9, 0.7, 0.85], n_bootstrap=1000)
"""

import random
import statistics
from typing import Sequence


def bootstrap_ci(
    scores: Sequence[float],
    confidence: float = 0.95,
    n_bootstrap: int = 1000,
) -> tuple[float, float]:
    """
    Bootstrap confidence interval cho mean score.

    Args:
        scores: List of scores (0.0–1.0)
        confidence: Confidence level (default 0.95 → 95% CI)
        n_bootstrap: Number of bootstrap samples

    Returns:
        (lower_bound, upper_bound)
    """
    if not scores:
        return (0.0, 0.0)
    if len(scores) == 1:
        return (scores[0], scores[0])

    means = []
    n = len(scores)
    for _ in range(n_bootstrap):
        sample = [random.choice(scores) for _ in range(n)]  # noqa: S311
        means.append(statistics.mean(sample))

    means.sort()
    alpha = 1 - confidence
    lo_idx = int(alpha / 2 * n_bootstrap)
    hi_idx = int((1 - alpha / 2) * n_bootstrap) - 1
    return (means[lo_idx], means[hi_idx])


def summarize_scores(results: list[dict]) -> dict:
    """
    Tóm tắt thống kê từ list of eval result dicts.

    Args:
        results: List of dicts với keys: score_completion, score_quality,
                 score_faithful, score_avg, latency_s, category

    Returns:
        Summary dict với mean, stdev, ci_95, by_category
    """
    if not results:
        return {"n": 0}

    def _stats(values: list[float]) -> dict:
        if not values:
            return {}
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        lo, hi = bootstrap_ci(values)
        return {
            "mean": round(mean, 4),
            "stdev": round(stdev, 4),
            "ci_95": (round(lo, 4), round(hi, 4)),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "n": len(values),
        }

    completion  = [r["score_completion"]  for r in results if r.get("score_completion") is not None]
    quality     = [r["score_quality"]     for r in results if r.get("score_quality")     is not None]
    faithfulness= [r["score_faithful"]    for r in results if r.get("score_faithful")    is not None]
    avg_scores  = [r["score_avg"]         for r in results if r.get("score_avg")         is not None]
    latencies   = [r["latency_s"]         for r in results if r.get("latency_s")         is not None]

    # Per-category
    by_category: dict[str, list[float]] = {}
    for r in results:
        cat = r.get("category", "unknown")
        if r.get("score_avg") is not None:
            by_category.setdefault(cat, []).append(r["score_avg"])

    return {
        "n": len(results),
        "completion":   _stats(completion),
        "quality":      _stats(quality),
        "faithfulness": _stats(faithfulness),
        "overall":      _stats(avg_scores),
        "latency_s":    _stats(latencies),
        "by_category": {
            cat: _stats(vals) for cat, vals in by_category.items()
        },
    }


def compare_runs(run_a: list[dict], run_b: list[dict]) -> dict:
    """
    So sánh 2 eval runs — dùng cho A/B testing model variants.

    Returns:
        dict với delta mean, winner, significance (thô)
    """
    a_scores = [r["score_avg"] for r in run_a if r.get("score_avg") is not None]
    b_scores = [r["score_avg"] for r in run_b if r.get("score_avg") is not None]

    if not a_scores or not b_scores:
        return {"error": "insufficient data"}

    mean_a = statistics.mean(a_scores)
    mean_b = statistics.mean(b_scores)
    delta  = mean_b - mean_a

    # CI overlap check (rough significance)
    lo_a, hi_a = bootstrap_ci(a_scores)
    lo_b, hi_b = bootstrap_ci(b_scores)
    overlap = lo_b <= hi_a and lo_a <= hi_b

    return {
        "mean_a":       round(mean_a, 4),
        "mean_b":       round(mean_b, 4),
        "delta":        round(delta, 4),
        "winner":       "B" if delta > 0 else ("A" if delta < 0 else "tie"),
        "ci_a":         (round(lo_a, 4), round(hi_a, 4)),
        "ci_b":         (round(lo_b, 4), round(hi_b, 4)),
        "ci_overlap":   overlap,
        "significant":  not overlap,  # rough: non-overlapping CI → likely significant
    }
