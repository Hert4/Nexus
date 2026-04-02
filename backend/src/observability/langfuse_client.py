"""
observability/langfuse_client.py — LLM tracing với Langfuse.

Trace mỗi LLM call (model, tokens, latency) và mỗi agent run (steps, tools).
Langfuse self-hosted tại http://localhost:3000 (xem docker-compose.monitoring.yml).

Usage:
    # Trong rag/chain.py hoặc agents/nodes/*.py:
    from src.observability.langfuse_client import get_langfuse_callback

    handler = get_langfuse_callback()
    if handler:
        result = await chain.ainvoke(input, config={"callbacks": [handler]})
    else:
        result = await chain.ainvoke(input)

Env vars cần thiết (trong .env):
    LANGFUSE_HOST=http://localhost:3000
    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_SECRET_KEY=sk-lf-...

Nếu chưa config → trả về None, không trace (graceful degradation).
"""

import time

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


def get_langfuse_callback():
    """
    Trả về LangFuse callback handler nếu đã config, None nếu chưa.

    Graceful degradation: nếu Langfuse chưa cài hoặc chưa config,
    app vẫn chạy bình thường — chỉ không có tracing.
    """
    # Kiểm tra env vars cần thiết
    host = getattr(settings, "langfuse_host", None)
    public_key = getattr(settings, "langfuse_public_key", None)
    secret_key = getattr(settings, "langfuse_secret_key", None)

    if not all([host, public_key, secret_key]):
        return None

    try:
        from langfuse.callback import CallbackHandler  # type: ignore

        handler = CallbackHandler(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        logger.debug("Langfuse callback initialized", host=host)
        return handler
    except ImportError:
        logger.warning("langfuse not installed — tracing disabled")
        return None
    except Exception as e:
        logger.warning("Langfuse init failed", error=str(e))
        return None


class TraceContext:
    """
    Context manager để trace một agent run thủ công (không qua LangChain callback).

    Usage:
        async with TraceContext("agent_run", task="fibonacci") as ctx:
            result = await agent_graph.ainvoke(state)
            ctx.set_output(result)
    """

    def __init__(self, name: str, **metadata):
        self.name = name
        self.metadata = metadata
        self._start = 0.0
        self._trace = None

    async def __aenter__(self):
        self._start = time.perf_counter()
        # Try to create Langfuse trace
        try:
            host = getattr(settings, "langfuse_host", None)
            public_key = getattr(settings, "langfuse_public_key", None)
            secret_key = getattr(settings, "langfuse_secret_key", None)

            if all([host, public_key, secret_key]):
                from langfuse import Langfuse  # type: ignore

                lf = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=host,
                )
                self._trace = lf.trace(
                    name=self.name,
                    metadata=self.metadata,
                )
        except Exception:
            pass  # Silent — tracing is optional
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self._start
        if self._trace:
            try:
                self._trace.update(
                    metadata={**self.metadata, "duration_seconds": elapsed},
                    status_message="error" if exc_type else "success",
                )
            except Exception:
                pass
        logger.debug("Trace complete", name=self.name, duration=round(elapsed, 3))
        return False  # không suppress exceptions

    def set_output(self, output) -> None:
        """Attach final output vào trace."""
        if self._trace:
            try:
                self._trace.update(output=str(output)[:500])
            except Exception:
                pass
