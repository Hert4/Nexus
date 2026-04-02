"""
api/routes/agents.py — Agent endpoints.

POST /v1/agents/run      — Run agent task, trả về kết quả khi xong
WebSocket /v1/agents/ws  — Stream từng node event real-time

WebSocket event format:
    {"event": "node_start",    "node": "planner"}
    {"event": "node_complete", "node": "planner", "output": "..."}
    {"event": "tool_call",     "tool": "web_search", "input": "..."}
    {"event": "final_answer",  "content": "..."}
    {"event": "error",         "detail": "..."}
"""

import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.agents.graph import agent_graph
from src.agents.state import AgentState

logger = structlog.get_logger(__name__)
router = APIRouter()


class AgentRequest(BaseModel):
    task: str
    stream: bool = True


class AgentResponse(BaseModel):
    task: str
    final_answer: str
    steps_taken: int
    tool_results: list[dict] = []


def _initial_state(task: str) -> AgentState:
    """Tạo initial state cho agent graph."""
    return AgentState(
        messages=[],
        task=task,
        plan=[],
        current_step=0,
        tool_results=[],
        final_answer="",
        needs_review=False,
        retry_count=0,
    )


@router.post("/agents/run", response_model=AgentResponse)
async def run_agent(req: AgentRequest):
    """
    Run agent task đến khi hoàn thành, trả về kết quả cuối.
    Dùng khi không cần stream từng bước.
    """
    logger.info("Agent run", task=req.task[:80])

    state = _initial_state(req.task)
    result = await agent_graph.ainvoke(state)

    return AgentResponse(
        task=req.task,
        final_answer=result.get("final_answer", "No answer generated"),
        steps_taken=len(result.get("plan", [])),
        tool_results=result.get("tool_results", []),
    )


@router.websocket("/agents/ws")
async def agent_websocket(websocket: WebSocket):
    """
    WebSocket endpoint để stream agent steps real-time.

    Client gửi: {"task": "your task here"}
    Server stream: node events → final_answer
    """
    await websocket.accept()
    logger.info("Agent WebSocket connected")

    async def send(event: dict):
        await websocket.send_text(json.dumps(event))

    try:
        # Nhận task từ client
        data = await websocket.receive_text()
        payload = json.loads(data)
        task = payload.get("task", "")

        if not task:
            await send({"event": "error", "detail": "Missing 'task' field"})
            return

        logger.info("Agent WebSocket task", task=task[:80])
        await send({"event": "start", "task": task})

        state = _initial_state(task)

        # Stream từng node qua astream_events
        async for event in agent_graph.astream_events(state, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chain_start" and name in ("planner", "researcher", "coder", "reviewer"):
                await send({"event": "node_start", "node": name})

            elif kind == "on_chain_end" and name in ("planner", "researcher", "coder", "reviewer"):
                output = event.get("data", {}).get("output", {})
                # Lấy text output gọn nhất để gửi qua WS
                summary = ""
                if isinstance(output, dict):
                    msgs = output.get("messages", [])
                    if msgs:
                        last = msgs[-1]
                        summary = getattr(last, "content", str(last))[:500]
                await send({
                    "event": "node_complete",
                    "node": name,
                    "output": summary,
                })

            elif kind == "on_tool_start":
                await send({
                    "event": "tool_call",
                    "tool": name,
                    "input": str(event.get("data", {}).get("input", ""))[:200],
                })

        # Lấy final state bằng ainvoke
        final = await agent_graph.ainvoke(state)
        answer = final.get("final_answer", "No answer generated")

        await send({"event": "final_answer", "content": answer})
        logger.info("Agent WebSocket done")

    except WebSocketDisconnect:
        logger.info("Agent WebSocket disconnected")
    except Exception as e:
        logger.error("Agent WebSocket error", error=str(e))
        try:
            await send({"event": "error", "detail": str(e)})
        except Exception:
            pass
