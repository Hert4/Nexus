"""
core/model_router.py — Điều hướng request đến llama-server với params phù hợp.

Vì chỉ có 1 model (Qwen3.5-9B), router quyết định context size và
temperature dựa trên độ phức tạp của task — không cần swap model.

Logic:
  - Simple (chat thường, Q&A ngắn)  → ctx 2048,  temperature 0.7
  - Complex (code gen, reasoning)    → ctx 8192,  temperature 0.2
  - Agent tasks                      → ctx 8192,  temperature 0.1 (deterministic hơn)

Usage:
    from src.core.model_router import router
    params = router.route("Write a Python function to sort a list")
    # → ModelParams(ctx_size=8192, temperature=0.2, max_tokens=4096)
"""

from enum import StrEnum

import structlog
from pydantic import BaseModel

from src.config import settings

logger = structlog.get_logger(__name__)

# Keywords để phát hiện task phức tạp
_CODE_KEYWORDS = {"code", "function", "implement", "script", "program", "debug", "fix", "class"}
_REASON_KEYWORDS = {"explain", "analyze", "compare", "evaluate", "why", "how does", "step by step"}
_AGENT_KEYWORDS = {"search", "find", "research", "calculate", "query", "run", "execute"}


class TaskComplexity(StrEnum):
    SIMPLE = "simple"
    COMPLEX = "complex"
    AGENT = "agent"


class ModelParams(BaseModel):
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    ctx_hint: str  # ghi chú cho logging


class ModelRouter:
    """
    Phân tích task và trả về ModelParams phù hợp.
    Tất cả vẫn dùng cùng model / endpoint, chỉ thay params.
    """

    def classify(self, prompt: str) -> TaskComplexity:
        """Phân loại độ phức tạp dựa vào keywords trong prompt."""
        lower = prompt.lower()
        if any(k in lower for k in _AGENT_KEYWORDS):
            return TaskComplexity.AGENT
        if any(k in lower for k in _CODE_KEYWORDS | _REASON_KEYWORDS):
            return TaskComplexity.COMPLEX
        return TaskComplexity.SIMPLE

    def route(
        self,
        prompt: str,
        force_complexity: TaskComplexity | None = None,
    ) -> ModelParams:
        """
        Trả về ModelParams cho prompt.

        Args:
            prompt: User message
            force_complexity: Override tự động classify (dùng trong agents)
        """
        complexity = force_complexity or self.classify(prompt)

        match complexity:
            case TaskComplexity.SIMPLE:
                params = ModelParams(
                    base_url=settings.llamacpp_chat_url,
                    model=settings.gguf_chat_model,
                    temperature=0.7,
                    max_tokens=1024,
                    ctx_hint="simple",
                )
            case TaskComplexity.COMPLEX:
                params = ModelParams(
                    base_url=settings.llamacpp_chat_url,
                    model=settings.gguf_chat_model,
                    temperature=0.2,
                    max_tokens=4096,
                    ctx_hint="complex",
                )
            case TaskComplexity.AGENT:
                params = ModelParams(
                    base_url=settings.llamacpp_chat_url,
                    model=settings.gguf_chat_model,
                    temperature=0.1,
                    max_tokens=4096,
                    ctx_hint="agent",
                )

        logger.debug("Model routed", complexity=complexity, params=params.ctx_hint)
        return params


# Singleton
router = ModelRouter()
