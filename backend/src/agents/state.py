"""
agents/state.py — AgentState schema cho LangGraph.

State là "bộ nhớ" được truyền qua tất cả nodes trong graph.
Mỗi node nhận state, xử lý, và trả về dict với các keys cần update.

LangGraph dùng TypedDict để define schema — strict typing giúp
phát hiện lỗi sớm khi node trả về key không đúng.
"""

from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State được share giữa tất cả nodes trong agent graph.

    Fields:
        messages:      Conversation history — LangGraph manage via add_messages reducer
        task:          Task gốc từ user
        plan:          Danh sách steps do planner node tạo ra
        current_step:  Index của step đang thực hiện
        tool_results:  Kết quả từ các tool calls (search, code exec, ...)
        final_answer:  Answer cuối cùng sau khi reviewer approve
        needs_review:  Flag để reviewer node quyết định pass hay retry
        retry_count:   Số lần đã retry (max 2)
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    task: str
    plan: list[str]
    current_step: int
    tool_results: list[dict]
    final_answer: str
    needs_review: bool
    retry_count: int
