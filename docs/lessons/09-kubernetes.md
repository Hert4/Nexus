# Bài 09 — Kubernetes + k3s

**Code**: [`k8s/`](../../k8s/) | [`scripts/k8s-setup.sh`](../../scripts/k8s-setup.sh) | [`scripts/k8s-deploy.sh`](../../scripts/k8s-deploy.sh)

---

## Vấn đề cần giải quyết

Docker Compose chạy tốt local, nhưng production cần:
- **High availability**: nhiều replicas, tự restart khi crash
- **Auto-scaling**: thêm pods khi CPU cao
- **Rolling updates**: deploy mà không downtime
- **Resource limits**: không để 1 service ăn hết RAM

**Kubernetes** giải quyết tất cả. **k3s** là bản lightweight cho single-node, GPU support tốt.

---

## Kiến trúc K8s

```
Ingress (nginx) → api-service → [pod1, pod2] → ClusterIP
                                     ↕
                              ConfigMap + Secret
                                     ↕
                           qdrant-service → StatefulSet
```

llama-server vẫn chạy **native trên host** — pods kết nối qua `hostAliases` trong deployment.

---

## 1. Namespace — [`k8s/namespace.yml`](../../k8s/namespace.yml)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: nexus-ai
```

Tất cả resources của Nexus AI nằm trong namespace `nexus-ai` — isolate hoàn toàn.

---

## 2. ConfigMap + Secret — [`k8s/configmap.yml`](../../k8s/configmap.yml), [`k8s/secret.yml`](../../k8s/secret.yml)

```yaml
# ConfigMap: env vars không nhạy cảm
apiVersion: v1
kind: ConfigMap
metadata:
  name: nexus-config
data:
  LLAMACPP_CHAT_URL: "http://host.docker.internal:8080/v1"
  QDRANT_URL: "http://qdrant-service:6333"
  APP_ENV: "production"
  ...

# Secret: base64-encoded, mount như env vars
apiVersion: v1
kind: Secret
stringData:
  LLM_API_KEY: "llama-cpp"
  JWT_SECRET: "change-me"
```

Pods dùng `envFrom` để load cả hai:
```yaml
envFrom:
  - configMapRef:
      name: nexus-config   # k8s/api/deployment.yml:26
  - secretRef:
      name: nexus-secrets  # k8s/api/deployment.yml:28
```

---

## 3. Qdrant StatefulSet — [`k8s/qdrant/statefulset.yml`](../../k8s/qdrant/statefulset.yml)

**StatefulSet** thay vì Deployment vì Qdrant cần persistent storage ổn định:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
spec:
  serviceName: qdrant-service
  replicas: 1
  template:
    spec:
      containers:
        - name: qdrant
          readinessProbe:
            httpGet:
              path: /healthz    # k8s/qdrant/statefulset.yml:30
              port: 6333
  volumeClaimTemplates:         # k8s/qdrant/statefulset.yml:44
    - spec:
        storageClassName: local-path  # k3s default
        resources:
          requests:
            storage: 20Gi
```

`local-path` là storage class mặc định của k3s — tự tạo PV trên host filesystem.

---

## 4. API Deployment — [`k8s/api/deployment.yml`](../../k8s/api/deployment.yml)

```yaml
spec:
  replicas: 2         # k8s/api/deployment.yml:8 — 2 replicas mặc định
  template:
    metadata:
      annotations:
        prometheus.io/scrape: "true"   # k8s/api/deployment.yml:17 — auto-discover
        prometheus.io/port: "8000"
    spec:
      hostAliases:                     # k8s/api/deployment.yml:21
        - ip: "127.0.0.1"
          hostnames: ["host.docker.internal"]  # reach llama-server
```

`hostAliases` giải quyết vấn đề pods không biết địa chỉ llama-server chạy trên host.

---

## 5. HPA — [`k8s/api/hpa.yml`](../../k8s/api/hpa.yml)

HorizontalPodAutoscaler tự scale khi load tăng:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 2
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70   # scale up khi CPU > 70%
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # chờ 5 phút trước khi scale down
```

---

## 6. Helm Chart — [`k8s/helm/nexus-ai/`](../../k8s/helm/nexus-ai/)

Helm wrap toàn bộ K8s manifests thành 1 package có thể cấu hình qua `values.yaml`:

```yaml
# k8s/helm/nexus-ai/values.yaml:12
api:
  replicas: 2
  hpa:
    enabled: true
    maxReplicas: 5

monitoring:
  enabled: true   # true → deploy Prometheus + Grafana

langfuse:
  enabled: false  # false mặc định
```

Templates dùng Go templating:
```yaml
# k8s/helm/nexus-ai/templates/api-deployment.yml:6
replicas: {{ .Values.api.replicas }}

