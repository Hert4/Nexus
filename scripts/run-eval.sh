#!/usr/bin/env bash
# scripts/run-eval.sh — Chạy evaluation suite và xuất báo cáo
#
# Usage:
#   bash scripts/run-eval.sh                        # full eval, tất cả categories
#   bash scripts/run-eval.sh --category factual     # chỉ factual
#   bash scripts/run-eval.sh --limit 10             # 10 cases đầu
#   bash scripts/run-eval.sh --category code --limit 5
#
# Output:
#   data/eval-reports/eval-<timestamp>.json    — full JSON report
#   data/eval-reports/eval-<timestamp>.md      — markdown summary

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="$ROOT/data/eval-reports"
mkdir -p "$REPORT_DIR"

# ── Parse args ─────────────────────────────────────────────────────────────────
CATEGORY=""
LIMIT=0
API_URL="${EVAL_API_URL:-http://localhost:8000}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --category) CATEGORY="$2"; shift 2 ;;
        --limit)    LIMIT="$2";    shift 2 ;;
        --api-url)  API_URL="$2";  shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_JSON="$REPORT_DIR/eval-${TIMESTAMP}.json"
REPORT_MD="$REPORT_DIR/eval-${TIMESTAMP}.md"

echo "================================================="
echo " Nexus AI — Evaluation Runner"
echo " API: $API_URL"
echo " Category: ${CATEGORY:-all}"
echo " Limit: ${LIMIT:-all}"
echo "================================================="

# ── 1. Check API health ────────────────────────────────────────────────────────
echo ""
echo "🔍 Checking API health..."
if ! curl -sf "$API_URL/health" > /dev/null; then
    echo "❌ API not reachable at $API_URL"
    echo "   Run: make up (Docker) or make serve + make up"
    exit 1
fi
echo "✓ API is up"

# ── 2. Trigger eval run ────────────────────────────────────────────────────────
echo ""
echo "🚀 Starting eval run..."

PAYLOAD="{\"limit\": $LIMIT, \"concurrency\": 3"
if [ -n "$CATEGORY" ]; then
    PAYLOAD="${PAYLOAD}, \"category\": \"$CATEGORY\""
fi
PAYLOAD="${PAYLOAD}}"

RESPONSE=$(curl -sf -X POST "$API_URL/v1/eval/run" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

RUN_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
N_CASES=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['n_cases'])")

echo "✓ Run started: $RUN_ID ($N_CASES cases)"
echo ""
echo -n "⏳ Waiting for completion"

# ── 3. Poll for results ────────────────────────────────────────────────────────
MAX_WAIT=300  # 5 minutes max
ELAPSED=0
RESULT=""

while [ $ELAPSED -lt $MAX_WAIT ]; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))

    STATUS_RESP=$(curl -sf "$API_URL/v1/eval/results/$RUN_ID" 2>/dev/null || echo '{"status":"error"}')
    STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")

    if [ "$STATUS" = "done" ]; then
        echo ""
        echo "✓ Eval complete (${ELAPSED}s)"
        RESULT="$STATUS_RESP"
        break
    elif [ "$STATUS" = "error" ]; then
        echo ""
        echo "❌ Eval run failed"
        echo "$STATUS_RESP" | python3 -m json.tool
        exit 1
    else
        echo -n "."
    fi
done

if [ -z "$RESULT" ]; then
    echo ""
    echo "⏰ Timeout — eval still running. Check: GET $API_URL/v1/eval/results/$RUN_ID"
    exit 1
fi

# ── 4. Save JSON report ────────────────────────────────────────────────────────
echo "$RESULT" | python3 -m json.tool > "$REPORT_JSON"
echo "📄 JSON report: $REPORT_JSON"

# ── 5. Generate Markdown summary ──────────────────────────────────────────────
python3 - <<'PYEOF' "$REPORT_JSON" "$REPORT_MD" "$RUN_ID" "$TIMESTAMP"
import json, sys
from pathlib import Path

report_path, md_path, run_id, timestamp = sys.argv[1:]
data = json.loads(Path(report_path).read_text())
result = data.get("result", data)

lines = [
    f"# Nexus AI Eval Report",
    f"",
    f"**Run ID**: `{run_id}`  ",
    f"**Timestamp**: {timestamp}  ",
    f"**Model**: {result.get('model', 'unknown')}  ",
    f"**Cases evaluated**: {result.get('n', 0)}  ",
    f"**Failed**: {result.get('failed', 0)}",
    f"",
    f"## Overall Scores",
    f"",
]

overall = result.get("overall", {})
if overall:
    mean = overall.get("mean", 0)
    ci = overall.get("ci_95", (0, 0))
    lines += [
        f"| Metric | Mean | 95% CI |",
        f"|--------|------|--------|",
        f"| Overall | **{mean:.3f}** | [{ci[0]:.3f}, {ci[1]:.3f}] |",
    ]

for axis in ("completion", "quality", "faithfulness"):
    s = result.get(axis, {})
    if s:
        mean = s.get("mean", 0)
        ci = s.get("ci_95", (0, 0))
        lines.append(f"| {axis.title()} | {mean:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] |")

latency = result.get("latency_s", {})
if latency:
    lines += ["", f"**Avg latency**: {latency.get('mean', 0):.1f}s (p95: {latency.get('max', 0):.1f}s)"]

# By category
by_cat = result.get("by_category", {})
if by_cat:
    lines += ["", "## By Category", "", "| Category | Mean | N |", "|----------|------|---|"]
    for cat, stats in sorted(by_cat.items()):
        lines.append(f"| {cat} | {stats.get('mean', 0):.3f} | {stats.get('n', 0)} |")

Path(md_path).write_text("\n".join(lines))
print(f"📋 Markdown summary: {md_path}")
PYEOF

# ── 6. Print summary ──────────────────────────────────────────────────────────
echo ""
echo "================================================="
echo "✅ Eval complete!"
echo ""
python3 -c "
import json
from pathlib import Path
data = json.loads(Path('$REPORT_JSON').read_text())
r = data.get('result', data)
overall = r.get('overall', {})
print(f\"  Overall mean: {overall.get('mean', 0):.3f}\")
print(f\"  95% CI:       {overall.get('ci_95', (0,0))}\")
print(f\"  Cases:        {r.get('n', 0)}\")
print(f\"  Latency avg:  {r.get('latency_s', {}).get('mean', 0):.1f}s\")
by_cat = r.get('by_category', {})
if by_cat:
    print()
    for cat, s in sorted(by_cat.items()):
        print(f\"  {cat:12s}: {s.get('mean', 0):.3f}\")
"
echo "================================================="
