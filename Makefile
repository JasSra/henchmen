.PHONY: help install run test fmt clean docker-build docker-up docker-down build-agent run-agent install-agent-deps

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt

run: ## Run the controller locally
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

run-ui: ## Run controller and open UI in browser
	@echo "Starting DeployBot Controller..."
	@echo "UI will be available at http://localhost:8080"
	@(sleep 2 && open http://localhost:8080 2>/dev/null || xdg-open http://localhost:8080 2>/dev/null || echo "Please open http://localhost:8080 in your browser") &
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

test: ## Run tests
	pytest tests/ -v

fmt: ## Format code with black and isort
	black app/ cli/ tests/
	isort app/ cli/ tests/

clean: ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf data/*.db

docker-build: ## Build Docker image
	docker-compose build

docker-up: ## Start services with Docker Compose
	docker-compose up -d

docker-down: ## Stop services
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

cli-deploy: ## Example: Deploy via CLI (make cli-deploy REPO=org/repo REF=main HOST=web-01)
	python -m cli.ctl deploy --repo $(REPO) --ref $(REF) --host $(HOST)

cli-logs: ## Example: View logs via CLI
	python -m cli.ctl logs

cli-status: ## Example: Check job status (make cli-status JOB_ID=xxx)
	python -m cli.ctl status $(JOB_ID)

# Agent targets
install-agent-deps: ## Install Go dependencies for agent
	@echo "Installing Go dependencies..."
	cd cmd/deploybot-agent && go mod download && go mod tidy

build-agent: ## Build the deploybot agent binary
	@echo "Building deploybot agent..."
	cd cmd/deploybot-agent && go build -o ../../bin/deploybot-agent .
	@echo "Agent built successfully at bin/deploybot-agent"

run-agent: build-agent ## Build and run the agent
	@echo "Starting deploybot agent..."
	./bin/deploybot-agent

agent-help: ## Show agent setup instructions
	@echo "DeployBot Agent Setup"
	@echo "===================="
	@echo ""
	@echo "1. Install Go (if not installed):"
	@echo "   - Visit https://go.dev/dl/"
	@echo "   - Download the macOS installer for your architecture"
	@echo "   - Or use Homebrew: brew install go"
	@echo ""
	@echo "2. Build the agent:"
	@echo "   make build-agent"
	@echo ""
	@echo "3. Run the agent:"
	@echo "   make run-agent"
	@echo ""
	@echo "4. Configure the agent:"
	@echo "   Edit .env and set AGENT_HOSTNAME, CONTROLLER_URL, etc."
	@echo ""
