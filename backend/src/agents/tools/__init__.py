"""agents/tools/__init__.py — Export tất cả tools."""

from src.agents.tools.calculator import calculator
from src.agents.tools.code_exec import execute_python
from src.agents.tools.db_query import query_database
from src.agents.tools.search import web_search

ALL_TOOLS = [web_search, execute_python, calculator, query_database]
RESEARCHER_TOOLS = [web_search]
CODER_TOOLS = [execute_python, calculator]

__all__ = ["web_search", "execute_python", "calculator", "query_database", "ALL_TOOLS"]
