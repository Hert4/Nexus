"""
rag/chain.py — LangChain LCEL RAG chain.

Flow: query → retrieve top-k → format context → LLM generate → stream

Chain dùng LangChain Expression Language (LCEL):
  {"context": retriever | format_docs, "question": passthrough}
  | prompt | llm | StrOutputParser()

Prompt yêu cầu model:
  - Cite nguồn (filename, page)
  - Thừa nhận khi không biết thay vì bịa

Usage:
    from src.rag.chain import rag_chain
    # Non-streaming
    answer = await rag_chain.invoke("What is RAG?")
    # Streaming
    async for chunk in rag_chain.stream("What is RAG?"):
        print(chunk, end="")
"""

from collections.abc import AsyncGenerator

import structlog
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

from src.config import settings
from src.rag.retriever import HybridRetriever

logger = structlog.get_logger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────
RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on provided context.

Rules:
1. Answer ONLY based on the context below. Do NOT use outside knowledge.
2. Always cite your sources using [filename, page X] format.
3. If the context doesn't contain enough information, say "I don't have enough information to answer this question."
4. Be concise and clear.

Context:
{context}
"""

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    ("human", "{question}"),
])


def _format_docs(docs: list[Document]) -> str:
    """Chuyển list[Document] thành string context cho prompt."""
    parts = []
    for doc in docs:
        filename = doc.metadata.get("source_filename", "unknown")
        page = doc.metadata.get("page", "")
        source = f"{filename}" + (f", page {page}" if page else "")
        parts.append(f"[{source}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


class RAGChain:
    """
    RAG chain kết hợp HybridRetriever + llama-server LLM.
    Hỗ trợ cả streaming và non-streaming.
    """

    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self._retriever = retriever or HybridRetriever()
        # LangChain ChatOpenAI trỏ vào llama-server
        self._llm = ChatOpenAI(
            base_url=settings.llamacpp_chat_url,
            api_key=settings.llm_api_key,
            model=settings.gguf_chat_model,
            temperature=0.3,
            max_tokens=2048,
            streaming=True,
        )
        # Build LCEL chain
        self._chain = (
            {
                "context": self._retrieve_and_format,
                "question": RunnablePassthrough(),
            }
            | RAG_PROMPT
            | self._llm
            | StrOutputParser()
        )

    async def _retrieve_and_format(self, question: str) -> str:
        docs = await self._retriever.retrieve(question)
        return _format_docs(docs)

    async def invoke(self, question: str) -> str:
        """Non-streaming — trả về full answer string."""
        logger.info("RAG invoke", question=question[:80])
        result = await self._chain.ainvoke(question)
        return result

    async def stream(self, question: str) -> AsyncGenerator[str, None]:
        """Streaming — yield từng chunk text."""
        logger.info("RAG stream", question=question[:80])
        async for chunk in self._chain.astream(question):
            yield chunk

    async def retrieve_with_answer(self, question: str) -> dict:
        """Trả về cả sources và answer (dùng cho API response có metadata)."""
        docs = await self._retriever.retrieve(question)
        context = _format_docs(docs)

        messages = RAG_PROMPT.format_messages(context=context, question=question)
        response = await self._llm.ainvoke(messages)
        answer = response.content

        sources = [
            {
                "filename": d.metadata.get("source_filename", ""),
                "page": d.metadata.get("page", ""),
                "chunk_index": d.metadata.get("chunk_index", 0),
                "snippet": d.page_content[:200],
            }
            for d in docs
        ]
        return {"answer": answer, "sources": sources}


# Singleton
rag_chain = RAGChain()
