#!/usr/bin/env bash
# scripts/seed-documents.sh — Ingest sample documents để test RAG
set -e

API_URL="${API_URL:-http://localhost:8000}"
DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docs"

echo "=== Seeding documents from docs/ ==="
echo "API: $API_URL"

# Đợi API ready
echo "Waiting for API..."
for i in $(seq 1 30); do
  if curl -sf "$API_URL/health" > /dev/null 2>&1; then
    echo "✓ API is up"
    break
  fi
  sleep 2
  if [ $i -eq 30 ]; then
    echo "ERROR: API not responding after 60s"
    exit 1
  fi
done

# Upload tất cả .md files trong docs/
for file in "$DOCS_DIR"/*.md; do
  if [ -f "$file" ]; then
    filename=$(basename "$file")
    echo "Uploading: $filename"
    result=$(curl -sf -X POST "$API_URL/v1/documents" \
      -F "file=@$file" \
      2>&1) || { echo "  ERROR uploading $filename"; continue; }
    chunks=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['chunks_count'])" 2>/dev/null || echo "?")
    echo "  ✓ $filename → $chunks chunks"
  fi
done

echo ""
echo "=== Seeding done! ==="
echo "Test: curl -X POST $API_URL/v1/chat -H 'Content-Type: application/json' -d '{\"message\": \"What is the Nexus AI architecture?\", \"stream\": false}'"
