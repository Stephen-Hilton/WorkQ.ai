# WorkQ.ai — convenience targets.
# All real work happens in scripts/. Targets here are thin wrappers.

.PHONY: help install validate deploy publish publish-prompts dev sam-sync \
        monitor monitor-bg test typecheck lint clean

# Default target prints help.
help:
	@echo "WorkQ.ai — make targets:"
	@echo ""
	@echo "  Setup:"
	@echo "    install            uv sync (apis + local) and pnpm install (webapp)"
	@echo ""
	@echo "  Validation:"
	@echo "    validate           run validate_prompt_parts.py + lint + typecheck"
	@echo "    test               run pytest + vitest"
	@echo "    typecheck          mypy + tsc"
	@echo "    lint               ruff + eslint"
	@echo ""
	@echo "  Deploy:"
	@echo "    deploy             sam deploy (infra only)"
	@echo "    publish            full pipeline: deploy + build + s3 sync + invalidate"
	@echo "    publish-prompts    derive app.json from config/prompt_parts.yaml + upload + invalidate"
	@echo "    sam-sync           sam sync --watch (fast Lambda code iteration)"
	@echo ""
	@echo "  Run:"
	@echo "    dev                Vite dev server for the webapp on :5173"
	@echo "    monitor            python -m local.monitor (foreground, logs to stdout + file)"
	@echo "    monitor-bg         python -m local.monitor in background, tail log"
	@echo ""
	@echo "  Cleanup:"
	@echo "    clean              remove build artifacts (dist, .venv, __pycache__)"

install:
	cd apis && uv sync
	cd local && uv sync
	cd ui/webapp && pnpm install

validate:
	python3 scripts/validate_prompt_parts.py config/prompt_parts.yaml
	cd apis && uv run ruff check . && uv run mypy .
	cd local && uv run ruff check . && uv run mypy .
	cd ui/webapp && pnpm run lint && pnpm run typecheck

test:
	cd apis && uv run pytest
	cd local && uv run pytest
	cd ui/webapp && pnpm run test

typecheck:
	cd apis && uv run mypy .
	cd local && uv run mypy .
	cd ui/webapp && pnpm run typecheck

lint:
	cd apis && uv run ruff check .
	cd local && uv run ruff check .
	cd ui/webapp && pnpm run lint

deploy:
	bash scripts/publish.sh --infra-only

publish:
	bash scripts/publish.sh

publish-prompts:
	bash scripts/publish.sh --prompts-only

sam-sync:
	cd infra && sam sync --watch --stack-name $${WORKQ_STACK_NAME:-workq}

dev:
	cd ui/webapp && pnpm run dev

monitor:
	cd local && uv run python -m monitor

monitor-bg:
	mkdir -p local/logs
	cd local && nohup uv run python -m monitor >> logs/monitor.stdout.log 2>&1 &
	@echo "monitor started in background; tail -f local/logs/monitor.log"

clean:
	rm -rf ui/webapp/dist ui/webapp/.vite
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .venv -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
