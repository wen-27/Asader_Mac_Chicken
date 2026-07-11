.PHONY: install install-local-services start-local-services stop-local-services chroma dev local tunnel migrate seed test health reindex webhook

# Create the Python 3.9 virtualenv and install the project in editable mode.
install:
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt && pip install -e .

# Informational target: local service binaries are managed outside Docker.
install-local-services:
	@echo "This project runs without Docker."
	@echo "PostgreSQL uses Postgres.app on localhost:5433."
	@echo "Redis is installed locally at .local/bin/redis-server."
	@echo "cloudflared is installed locally at .local/bin/cloudflared."

# Start the full local stack through the Python runner.
start-local-services:
	. .venv/bin/activate && python -m scripts.local_dev

# Stop common local processes started during bot testing.
stop-local-services:
	pkill -f ".local/bin/redis-server" || true
	pkill -f "chroma run" || true
	pkill -f "uvicorn app.main:app" || true

# Run ChromaDB manually when you do not want scripts.local_dev to manage it.
chroma:
	chroma run --host localhost --port 8001 --path ./.chroma

# Run only FastAPI. Redis/PostgreSQL/Chroma must already be running.
dev:
	uvicorn app.main:app --reload

# Alias for the standard local no-Docker stack.
local:
	. .venv/bin/activate && python -m scripts.local_dev

# Expose localhost:8000 through a public HTTPS URL for WhatsApp webhooks.
tunnel:
	.local/bin/cloudflared tunnel --protocol http2 --url http://localhost:8000

# Apply PostgreSQL schema migrations.
migrate:
	alembic upgrade head

# Upsert catalog, aliases and delivery zones.
seed:
	python -m scripts.seed

# Run the automated regression suite.
test:
	pytest

# Verify API and dependency health.
health:
	curl http://localhost:8000/health
	curl http://localhost:8000/health/dependencies

# Rebuild ChromaDB catalog vectors from PostgreSQL products and aliases.
reindex:
	curl -X POST http://localhost:8000/admin/catalog/reindex-vector-store

# Verify the WhatsApp webhook using PUBLIC_WEBHOOK_URL and WHATSAPP_VERIFY_TOKEN.
webhook:
	curl "$${PUBLIC_WEBHOOK_URL}/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=$${WHATSAPP_VERIFY_TOKEN}&hub.challenge=test"
