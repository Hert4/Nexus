"""
agents/tools/calculator.py — Safe math expression evaluator.

Dùng numexpr cho fast numeric evaluation.
Fallback sang Python eval với restricted namespace nếu numexpr không đủ.
"""

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger(__name__)


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression.

    Supports: arithmetic (+,-,*,/,**), functions (sin, cos, sqrt, log, abs),
    constants (pi, e), comparisons.

    Examples:
        "2 + 2" → "4"
        "sqrt(144)" → "12.0"
        "sin(pi/2)" → "1.0"
        "2**10" → "1024"

    Args:
        expression: Math expression as string

    Returns:
        Result as string
    """
    import math

    logger.debug("Calculator", expression=expression)

    # Safe namespace — chỉ cho phép math functions
    safe_ns: dict = {
        "__builtins__": {},
        "abs": abs, "round": round, "min": min, "max": max,
        "sum": sum, "pow": pow,
        **{k: v for k, v in vars(math).items() if not k.startswith("_")},
    }

    try:
        # Thử numexpr trước (nhanh hơn cho vector math)
        import numexpr as ne
        result = ne.evaluate(expression)
        return str(float(result))
    except Exception:
        pass

    # Fallback: eval với restricted namespace
    try:
        result = eval(expression, safe_ns)  # noqa: S307 — safe_ns restrict builtins
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero"
    except Exception as e:
        return f"Error: {e}"
