#!/usr/bin/env bash
# scripts/start-llamacpp.sh — Khởi động llama-server native trên host
# Chạy TRƯỚC khi make up
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Chat: CUDA-compiled binary (GPU acceleration cho LLM)
LLAMA_SERVER="/home/dev/Develop_2026/llama.cpp/build/bin/llama-server"
# Embed: Homebrew binary (CPU — nomic-embed GGUF không compat với build cũ)
LLAMA_SERVER_CPU="llama-server"

CHAT_MODEL="$ROOT/models/Qwen3.5-9B.Q6_K.gguf"
EMBED_MODEL="$ROOT/models/nomic-embed-text-v1.5.Q4_K_M.gguf"
CHAT_PORT=8080
EMBED_PORT=8081

# PID files để track processes
PID_DIR="$ROOT/.pids"
mkdir -p "$PID_DIR"

start_chat() {
    if [ -f "$PID_DIR/chat.pid" ] && kill -0 "$(cat $PID_DIR/chat.pid)" 2>/dev/null; then
        echo "✓ llama-server chat đang chạy (PID $(cat $PID_DIR/chat.pid))"
        return
    fi
    echo "Starting llama-server chat (port $CHAT_PORT, model: Qwen3.5-9B.Q6_K)..."
    "$LLAMA_SERVER" \
        --model "$CHAT_MODEL" \
        --alias "$(basename $CHAT_MODEL)" \
        --host 0.0.0.0 \
        --port $CHAT_PORT \
        --ctx-size 8192 \
        --n-gpu-layers 99 \
        --parallel 4 \
        --flash-attn on \
        > "$ROOT/.pids/chat.log" 2>&1 &
    echo $! > "$PID_DIR/chat.pid"
    echo "  PID: $(cat $PID_DIR/chat.pid) | Log: .pids/chat.log"
}

start_embed() {
    if [ -f "$PID_DIR/embed.pid" ] && kill -0 "$(cat $PID_DIR/embed.pid)" 2>/dev/null; then
        echo "✓ llama-server embed đang chạy (PID $(cat $PID_DIR/embed.pid))"
        return
    fi
    echo "Starting llama-server embed (port $EMBED_PORT, model: nomic-embed-text)..."
    "$LLAMA_SERVER_CPU" \
        --model "$EMBED_MODEL" \
        --alias "$(basename $EMBED_MODEL)" \
        --host 0.0.0.0 \
        --port $EMBED_PORT \
        --n-gpu-layers 99 \
        --embedding \
        --pooling mean \
        > "$ROOT/.pids/embed.log" 2>&1 &
    echo $! > "$PID_DIR/embed.pid"
    echo "  PID: $(cat $PID_DIR/embed.pid) | Log: .pids/embed.log"
}

wait_ready() {
    local url=$1
    local name=$2
    echo -n "Waiting for $name..."
    for i in $(seq 1 60); do
        if curl -sf "$url/health" > /dev/null 2>&1; then
            echo " ready ✓"
            return 0
        fi
        echo -n "."
        sleep 2
    done
    echo " TIMEOUT ✗"
    return 1
}

stop_all() {
    for f in "$PID_DIR"/*.pid; do
        [ -f "$f" ] || continue
        pid=$(cat "$f")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "Stopped PID $pid ($(basename $f .pid))"
        fi
        rm -f "$f"
    done
}

case "${1:-start}" in
    start)
        start_embed
        start_chat
        wait_ready "http://localhost:$EMBED_PORT" "embed"
        wait_ready "http://localhost:$CHAT_PORT" "chat"
        echo ""
        echo "✅ Both llama-servers ready!"
        echo "   Chat:  http://localhost:$CHAT_PORT/v1"
        echo "   Embed: http://localhost:$EMBED_PORT/v1"
        ;;
    stop)
        stop_all
        echo "All stopped."
        ;;
    status)
        for name in chat embed; do
            f="$PID_DIR/$name.pid"
            if [ -f "$f" ] && kill -0 "$(cat $f)" 2>/dev/null; then
                echo "$name: running (PID $(cat $f))"
            else
                echo "$name: stopped"
            fi
        done
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
