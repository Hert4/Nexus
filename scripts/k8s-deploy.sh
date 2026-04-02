#!/usr/bin/env bash
# scripts/k8s-deploy.sh — Deploy/update Nexus AI lên k3s qua Helm
#
# Cần chạy k8s-setup.sh trước (1 lần).
# Dùng script này mỗi khi có code thay đổi.
#
# Usage:
#   bash scripts/k8s-deploy.sh              # deploy với defaults
#   bash scripts/k8s-deploy.sh --monitoring # enable Prometheus + Grafana
#   bash scripts/k8s-deploy.sh --langfuse   # enable Langfuse tracing
#   bash scripts/k8s-deploy.sh --all        # enable tất cả

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="nexus-ai"
RELEASE="nexus-ai"
CHART="$ROOT/k8s/helm/nexus-ai"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

# ── Parse flags ───────────────────────────────────────────────────────────────
ENABLE_MONITORING=false
ENABLE_LANGFUSE=false

for arg in "$@"; do
    case $arg in
        --monitoring) ENABLE_MONITORING=true ;;
        --langfuse)   ENABLE_LANGFUSE=true   ;;
        --all)        ENABLE_MONITORING=true; ENABLE_LANGFUSE=true ;;
    esac
done

echo "================================================="
echo " Nexus AI — K8s Deploy"
echo " Monitoring: $ENABLE_MONITORING"
echo " Langfuse:   $ENABLE_LANGFUSE"
echo "================================================="

# ── Rebuild + re-import image ─────────────────────────────────────────────────
echo ""
echo "🔨 Rebuild Docker image..."
docker build -t nexus-ai-api:latest "$ROOT/backend"
if [ "$(id -u)" -eq 0 ]; then
    docker save nexus-ai-api:latest | k3s ctr images import -
else
    docker save nexus-ai-api:latest | sudo k3s ctr images import -
fi
echo "✓ nexus-ai-api:latest imported"

# ── Helm deploy ───────────────────────────────────────────────────────────────
echo ""
echo "🚀 Helm upgrade --install $RELEASE..."

# Auto-detect Node IP để pods reach llama-server trên host
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "")
if [ -z "$NODE_IP" ]; then
    NODE_IP=$(ip route get 1 | awk '{print $7; exit}')
fi
echo "  Node IP (llama-server): $NODE_IP"

HELM_ARGS=(
    upgrade --install "$RELEASE" "$CHART"
    --namespace "$NAMESPACE"
    --create-namespace
    --set "monitoring.enabled=$ENABLE_MONITORING"
    --set "langfuse.enabled=$ENABLE_LANGFUSE"
    --set "config.llamacppChatUrl=http://${NODE_IP}:8080/v1"
    --set "config.llamacppEmbedUrl=http://${NODE_IP}:8081/v1"
    --wait
    --timeout 5m
)

helm "${HELM_ARGS[@]}"

# ── Status ────────────────────────────────────────────────────────────────────
echo ""
echo "📊 Pod status:"
kubectl -n "$NAMESPACE" get pods

echo ""
echo "🌐 Services:"
kubectl -n "$NAMESPACE" get svc

echo ""
echo "================================================="
echo "✅ Deploy hoàn tất!"
echo ""
echo "  API:         http://nexus.local/api/health"
echo "  API direct:  kubectl -n $NAMESPACE port-forward svc/api-service 8000:8000"

if [ "$ENABLE_MONITORING" = "true" ]; then
    echo "  Prometheus:  http://NODE_IP:30090"
    echo "  Grafana:     http://NODE_IP:30300  (admin/admin)"
fi

if [ "$ENABLE_LANGFUSE" = "true" ]; then
    echo "  Langfuse:    http://NODE_IP:30302"
fi

echo ""
echo "  kubectl -n $NAMESPACE logs -l app=nexus-api --follow"
echo "================================================="
