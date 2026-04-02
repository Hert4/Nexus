#!/usr/bin/env bash
# scripts/k8s-setup.sh — Cài k3s, nvidia device plugin, và deploy Nexus AI
#
# Chạy 1 lần trên host Linux có RTX 4070 Super:
#   sudo bash scripts/k8s-setup.sh
#
# Sau đó dùng scripts/k8s-deploy.sh để update

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="nexus-ai"

echo "================================================="
echo " Nexus AI — K8s Setup (k3s)"
echo "================================================="

# ── 1. Cài k3s ────────────────────────────────────────────────────────────────
if command -v k3s &>/dev/null; then
    echo "✓ k3s đã cài ($(k3s --version | head -1))"
else
    echo ""
    echo "📦 Cài k3s..."
    # --disable traefik vì dùng nginx ingress
    # --write-kubeconfig-mode 644 để non-root user đọc được
    curl -sfL https://get.k3s.io | sh -s - \
        --disable traefik \
        --write-kubeconfig-mode 644

    # Chờ k3s sẵn sàng
    echo -n "Waiting for k3s..."
    for i in $(seq 1 30); do
        if k3s kubectl get nodes &>/dev/null; then
            echo " ready ✓"
            break
        fi
        echo -n "."
        sleep 3
    done
fi

# ── 2. Setup kubectl alias & KUBECONFIG ───────────────────────────────────────
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> ~/.bashrc || true

# Alias kubectl → k3s kubectl nếu chưa cài kubectl standalone
if ! command -v kubectl &>/dev/null; then
    echo 'alias kubectl="k3s kubectl"' >> ~/.bashrc || true
    alias kubectl="k3s kubectl"
fi

echo "✓ kubectl: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

# ── 3. Cài Helm ───────────────────────────────────────────────────────────────
if command -v helm &>/dev/null; then
    echo "✓ Helm đã cài ($(helm version --short))"
else
    echo ""
    echo "📦 Cài Helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    echo "✓ Helm $(helm version --short)"
fi

# ── 4. Nvidia device plugin (GPU support trong K8s) ───────────────────────────
echo ""
echo "🔧 Setup NVIDIA device plugin..."

# Kiểm tra nvidia-smi trước
if ! command -v nvidia-smi &>/dev/null; then
    echo "⚠ nvidia-smi không tìm thấy — bỏ qua GPU plugin"
    echo "  GPU support cần NVIDIA driver đã cài trên host"
else
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    echo "✓ GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1) (${GPU_COUNT} cards)"

    # k3s containerd runtime cần nvidia-container-runtime
    if ! command -v nvidia-container-runtime &>/dev/null; then
        echo "⚠ nvidia-container-runtime chưa cài"
        echo "  Cài theo: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    else
        # Apply nvidia device plugin daemonset
        kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.15.0/deployments/static/nvidia-device-plugin.yml
        echo "✓ NVIDIA device plugin applied"
    fi
fi

# ── 5. Cài nginx ingress controller ───────────────────────────────────────────
echo ""
echo "📦 Cài nginx ingress controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/cloud/deploy.yaml

# Chờ ingress controller sẵn sàng (image pull có thể mất 3-5 phút)
echo -n "Waiting for ingress-nginx (có thể mất vài phút để pull image)..."
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=300s && echo " ✓" || echo " ✓ (already running)"

# ── 6. Build và import image vào k3s registry ─────────────────────────────────
echo ""
echo "🔨 Build nexus-ai-api Docker image..."
docker build -t nexus-ai-api:latest "$ROOT/backend"

echo "📤 Import image vào k3s containerd..."
# k3s ctr socket thuộc group root — chạy với sudo
if [ "$(id -u)" -eq 0 ]; then
    docker save nexus-ai-api:latest | k3s ctr images import -
else
    docker save nexus-ai-api:latest | sudo k3s ctr images import -
fi
echo "✓ Image imported: nexus-ai-api:latest"

# ── 7. Tạo namespace ──────────────────────────────────────────────────────────
echo ""
kubectl apply -f "$ROOT/k8s/namespace.yml"

# ── 8. Thêm /etc/hosts cho nexus.local ───────────────────────────────────────
if ! grep -q "nexus.local" /etc/hosts; then
    if [ "$(id -u)" -eq 0 ]; then
        echo "127.0.0.1 nexus.local" >> /etc/hosts
    else
        echo "127.0.0.1 nexus.local" | sudo tee -a /etc/hosts > /dev/null
    fi
    echo "✓ Thêm nexus.local vào /etc/hosts"
fi

echo ""
echo "================================================="
echo "✅ K8s setup hoàn tất!"
echo ""
echo "Next steps:"
echo "  bash scripts/k8s-deploy.sh        # Deploy Nexus AI"
echo "  kubectl -n nexus-ai get pods       # Xem pods"
echo "  export KUBECONFIG=/etc/rancher/k3s/k3s.yaml"
echo "================================================="
