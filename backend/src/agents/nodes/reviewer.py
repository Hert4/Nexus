"""
agents/nodes/reviewer.py — Reviewer node: self-critique và quyết định pass/retry.

Đánh giá output từ researcher/coder, quyết định:
- PASS: final_answer đủ tốt → END
- RETRY: cần thêm research → loop lại researcher (max 2 lần)
"""

import structlog
from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.core.llm import LLMClient

logger = structlog.get_logger(__name__)

MAX_RETRIES = 2

REVIEWER_PROMPT = """You are a quality reviewer.
Evaluate if the research/work adequately answers the task.

Original task: {task}

Work done so far:
{work_summary}

Evaluate on these criteria:
1. Does it directly answer the task? (yes/no)
2. Is the information sufficient and accurate? (yes/no)
3. Are there obvious gaps or errors? (yes/no)

First line must be exactly "PASS" or "RETRY".
Then provide a brief explanation and the final answer if passing.

Format:
PASS
[explanation]
FINAL ANSWER: [complete answer here]

or:

RETRY
[what's missing or needs improvement]"""

SYNTHESIZER_PROMPT = """Synthesize all research and work into a clear, complete final answer.

Task: {task}

Research and work summary:
{work_summary}

Write a comprehensive, well-structured final answer. Cite sources where applicable."""


async def reviewer_node(state: AgentState) -> dict:
    """
    Reviewer node — quyết định PASS hoặc RETRY.

    Input state keys: task, tool_results, retry_count
    Output state keys: final_answer, needs_review, retry_count, messages
    """
    task = state["task"]
    tool_results = state.get("tool_results", [])
    retry_count = state.get("retry_count", 0)

    logger.info("Reviewer node", retry_count=retry_count)

    # Tóm tắt work đã làm
    work_summary = "\n\n".join(f"[{r['tool']}]: {r.get('result', '')[:400]}" for r in tool_results)

    # Nếu đã retry đủ lần → force PASS với best effort answer
    if retry_count >= MAX_RETRIES:
        logger.warning("Max retries reached, forcing pass")
        llm = LLMClient()
        final = await llm.chat(
            prompt=SYNTHESIZER_PROMPT.format(task=task, work_summary=work_summary),
            temperature=0.3,
            max_tokens=2048,
        )
        return {
            "final_answer": final,
            "needs_review": False,
            "messages": [AIMessage(content=f"[Max retries reached]\n{final}")],
        }

    # LLM review
    llm = LLMClient()
    review = await llm.chat(
        prompt=REVIEWER_PROMPT.format(task=task, work_summary=work_summary),
        system="You are a strict quality reviewer. Be concise.",
        temperature=0.1,
        max_tokens=1024,
    )

    first_line = review.strip().split("\n")[0].strip().upper()
    passed = first_line == "PASS"

    logger.info("Review decision", decision=first_line, retry_count=retry_count)

    if passed:
        # Extract final answer from review
        final_answer = ""
        if "FINAL ANSWER:" in review:
            final_answer = review.split("FINAL ANSWER:", 1)[1].strip()
        else:
            # Synthesize nếu reviewer không provide
            final_answer = await llm.chat(
                prompt=SYNTHESIZER_PROMPT.format(task=task, work_summary=work_summary),
                temperature=0.3,
                max_tokens=2048,
            )

        return {
            "final_answer": final_answer,
            "needs_review": False,
            "messages": [AIMessage(content=final_answer)],
        }
    else:
        # RETRY
        return {
            "needs_review": True,
            "retry_count": retry_count + 1,
            "messages": [AIMessage(content=f"[Review: needs improvement]\n{review}")],
        }
