"""
agents/nodes/coder.py — Coder node: generate và execute Python code.

Chỉ chạy khi task cần code (conditional edge từ researcher).
Generate code → execute trong sandbox → trả về output.
"""

import structlog
from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.agents.tools.code_exec import execute_python
from src.core.llm import LLMClient
from src.core.model_router import TaskComplexity
from src.core.model_router import router as model_router

logger = structlog.get_logger(__name__)

CODER_PROMPT = """You are an expert Python programmer.
Write clean, working Python code to solve the task.

Task: {task}
Context from research: {context}

Requirements:
- Write complete, runnable Python code
- Use print() to output results
- Handle edge cases
- No external API calls or file I/O

Output ONLY the Python code, no explanations, no markdown fences."""


async def coder_node(state: AgentState) -> dict:
    """
    Coder node — generate Python code và execute.

    Input state keys: task, tool_results
    Output state keys: tool_results, messages
    """
    task = state["task"]
    tool_results = list(state.get("tool_results", []))

    # Lấy research context từ tool_results
    context = "\n".join(
        r["result"]
        for r in tool_results
        if r.get("tool") in ("researcher_synthesis", "rag_retriever")
    )[:1000]

    logger.info("Coder node", task=task[:80])

    # 1. Generate code
    model_router.route(task, force_complexity=TaskComplexity.COMPLEX)
    llm = LLMClient()

    code = await llm.chat(
        prompt=CODER_PROMPT.format(task=task, context=context or "No context available"),
        system="Output only Python code. No markdown, no explanations.",
        temperature=0.1,  # low temp → deterministic code
        max_tokens=2048,
    )

    # Clean up markdown fences nếu model vẫn thêm vào
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    logger.info("Code generated", code_len=len(code))

    # 2. Execute code
    exec_result = execute_python.invoke(code)
    logger.info("Code executed", result=exec_result[:100])

    tool_results.append(
        {
            "tool": "coder",
            "code": code,
            "result": exec_result,
        }
    )

    return {
        "tool_results": tool_results,
        "messages": [
            AIMessage(content=f"Code executed:\n```python\n{code}\n```\nOutput: {exec_result}")
        ],
    }
