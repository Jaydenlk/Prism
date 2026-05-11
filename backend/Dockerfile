FROM python:3.12-slim

WORKDIR /app

# System deps (git required for Session 4c SourceResolver 3/4 — git clone + sparse-checkout)
# nodejs+npm required for npx-based MCP servers (brave-search, tavily)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Python deps (build context = repo root so we can COPY executor/)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend package + executor package so subprocess can import executor
COPY backend /app/backend
COPY executor /app/executor
COPY executor_v2 /app/executor_v2

# Make both importable: cwd = /app means `from app.*` (via backend/app) still
# resolves if we cd into backend, AND `from executor.*` resolves directly.
# We chose: run uvicorn from /app with PYTHONPATH=/app:/app/backend so both
# `app.*` (FastAPI router imports) and `executor.*` (subprocess imports) work.
ENV PYTHONPATH=/app:/app/backend
WORKDIR /app/backend

RUN useradd -m -s /bin/bash prism

EXPOSE 8000

# Alembic runs as root (needs DB perms), then switch to non-root for uvicorn
ENTRYPOINT ["sh", "-c", "alembic upgrade head && exec su prism -c 'uvicorn app.main:app --host 0.0.0.0 --port 8000'"]
