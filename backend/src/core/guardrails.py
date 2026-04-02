"""
core/guardrails.py — Input/output safety checks.

1. Prompt injection detection: phát hiện các pattern cố ý override system
2. Output sanity check: cảnh báo nếu output quá ngắn hoặc có hallucination markers
3. Rate limiting: simple in-memory per-IP limiter (dùng cho dev/local)

Usage:
    from src.core.guardrails import check_input, check_output, RateLimiter

    # Input check
    result = check_input(user_message)
    if not result.safe:
        raise HTTPException(400, result.reason)

    # Output check
    warning = check_output(llm_response)
    if warning:
        logger.warning("Output issue", reason=warning)

    # Rate limiting
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    if not limiter.allow("user_ip"):
        raise HTTPException(429, "Too many requests")
"""

import re
import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# ── Prompt injection patterns ──────────────────────────────────────────────────
# Patterns phổ biến trong prompt injection attacks
_INJECTION_PATTERNS: list[re.Pattern] = [
    # "ignore [all/previous/above] [previous] instructions/prompts/context"
    re.compile(
        r"ignore\s+(?:all\s+)?(?:previous\s+|above\s+)?(instructions?|prompts?|context)", re.I
    ),
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(r"forget\s+(?:everything|all|previous)", re.I),
    re.compile(r"new\s+(?:role|persona|instructions?|task):", re.I),
    re.compile(r"system:\s*(?:you|ignore|act)", re.I),
    re.compile(r"\[system\]", re.I),
    re.compile(r"disregard\s+(?:your|all|previous)", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"do\s+anything\s+now", re.I),
    re.compile(r"DAN\s+mode", re.I),
]

# ── Hallucination / low-quality output markers ────────────────────────────────
_HALLUCINATION_MARKERS = [
    "as an AI language model, I don't have",
    "I cannot provide real-time",
    "I don't have access to the internet",
    "my knowledge cutoff",
    "I'm not able to browse",
    # Repetition patterns (model stuck)
    "...",
]

# Minimum useful response length
_MIN_RESPONSE_TOKENS = 5  # rough word count


@dataclass
class InputCheckResult:
    safe: bool
    reason: str = ""
    risk_level: str = "low"  # low | medium | high


def check_input(text: str, max_length: int = 4000) -> InputCheckResult:
    """
    Kiểm tra input từ user.

    Checks:
    1. Length limit
    2. Prompt injection patterns

    Returns:
        InputCheckResult với safe=True/False và reason
    """
    if not text or not text.strip():
        return InputCheckResult(safe=False, reason="Empty input", risk_level="low")

    # Length check
    if len(text) > max_length:
        return InputCheckResult(
            safe=False,
            reason=f"Input too long ({len(text)} chars, max {max_length})",
            risk_level="low",
        )

    # Prompt injection
    matched_patterns = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matched_patterns.append(pattern.pattern[:40])

    if matched_patterns:
        logger.warning("Prompt injection detected", patterns=matched_patterns[:3])
        return InputCheckResult(
            safe=False,
            reason="Potential prompt injection detected",
            risk_level="high",
        )

    return InputCheckResult(safe=True)


def check_output(text: str) -> str:
    """
    Kiểm tra output từ LLM.

    Returns:
        Warning string nếu có vấn đề, empty string nếu OK.
    """
    if not text or len(text.split()) < _MIN_RESPONSE_TOKENS:
        return "Response too short"

    for marker in _HALLUCINATION_MARKERS:
        if marker.lower() in text.lower():
            return f"Possible hallucination marker: '{marker[:40]}'"

    # Repetition check — detect nếu cùng câu lặp lại nhiều lần
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
    if len(sentences) > 3:
        unique = len(set(sentences))
        if unique / len(sentences) < 0.5:  # >50% duplicates
            return "Repetitive output detected"

    return ""


# ── Rate Limiter ───────────────────────────────────────────────────────────────
@dataclass
class RateLimiter:
    """
    Simple in-memory sliding window rate limiter.

    Dùng cho dev/local. Production nên dùng Redis-backed limiter.

    Args:
        max_requests: Max requests per window
        window_seconds: Window size in seconds
    """

    max_requests: int = 20
    window_seconds: int = 60
    _buckets: dict[str, list[float]] = field(default_factory=dict, repr=False)

    def allow(self, key: str) -> bool:
        """
        Check nếu key (IP hoặc user_id) được phép.
        Returns True nếu allowed, False nếu rate limited.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Cleanup old timestamps
        timestamps = self._buckets.get(key, [])
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self.max_requests:
            logger.warning("Rate limit hit", key=key[:20], count=len(timestamps))
            return False

        timestamps.append(now)
        self._buckets[key] = timestamps
        return True

    def remaining(self, key: str) -> int:
        """Số requests còn lại trong window."""
        now = time.time()
        cutoff = now - self.window_seconds
        timestamps = [t for t in self._buckets.get(key, []) if t > cutoff]
        return max(0, self.max_requests - len(timestamps))


# Singleton limiters cho các endpoint khác nhau
chat_limiter = RateLimiter(max_requests=30, window_seconds=60)
agent_limiter = RateLimiter(max_requests=10, window_seconds=60)
eval_limiter = RateLimiter(max_requests=5, window_seconds=300)
