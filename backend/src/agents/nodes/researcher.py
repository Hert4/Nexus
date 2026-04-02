"""
agents/nodes/researcher.py — Researcher node: thu thập thông tin.

Dùng RAG retriever (Qdrant) + DuckDuckGo search để gather context
cho current_step trong plan.
"""

import structlog
from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.agents.tools.search import web_search
from src.core.llm import LLMClient
from src.core.model_router import TaskComplexity
from src.core.model_router import router as model_router
from src.rag.retriever import HybridRetriever

logger = structlog.get_logger(__name__)

RESEARCHER_PROMPT = """You are a research assistant.
Based on the information gathered, provide a comprehensive answer.

Task: {task}
Current step: {step}

Information from knowledge base:
{rag_context}

Information from web search:
{search_context}

Provide a thorough research summary for this step."""


async def researcher_node(state: AgentState) -> dict:
    """
    Researcher node — gather context từ RAG + web search.

    Input state keys: task, plan, current_step
    Output state keys: tool_results, messages
    """
    task = state["task"]
    plan = state.get("plan", [task])
    step_idx = state.get("current_step", 0)
    current_step = plan[step_idx] if step_idx < len(plan) else task

    logger.info("Researcher node", step=current_step[:80])

    tool_results = list(state.get("tool_results", []))

    # 1. RAG retrieval từ Qdrant
    rag_context = ""
    try:
        retriever = HybridRetriever()
        docs = await retriever.retrieve(current_step, top_k=3)
        if docs:
            rag_context = "\n\n".join(
                f"[{d.metadata.get('source_filename', 'doc')}]\n{d.page_content}" for d in docs
            )
            tool_results.append(
                {"tool": "rag_retriever", "query": current_step, "result": rag_context[:500]}
            )
    except Exception as e:
        logger.warning("RAG retrieval failed", error=str(e))
        rag_context = "(RAG unavailable)"

    # 2. Web search
    search_context = ""
    try:
        search_result = web_search.invoke(current_step)
        search_context = search_result
        tool_results.append(
            {"tool": "web_search", "query": current_step, "result": search_result[:500]}
        )
    except Exception as e:
        logger.warning("Web search failed", error=str(e))
        search_context = "(Web search unavailable)"

    # 3. LLM synthesize research
    params = model_router.route(task, force_complexity=TaskComplexity.COMPLEX)
    llm = LLMClient()

    prompt = RESEARCHER_PROMPT.format(
        task=task,
        step=current_step,
        rag_context=rag_context or "(no results)",
        search_context=search_context or "(no results)",
    )

    research_summary = await llm.chat(
        prompt=prompt,
        temperature=params.temperature,
        max_tokens=1024,
    )

    tool_results.append({"tool": "researcher_synthesis", "result": research_summary})
    logger.info("Researcher done", result_len=len(research_summary))

    return {
        "tool_results": tool_results,
        "messages": [AIMessage(content=f"Research for step '{current_step}':\n{research_summary}")],
    }
