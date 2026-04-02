"""
agents/tools/search.py — DuckDuckGo web search tool.

Dùng `duckduckgo-search` package để search web mà không cần API key.
LangChain @tool decorator expose function này cho LLM tool calling.
"""

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger(__name__)


@tool
def web_search(query: str) -> str:
    """Search the web for current information about a topic.

    Use this when you need up-to-date information not in the knowledge base.

    Args:
        query: Search query string

    Returns:
        Formatted search results as string
    """
    from duckduckgo_search import DDGS

    logger.info("Web search", query=query[:80])
    try:
        results = DDGS().text(query, max_results=5)
        if not results:
            return "No results found."
        formatted = "\n\n".join(
            f"**{r['title']}**\n{r['body']}\nSource: {r['href']}" for r in results
        )
        logger.info("Web search done", count=len(results))
        return formatted
    except Exception as e:
        logger.error("Web search failed", error=str(e))
        return f"Search failed: {e}"
