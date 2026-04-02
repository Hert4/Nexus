#!/usr/bin/env bash
# scripts/setup.sh — One-command setup cho Nexus AI
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== Nexus AI Setup ==="

# 1. Check Docker
if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker not found. Install Docker first."
  exit 1
fi
echo "✓ Docker found: $(docker --version)"

# 2. Check NVIDIA
if ! command -v nvidia-smi &>/dev/null; then
  echo "WARNING: nvidia-smi not found — GPU acceleration may not work"
else
  echo "✓ GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
fi

# 3. Check models symlinks
echo ""
echo "=== Checking models/ ==="
if [ ! -d "$ROOT/models" ]; then
  echo "ERROR: models/ directory not found"
  exit 1
fi

CHAT_MODEL="$ROOT/models/Qwen3.5-9B.Q6_K.gguf"
EMBED_MODEL="$ROOT/models/nomic-embed-text-v1.5.Q4_K_M.gguf"

for MODEL in "$CHAT_MODEL" "$EMBED_MODEL"; do
  if [ ! -f "$MODEL" ]; then
    echo "ERROR: Missing model: $MODEL"
    echo "       Tạo symlink: ln -s /path/to/model.gguf $MODEL"
    exit 1
  fi
  echo "✓ $(basename $MODEL) ($(du -sh "$MODEL" | cut -f1))"
done

# 4. Copy .env nếu chưa có
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "✓ Created .env from .env.example"
else
  echo "✓ .env already exists"
fi

echo ""
echo "=== Setup complete! ==="
echo "Run: make up"
