"""
agents/graph.py — LangGraph state machine cho Nexus AI Agent.

Graph structure:
    START → planner → researcher → [coder?] → reviewer → END
                          ↑                        │
                          └── retry (needs_review) ┘

Conditional edges:
  - researcher → coder: nếu task chứa keyword lập trình
  - reviewer → researcher: nếu needs_review=True và retry_count < MAX
  - reviewer → END: nếu needs_review=False

Usage:
    from src.agents.graph import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"task": "...", ...})
"""

import structlog
from langgraph.graph import END, START, StateGraph

from src.agents.nodes.coder import coder_node
from src.agents.nodes.planner import planner_node
from src.agents.nodes.researcher import researcher_node
from src.agents.nodes.reviewer import reviewer_node
from src.agents.state import AgentState

logger = structlog.get_logger(__name__)

# Keywords để quyết định có cần coder node không
_CODE_TASK_KEYWORDS = {
    "code", "script", "program", "function", "implement",
    "calculate", "compute", "algorithm", "python", "debug",
}


def _needs_coder(state: AgentState) -> str:
    """Conditional edge: researcher → coder hay reviewer?"""
    task = state.get("task", "").lower()
    if any(kw in task for kw in _CODE_TASK_KEYWORDS):
        logger.debug("Routing to coder")
        return "coder"
    return "reviewer"


def _reviewer_decision(state: AgentState) -> str:
    """Conditional edge: reviewer → researcher (retry) hay END?"""
    if state.get("needs_review", False):
        logger.debug("Reviewer: retry", count=state.get("retry_count", 0))
        return "researcher"
    logger.debug("Reviewer: done")
    return END


def build_graph() -> StateGraph:
    """
    Build và compile LangGraph state machine.

    Returns compiled graph sẵn sàng để invoke/stream.
    """
    graph = StateGraph(AgentState)

    # Thêm nodes
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("coder", coder_node)
    graph.add_node("reviewer", reviewer_node)

    # Edges cố định
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("coder", "reviewer")

    # Conditional edge: researcher → coder | reviewer
    graph.add_conditional_edges(
        "researcher",
        _needs_coder,
        {"coder": "coder", "reviewer": "reviewer"},
    )

    # Conditional edge: reviewer → researcher (retry) | END
    graph.add_conditional_edges(
        "reviewer",
        _reviewer_decision,
        {"researcher": "researcher", END: END},
    )

    compiled = graph.compile()
    logger.info("Agent graph compiled")
    return compiled


# Singleton — compile 1 lần khi import
agent_graph = build_graph()
