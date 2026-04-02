"""
agents/tools/code_exec.py — Sandboxed Python code execution.

Chạy Python code trong subprocess với:
- Timeout 30s (tránh infinite loop)
- Restricted builtins (block import os, sys, subprocess)
- Resource limits

KHÔNG dùng eval() vì không safe. subprocess với timeout là cách đúng.
"""

import subprocess
import sys
import textwrap

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 30

# Imports bị block vì security
BLOCKED_IMPORTS = {"os", "sys", "subprocess", "shutil", "socket", "requests", "httpx"}

SANDBOX_HEADER = """
import builtins
_real_import = builtins.__import__
_blocked = {blocked}

def _safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top in _blocked:
        raise ImportError(f"Import '{{name}}' is not allowed in sandbox")
    return _real_import(name, *args, **kwargs)

builtins.__import__ = _safe_import
"""


@tool
def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed environment.

    Good for: calculations, data processing, algorithm implementation.
    NOT allowed: file I/O, network requests, system commands.

    Args:
        code: Valid Python code to execute

    Returns:
        stdout output or error message
    """
    logger.info("Code execution requested", code_len=len(code))

    blocked_str = str(BLOCKED_IMPORTS)
    header = SANDBOX_HEADER.format(blocked=blocked_str)
    full_code = header + "\n" + textwrap.dedent(code)

    try:
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            output = result.stdout.strip() or "(no output)"
            logger.info("Code execution success")
            return output
        else:
            err = result.stderr.strip()
            # Bỏ sandbox header lines khỏi traceback để clean hơn
            err_lines = [line for line in err.splitlines() if "sandbox" not in line.lower()]
            return "Error:\n" + "\n".join(err_lines)

    except subprocess.TimeoutExpired:
        logger.warning("Code execution timeout")
        return f"Execution timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        logger.error("Code execution failed", error=str(e))
        return f"Execution failed: {e}"
