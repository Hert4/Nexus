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
from collections.abc import AsyncGenerator

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.core.llm import LLMClient
from src.core.model_router import TaskComplexity, router as model_router
from src.rag.chain import RAGChain

logger = structlog.get_logger(__name__)
api_router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    stream: bool = True
    use_rag: bool = True  # Dùng RAG hay plain chat
    system: str = "You are a helpful assistant."


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict] = []


async def _sse_generator(gen: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
    """Wrap async text generator thành SSE bytes stream."""
    async for chunk in gen:
        data = json.dumps({"chunk": chunk})
        yield f"data: {data}\n\n".encode()
    yield b"data: [DONE]\n\n"


@api_router.post("/chat")
async def chat(req: ChatRequest):
    """
    Chat endpoint.
    - use_rag=True  → dùng RAG chain (retrieve từ Qdrant + LLM generate)
    - use_rag=False → plain LLM chat
    - stream=True   → SSE streaming response
    - stream=False  → JSON response
    """
    logger.info("Chat request", use_rag=req.use_rag, stream=req.stream, msg_len=len(req.message))

    if req.use_rag:
        chain = RAGChain()
        if req.stream:
            return StreamingResponse(
                _sse_generator(chain.stream(req.message)),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"},
            )
        else:
            result = await chain.retrieve_with_answer(req.message)
            return ChatResponse(**result)
    else:
        # Plain chat — dùng model router để chọn params
        params = model_router.route(req.message)
        llm = LLMClient(base_url=params.base_url, model=params.model)
        if req.stream:
            return StreamingResponse(
                _sse_generator(
                    llm.stream(req.message, system=req.system, temperature=params.temperature)
                ),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"},
            )
        else:
            answer = await llm.chat(req.message, system=req.system, temperature=params.temperature)
            return ChatResponse(answer=answer)


router = api_router
