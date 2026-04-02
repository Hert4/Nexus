# Bài 08 — LangGraph Agent System

**Code**: [`backend/src/agents/`](../../backend/src/agents/)

---

## Vấn đề cần giải quyết

Chat RAG (bài 06) chỉ làm 1 việc: retrieve → generate. Nhưng có tasks phức tạp hơn cần nhiều bước: research, viết code, review kết quả, retry nếu chưa đủ tốt.

**LangGraph** giải quyết điều này bằng **state machine**: các nodes (functions) được kết nối bằng edges, state được truyền qua từng node.

---

## Kiến trúc graph

```
START → planner → researcher → [coder?] → reviewer → END
                      ↑                        │
                      └──── retry (max 2) ─────┘
```

File: [`agents/graph.py`](../../backend/src/agents/graph.py)

---

## 1. AgentState — [`agents/state.py:17`](../../backend/src/agents/state.py#L17)

State là "bộ nhớ" chung truyền qua tất cả nodes:

```python
class AgentState(TypedDict):
    messages:     Annotated[Sequence[BaseMessage], add_messages]  # state.py:32
    task:         str          # state.py:33 — task gốc từ user, không thay đổi
    plan:         list[str]    # state.py:34 — do planner tạo ra
    current_step: int          # state.py:35 — index step đang làm
    tool_results: list[dict]   # state.py:36 — kết quả từ search, code exec, ...
    final_answer: str          # state.py:37 — answer cuối khi reviewer approve
    needs_review: bool         # state.py:38 — flag reviewer set
    retry_count:  int          # state.py:39 — đếm số lần retry
```

`Annotated[Sequence, add_messages]` — LangGraph dùng `add_messages` reducer: các messages mới được **append** thay vì overwrite.

---

## 2. Build graph — [`agents/graph.py:56`](../../backend/src/agents/graph.py#L56)

```python
graph = StateGraph(AgentState)  # graph.py:58

# Thêm 4 nodes
graph.add_node("planner",    planner_node)    # graph.py:65
graph.add_node("researcher", researcher_node) # graph.py:66
graph.add_node("coder",      coder_node)      # graph.py:67
graph.add_node("reviewer",   reviewer_node)   # graph.py:68

# Fixed edges
graph.add_edge(START, "planner")      # graph.py:71
graph.add_edge("planner", "researcher")  # graph.py:72
graph.add_edge("coder", "reviewer")   # graph.py:73

# Conditional edge: researcher → coder hay reviewer?
graph.add_conditional_edges("researcher", _needs_coder, ...)  # graph.py:76

# Conditional edge: reviewer → retry hay END?
graph.add_conditional_edges("reviewer", _reviewer_decision, ...)  # graph.py:83

compiled = graph.compile()  # graph.py:90
```

---

## 3. Conditional edges

### researcher → coder? ([`graph.py:38`](../../backend/src/agents/graph.py#L38))

```python
_CODE_TASK_KEYWORDS = {"code", "script", "calculate", "python", ...}

def _needs_coder(state) -> str:
    task = state["task"].lower()
    if any(kw in task for kw in _CODE_TASK_KEYWORDS):
        return "coder"   # → coder node
    return "reviewer"    # → reviewer trực tiếp
```

### reviewer → retry hay END? ([`graph.py:47`](../../backend/src/agents/graph.py#L47))

```python
def _reviewer_decision(state) -> str:
    if state.get("needs_review", False):
        return "researcher"  # retry
    return END               # done
```

---

## 4. Các nodes

### planner ([`nodes/planner.py:29`](../../backend/src/agents/nodes/planner.py#L29))

- Nhận `task` → LLM decompose thành `list[str]` steps
- Output JSON array, parse tại [`planner.py:50-60`](../../backend/src/agents/nodes/planner.py#L50)
- Trả về: `{"plan": [...], "current_step": 0, "messages": [...]}`

### researcher ([`nodes/researcher.py:33`](../../backend/src/agents/nodes/researcher.py#L33))

- RAG retrieve từ Qdrant ([`researcher.py:44-53`](../../backend/src/agents/nodes/researcher.py#L44))
- Web search DuckDuckGo ([`researcher.py:56-62`](../../backend/src/agents/nodes/researcher.py#L56))
- LLM synthesize cả 2 nguồn thành research summary
- Trả về: `{"tool_results": [...], "messages": [...]}`

### coder ([`nodes/coder.py:32`](../../backend/src/agents/nodes/coder.py#L32))

- Chỉ chạy khi task cần code
- LLM generate Python code (`temperature=0.1` — deterministic)
- Execute trong sandbox ([`code_exec.py`](../../backend/src/agents/tools/code_exec.py)) với timeout 30s
- Trả về: `{"tool_results": [...code + output..., ], "messages": [...]}`

### reviewer ([`nodes/reviewer.py:54`](../../backend/src/agents/nodes/reviewer.py#L54))

- LLM review toàn bộ work, quyết định `PASS` hay `RETRY`
- Nếu PASS: extract/synthesize `final_answer`
- Nếu RETRY: set `needs_review=True`, `retry_count += 1`
- Max retries = 2 ([`reviewer.py:15`](../../backend/src/agents/nodes/reviewer.py#L15)) → force PASS sau đó

---

## 5. Tools

| Tool | File | Dùng cho |
|------|------|----------|
| `web_search` | [`tools/search.py`](../../backend/src/agents/tools/search.py) | DuckDuckGo, không cần API key |
| `execute_python` | [`tools/code_exec.py`](../../backend/src/agents/tools/code_exec.py) | Sandbox subprocess, timeout 30s |
| `calculator` | [`tools/calculator.py`](../../backend/src/agents/tools/calculator.py) | numexpr + eval restricted |
| `query_database` | [`tools/db_query.py`](../../backend/src/agents/tools/db_query.py) | SQLite SELECT only |

---

## 6. API endpoints — [`api/routes/agents.py`](../../backend/src/api/routes/agents.py)

### POST /v1/agents/run ([`agents.py:55`](../../backend/src/api/routes/agents.py#L55))

Chạy đến khi xong, trả về JSON:
```bash
curl -X POST http://localhost:8000/v1/agents/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Calculate fibonacci(10) with Python"}'
```

### WebSocket /v1/agents/ws ([`agents.py:74`](../../backend/src/api/routes/agents.py#L74))

Stream từng node event real-time:
```python
# agents.py:103
async for event in agent_graph.astream_events(state, version="v2"):
    kind = event["event"]   # "on_chain_start", "on_chain_end", "on_tool_start"
    name = event["name"]    # "planner", "researcher", ...
```

Event format:
```json
{"event": "node_start",    "node": "planner"}
{"event": "node_complete", "node": "planner", "output": "Plan: 3 steps..."}
{"event": "tool_call",     "tool": "web_search", "input": "fibonacci algorithm"}
{"event": "final_answer",  "content": "fibonacci(10) = 55"}
```

Test WebSocket:
```bash
# Dùng websocat
websocat ws://localhost:8000/v1/agents/ws <<< '{"task": "What is 2^10?"}'
```

---

## Thử ngay

```bash
# Non-streaming agent
curl -X POST http://localhost:8000/v1/agents/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Calculate 2 to the power of 10 using Python"}' \
  | python3 -m json.tool

# Xem graph structure (cần graphviz)
cd backend
python3 -c "
from src.agents.graph import agent_graph
print(agent_graph.get_graph().draw_ascii())
"
```

---

**Bài trước**: [07 — Chat API & SSE](./07-chat-api-sse.md)

**Tiếp theo**: Phase 3 — Kubernetes + Monitoring (`docs/lessons/09-kubernetes.md`)
