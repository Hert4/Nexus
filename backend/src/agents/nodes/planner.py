"""
agents/nodes/planner.py — Planner node: decompose task thành steps.

Nhận task từ user → LLM phân tích → output danh sách steps cụ thể.
Đây là node đầu tiên trong graph, chạy 1 lần duy nhất.
"""

import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.state import AgentState
from src.core.llm import LLMClient
from src.core.model_router import TaskComplexity
from src.core.model_router import router as model_router

logger = structlog.get_logger(__name__)

PLANNER_PROMPT = """You are a task planning assistant.
Break down the given task into clear, actionable steps.

Task: {task}

Output a JSON array of steps. Each step should be specific and actionable.
Example: ["Search for information about X", "Analyze the findings", "Write a summary"]

Respond with ONLY the JSON array, no other text."""


async def planner_node(state: AgentState) -> dict:
    """
    Planner node — decompose task thành steps.

    Input state keys: task
    Output state keys: plan, messages, current_step
    """
    task = state["task"]
    logger.info("Planner node", task=task[:80])

    params = model_router.route(task, force_complexity=TaskComplexity.COMPLEX)
    llm = LLMClient()

    prompt = PLANNER_PROMPT.format(task=task)
    response = await llm.chat(
        prompt=prompt,
        system="You are a precise task planner. Output only valid JSON.",
        temperature=params.temperature,
        max_tokens=512,
    )

    # Parse JSON plan
    try:
        # Tìm JSON array trong response (model có thể thêm text thừa)
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            plan = json.loads(response[start:end])
        else:
            # Fallback: tạo plan đơn giản
            plan = [f"Research and answer: {task}"]
    except (json.JSONDecodeError, ValueError):
        plan = [f"Research and answer: {task}"]

    logger.info("Plan created", steps=len(plan), plan=plan)

    return {
        "plan": plan,
        "current_step": 0,
        "messages": [
            HumanMessage(content=task),
            AIMessage(
                content=f"Plan created with {len(plan)} steps:\n"
                + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan))
            ),
        ],
    }