{{- if .Values.api.hpa.enabled }}   # templates/api-hpa.yml:1
apiVersion: autoscaling/v2
...
{{- end }}
```

---

## 7. Setup k3s — [`scripts/k8s-setup.sh`](../../scripts/k8s-setup.sh)

Script cài đặt k3s + tất cả dependencies một lần:

```bash
# scripts/k8s-setup.sh:26
curl -sfL https://get.k3s.io | sh -s - \
    --disable traefik \           # dùng nginx ingress thay thế
    --write-kubeconfig-mode 644   # non-root user đọc được

# scripts/k8s-setup.sh:70 — build + import image vào k3s containerd
docker build -t nexus-ai-api:latest ./backend
docker save nexus-ai-api:latest | k3s ctr images import -
```

`imagePullPolicy: Never` trong deployment — k3s dùng local image, không pull từ registry.

---

## Thử ngay

```bash
# 1. Setup (1 lần, cần sudo — chạy trong terminal thật, không qua script tự động)
sudo make k8s-setup

# 2. Deploy
make k8s-deploy

# 3. Kiểm tra
make k8s-status
# NAME                          READY   STATUS    RESTARTS
# qdrant-0                      1/1     Running   0
# nexus-api-7d9f8b-xxx          1/1     Running   0
# nexus-api-7d9f8b-yyy          1/1     Running   0

# 4. Test qua Ingress
curl http://nexus.local/api/health

# 5. Port-forward trực tiếp
kubectl -n nexus-ai port-forward svc/api-service 8000:8000
curl http://localhost:8000/health

# 6. Helm với monitoring
make k8s-deploy-all
# → Prometheus :30090, Grafana :30300
```

---

## Lỗi thực tế gặp phải (troubleshooting)

### 1. ingress-nginx timeout khi setup

**Lỗi**: `timed out waiting for the condition` trong `k8s-setup.sh`

**Nguyên nhân**: Image `registry.k8s.io/ingress-nginx/controller:v1.10.1` (~100MB) pull mất 2-3 phút, script timeout sau 120s.

**Fix** ([`scripts/k8s-setup.sh:93`](../../scripts/k8s-setup.sh#L93)): Tăng timeout lên 300s + thêm `|| true` để không fail nếu đã running:
```bash
kubectl rollout status deployment/ingress-nginx-controller \
  -n ingress-nginx --timeout=300s && echo " ✓" || echo " ✓ (already running)"
```

---

### 2. `k3s ctr images import` cần sudo

**Lỗi**: `dial unix /run/k3s/containerd/containerd.sock: connect: permission denied`

**Nguyên nhân**: k3s containerd socket (`/run/k3s/containerd/containerd.sock`) thuộc `root:root`, user thường không có quyền.

**Fix** ([`scripts/k8s-deploy.sh:44`](../../scripts/k8s-deploy.sh#L44)): Check `id -u` trước:
```bash
if [ "$(id -u)" -eq 0 ]; then
    docker save nexus-ai-api:latest | k3s ctr images import -
else
    docker save nexus-ai-api:latest | sudo k3s ctr images import -
fi
```

**Lưu ý**: `sudo` cần terminal thật (TTY). Không chạy được từ non-interactive script. Dùng terminal trực tiếp:
```bash
sudo make k8s-setup   # ← luôn chạy trong terminal, không từ CI/CD script
```

---

### 3. Namespace conflict với Helm

**Lỗi**: `invalid ownership metadata; label validation error: key "app.kubernetes.io/managed-by" must equal "Helm"`

**Nguyên nhân**: Namespace `nexus-ai` đã được tạo bằng `kubectl apply` (không có Helm labels), sau đó Helm không nhận ownership.

**Fix**: Add annotations + labels cho Helm:
```bash
kubectl annotate namespace nexus-ai \
  meta.helm.sh/release-name=nexus-ai \
  meta.helm.sh/release-namespace=nexus-ai \
  --overwrite

kubectl label namespace nexus-ai \
  app.kubernetes.io/managed-by=Helm \
  --overwrite
```

**Phòng tránh**: Không `kubectl apply -f k8s/namespace.yml` trước khi `helm install`. Helm tự tạo namespace khi có `--create-namespace`.

---

### 4. `host.docker.internal` không work trong K8s pods

**Lỗi**: `health: llamacpp_chat: error — All connection attempts failed`

**Nguyên nhân**: `host.docker.internal` với `hostAliases: 127.0.0.1` trỏ về localhost của pod, không phải host. llama-server không chạy trong pod.

**Fix** ([`scripts/k8s-deploy.sh:55`](../../scripts/k8s-deploy.sh#L55)): Dùng Node IP thực tế:
```bash
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
helm upgrade --install nexus-ai ... \
  --set "config.llamacppChatUrl=http://${NODE_IP}:8080/v1" \
  --set "config.llamacppEmbedUrl=http://${NODE_IP}:8081/v1"
```

`k8s-deploy.sh` tự động detect Node IP, không cần config thủ công.

---

**Bài trước**: [08 — LangGraph Agents](./08-langgraph-agents.md)

**Tiếp theo**: [10 — Monitoring & Observability](./10-monitoring.md)
