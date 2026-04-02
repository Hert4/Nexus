"""
api/routes/chat.py — Streaming chat endpoint via Server-Sent Events (SSE).

POST /v1/chat
  Body: ChatRequest
  Response: StreamingResponse (text/event-stream) hoặc JSON tùy flag

SSE format:
  data: {"chunk": "Hello"}
  data: {"chunk": " world"}
  data: [DONE]

Hỗ trợ cả RAG mode (dùng documents đã ingest) và plain chat mode.
"""

import json
import uuid
from collections.abc import AsyncGenerator

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.core.guardrails import chat_limiter, check_input
from src.core.llm import LLMClient
from src.core.model_router import router as model_router
from src.rag.chain import RAGChain

logger = structlog.get_logger(__name__)
api_router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    stream: bool = True
    use_rag: bool = True  # Dùng RAG hay plain chat
    system: str = "You are a helpful assistant."
    session_id: str = ""  # Optional — dùng cho A/B sticky assignment


class ChatResponse(BaseModel):
    message_id: str
    answer: str
    sources: list[dict] = []


async def _sse_generator(gen: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
    """Wrap async text generator thành SSE bytes stream."""
    async for chunk in gen:
        data = json.dumps({"chunk": chunk})
        yield f"data: {data}\n\n".encode()
    yield b"data: [DONE]\n\n"


@api_router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """
    Chat endpoint với guardrails.
    - use_rag=True  → RAG chain (retrieve từ Qdrant + LLM generate)
    - use_rag=False → plain LLM chat
    - stream=True   → SSE streaming response
    - stream=False  → JSON response với message_id cho feedback
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not chat_limiter.allow(client_ip):
        raise HTTPException(429, "Too many requests. Please slow down.")

    # Input guardrails
    check = check_input(req.message)
    if not check.safe:
        logger.warning("Input blocked", reason=check.reason, risk=check.risk_level)
        raise HTTPException(400, f"Input rejected: {check.reason}")

    message_id = str(uuid.uuid4())[:8]
    logger.info(
        "Chat request",
        message_id=message_id,
        use_rag=req.use_rag,
        stream=req.stream,
        msg_len=len(req.message),
    )

    if req.use_rag:
        chain = RAGChain()
        if req.stream:
            return StreamingResponse(
                _sse_generator(chain.stream(req.message)),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no", "X-Message-ID": message_id},
            )
        else:
            result = await chain.retrieve_with_answer(req.message)
            return ChatResponse(message_id=message_id, **result)
    else:
        params = model_router.route(req.message)
        llm = LLMClient(base_url=params.base_url, model=params.model)
        if req.stream:
            return StreamingResponse(
                _sse_generator(
                    llm.stream(req.message, system=req.system, temperature=params.temperature)
                ),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no", "X-Message-ID": message_id},
            )
        else:
            answer = await llm.chat(req.message, system=req.system, temperature=params.temperature)
            return ChatResponse(message_id=message_id, answer=answer)


router = api_router
