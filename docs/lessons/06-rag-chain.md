# Bài 06 — RAG Chain (LCEL)

**Code**: [`backend/src/rag/chain.py`](../../backend/src/rag/chain.py)

---

## Vấn đề cần giải quyết

Sau khi có retriever (bài 05) và LLM client (bài 02), cần **kết nối** chúng thành 1 pipeline:
1. Retrieve chunks liên quan từ Qdrant
2. Format chunks thành context string
3. Inject context vào prompt
4. LLM generate answer

---

## LangChain LCEL là gì?

**LangChain Expression Language** — dùng toán tử `|` (pipe) để kết nối các components, giống Unix pipe:

```python
# chain.py:84-92
self._chain = (
    {
        "context": self._retrieve_and_format,   # async fn: query → str
        "question": RunnablePassthrough(),       # pass thẳng input
    }
    | RAG_PROMPT          # ChatPromptTemplate: inject context + question
    | self._llm           # ChatOpenAI: generate
    | StrOutputParser()   # extract .content từ AIMessage → str
)
```

Khi gọi `chain.ainvoke("What is RAG?")`:
1. `{"context": ..., "question": ...}` chạy song song → dict
2. Dict inject vào `RAG_PROMPT` → `ChatPromptValue`
3. LLM nhận prompt → trả về `AIMessage`
4. `StrOutputParser` extract `.content` → str

---

## System Prompt

```python
# chain.py:38-48
RAG_SYSTEM_PROMPT = """You are a helpful assistant...

Rules:
1. Answer ONLY based on the context below. Do NOT use outside knowledge.
2. Always cite your sources using [filename, page X] format.
3. If the context doesn't contain enough information, say "I don't have enough information..."
"""
```

Rule 1 ngăn model hallucinate — chỉ dùng context được cung cấp.  
Rule 2 buộc model cite source → user biết thông tin từ đâu.  
Rule 3 tránh model bịa khi không có thông tin.

```python
# chain.py:50-52
RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    ("human", "{question}"),     # {context} được inject vào system prompt
])
```

---

## Format context

```python
# chain.py:56
def _format_docs(docs: list[Document]) -> str:
    parts = []
    for doc in docs:
        filename = doc.metadata.get("source_filename", "unknown")
        page = doc.metadata.get("page", "")
        source = f"{filename}" + (f", page {page}" if page else "")
        parts.append(f"[{source}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)
```

Output ví dụ:
```
[ARCHITECTURE.md]
## 1. llama.cpp (llama-server)
llama-server expose API giống hệt OpenAI format...

---

[SETUP.md, page 2]
Bước 3: Start Docker services...
```

`---` ngăn cách giúp model nhận biết ranh giới giữa các nguồn khác nhau.

---

## Retrieve + format (async)

```python
# chain.py:95-97
async def _retrieve_and_format(self, question: str) -> str:
    docs = await self._retriever.retrieve(question)   # HybridRetriever
    return _format_docs(docs)
```

Đây là function được pass vào LCEL chain như 1 `Runnable` — LCEL tự handle async.

---

## Streaming

```python
# chain.py:105
async def stream(self, question: str) -> AsyncGenerator[str, None]:
    async for chunk in self._chain.astream(question):
        yield chunk
```

`astream()` — LangChain LCEL method, stream tokens từ LLM qua toàn bộ chain.  
`yield chunk` — re-yield từng token lên caller (`chat.py:67`).

---

## Non-streaming với sources

```python
# chain.py:111
async def retrieve_with_answer(self, question: str) -> dict:
    docs = await self._retriever.retrieve(question)
    context = _format_docs(docs)
    messages = RAG_PROMPT.format_messages(context=context, question=question)
    response = await self._llm.ainvoke(messages)   # chain.py:118

    sources = [
        {
            "filename": d.metadata.get("source_filename", ""),
            "snippet": d.page_content[:200],  # 200 ký tự đầu
        }
        for d in docs
    ]
    return {"answer": response.content, "sources": sources}
```

Trả về cả `answer` + `sources` → API response có metadata (dùng khi `stream=false`).

---

## Thử ngay

```bash
# Đảm bảo đã seed: bash scripts/seed-documents.sh

cd backend
python3 -c "
import asyncio
from src.rag.chain import RAGChain

async def test():
    chain = RAGChain()

    # Non-streaming với sources
    result = await chain.retrieve_with_answer('What is the Nexus AI architecture?')
    print('Answer:', result['answer'][:300])
    print('Sources:', [s['filename'] for s in result['sources']])

asyncio.run(test())
"
```

---

**Bài trước**: [05 — Hybrid Retriever](./05-hybrid-retriever.md)
**Bài tiếp theo**: [07 — Chat API & SSE](./07-chat-api-sse.md)
