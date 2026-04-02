.PHONY: up down logs logs-chat logs-embed setup serve serve-stop serve-status test lint build monitor-up monitor-down k8s-setup k8s-deploy k8s-status k8s-down eval eval-factual eval-quick help

help:
	@echo "Nexus AI — available commands:"
	@echo ""
	@echo "  === llama-server (native, chạy trên host) ==="
	@echo "  make serve       Start cả chat + embed llama-server"
	@echo "  make serve-stop  Stop cả hai"
	@echo "  make serve-status Status"
	@echo ""
	@echo "  === Docker (qdrant + api) ==="
	@echo "  make up          docker compose up -d"
	@echo "  make down        docker compose down"
	@echo "  make logs        Stream API logs"
	@echo "  make logs-chat   Tail llama-server chat log"
	@echo "  make logs-embed  Tail llama-server embed log"
	@echo ""
	@echo "  === Monitoring (local Docker) ==="
	@echo "  make monitor-up  Start Prometheus + Grafana"
	@echo "  make monitor-down Stop monitoring stack"
	@echo ""
	@echo "  === Evaluation ==="
	@echo "  make eval         Run full eval suite"
	@echo "  make eval-factual Run factual cases only"
	@echo "  make eval-quick   Run 10 cases (fast sanity check)"
	@echo ""
	@echo "  === Kubernetes (k3s) ==="
	@echo "  make k8s-setup   Cài k3s + nginx ingress (chạy 1 lần, cần sudo)"
	@echo "  make k8s-deploy  Build + deploy lên k3s qua Helm"
	@echo "  make k8s-status  Xem pods/services trong nexus-ai namespace"
	@echo "  make k8s-down    Uninstall Helm release"
	@echo ""
	@echo "  === Dev ==="
	@echo "  make setup       Check models + copy .env"
	@echo "  make test        Run pytest"
	@echo "  make lint        Run ruff linter"
	@echo "  make build       Rebuild API image"

# ── llama-server (native on host) ──────────────────────────────────────────────
serve:
	bash scripts/start-llamacpp.sh start

serve-stop:
	bash scripts/start-llamacpp.sh stop

serve-status:
	bash scripts/start-llamacpp.sh status

logs-chat:
	tail -f .pids/chat.log

logs-embed:
	tail -f .pids/embed.log

# ── Docker ─────────────────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f api

# ── Monitoring ─────────────────────────────────────────────────────────────────
monitor-up:
	docker network create nexus-network 2>/dev/null || true
	docker compose -f docker-compose.monitoring.yml up -d
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3001  (admin/admin)"

monitor-down:
	docker compose -f docker-compose.monitoring.yml down

# ── Kubernetes ─────────────────────────────────────────────────────────────────
k8s-setup:
	sudo bash scripts/k8s-setup.sh

k8s-deploy:
	bash scripts/k8s-deploy.sh

k8s-deploy-all:
	bash scripts/k8s-deploy.sh --all

k8s-status:
	kubectl -n nexus-ai get pods,svc,hpa

k8s-down:
	helm uninstall nexus-ai -n nexus-ai || true

eval:
	bash scripts/run-eval.sh

eval-factual:
	bash scripts/run-eval.sh --category factual

eval-quick:
	bash scripts/run-eval.sh --limit 10

# ── Setup ──────────────────────────────────────────────────────────────────────
setup:
	@echo "=== Checking models/ ==="
	@ls -la models/*.gguf || (echo "ERROR: No GGUF symlinks in models/" && exit 1)
	@echo ""
	@if [ ! -f .env ]; then cp .env.example .env && echo "Copied .env.example → .env"; else echo ".env already exists"; fi
	@echo ""
	@echo "Next steps:"
	@echo "  1. make serve   (start llama-server on host)"
	@echo "  2. make up      (start qdrant + api via docker)"

# ── Dev ────────────────────────────────────────────────────────────────────────
test:
	cd backend && python -m pytest tests/ -v

lint:
	cd backend && ruff check src/

build:
	docker compose build api
