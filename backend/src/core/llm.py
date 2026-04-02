"""
core/llm.py — OpenAI-compatible LLM client wrapper cho llama.cpp server.

llama-server expose /v1/chat/completions giống OpenAI API hoàn toàn,
nên ta dùng openai Python SDK trỏ thẳng vào đó.

Usage:
    from src.core.llm import LLMClient
    client = LLMClient()
    # Streaming
    async for chunk in client.stream("Explain RAG"):
        print(chunk, end="")
    # Non-streaming
    response = await client.chat("Explain RAG")
"""

from collections.abc import AsyncGenerator

import structlog
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError

from src.config import settings

logger = structlog.get_logger(__name__)


class LLMClient:
    """
    Wrapper around openai.AsyncOpenAI pointed at llama-server.

    Mọi LLM call trong project đều qua class này — dễ swap provider
    sau này chỉ cần đổi base_url + model.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.llamacpp_chat_url
        self._model = model or settings.gguf_chat_model
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=settings.llm_api_key,
            timeout=120.0,
        )

    async def chat(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Non-streaming chat completion. Trả về full response string."""
        logger.debug("LLM chat request", model=self._model, prompt_len=len(prompt))
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            logger.debug("LLM chat done", tokens=response.usage.total_tokens if response.usage else 0)
            return content
        except (APIConnectionError, APITimeoutError) as e:
            logger.error("LLM connection error", error=str(e))
            raise

    async def stream(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat — yield từng text chunk."""
        logger.debug("LLM stream request", model=self._model)
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except (APIConnectionError, APITimeoutError) as e:
            logger.error("LLM stream error", error=str(e))
            raise

    async def chat_messages(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Non-streaming với danh sách messages (system/user/assistant)."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def stream_messages(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming với danh sách messages."""
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# Singleton instance dùng chung trong app
llm_client = LLMClient()
