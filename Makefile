.PHONY: help setup setup-next up up-with-commands up-next up-next-with-commands down down-next logs logs-next build clean

COMPOSE      = docker compose -f docker-compose.yml
COMPOSE_NEXT = docker compose -f docker-compose-next.yml

SECRETS_DIR  = backend/runtime/secrets
SECRETS_FILE = $(SECRETS_DIR)/postgres_password_secret

# ──────────────────────────────────────────────────────────────────────────────
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ──────────────────────────────────────────────────────────────────────────────
setup: ## Copy .env.*.example files and scaffold secrets (skips existing files)
	@echo "Copying environment files..."
	@cp -n .env.backend.example            .env.backend            && echo "  created .env.backend"            || echo "  skipped .env.backend (exists)"
	@cp -n .env.db.example                 .env.db                 && echo "  created .env.db"                 || echo "  skipped .env.db (exists)"
	@cp -n .env.proxy.example              .env.proxy              && echo "  created .env.proxy"              || echo "  skipped .env.proxy (exists)"
	@cp -n .env.ingester.example           .env.ingester           && echo "  created .env.ingester"           || echo "  skipped .env.ingester (exists)"
	@cp -n .env.pending_aggregations.example .env.pending_aggregations && echo "  created .env.pending_aggregations" || echo "  skipped .env.pending_aggregations (exists)"
	@cp -n dashboard/.env.example          dashboard/.env          && echo "  created dashboard/.env"          || echo "  skipped dashboard/.env (exists)"
	@echo "Scaffolding secrets..."
	@mkdir -p $(SECRETS_DIR)
	@if [ ! -f $(SECRETS_FILE) ]; then \
		echo "change_me" > $(SECRETS_FILE) && echo "  created $(SECRETS_FILE) — replace 'change_me' with a real password"; \
	else \
		echo "  skipped $(SECRETS_FILE) (exists)"; \
	fi
	@echo "Done. Edit the generated files before running 'make up'."

setup-next: ## Copy .env.example → .env (for docker-compose-next.yml, skips if exists)
	@echo "Copying environment file..."
	@cp -n .env.example   .env           && echo "  created .env"           || echo "  skipped .env (exists)"
	@cp -n dashboard/.env.example dashboard/.env && echo "  created dashboard/.env" || echo "  skipped dashboard/.env (exists)"
	@echo "Done. Edit .env before running 'make up-next'."

# ──────────────────────────────────────────────────────────────────────────────
up: ## Build images and start all services  [default]
	$(COMPOSE) up --build -d

up-with-commands: ## Build images and start all services including ingester + aggregations
	$(COMPOSE) --profile=with_commands up --build -d

up-next: ## Pull pre-built images and start services (local-db profile)
	$(COMPOSE_NEXT) --profile=local-db up -d

up-next-with-commands: ## Pull pre-built images including ingester + aggregations (local-db)
	$(COMPOSE_NEXT) --profile=local-db --profile=with_commands up -d

down: ## Stop and remove containers
	$(COMPOSE) down

down-next: ## Stop and remove containers (docker-compose-next.yml)
	$(COMPOSE_NEXT) --profile=local-db down

logs: ## Tail logs for all running services
	$(COMPOSE) logs -f

logs-next: ## Tail logs (docker-compose-next.yml)
	$(COMPOSE_NEXT) logs -f

build: ## Build images without starting containers
	$(COMPOSE) build

clean: ## Stop all services and remove volumes  ⚠ destroys data
	$(COMPOSE) down -v
