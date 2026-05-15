FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# npm 使用国内镜像（npmmirror.com）避免国内下载超时
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com

# Pre-install MCP server packages (build time, not runtime)
RUN npx -y mcp-searxng --help 2>/dev/null; \
    npx -y @modelcontextprotocol/server-filesystem --help 2>/dev/null; \
    true

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

RUN useradd -m -s /bin/bash prism \
    && mkdir -p /workspace /app/data/marketplace_cache /app/data/plugin_cache \
    && chown -R prism:prism /workspace /app/backend /app/data

# Pre-download embedding model as prism user (cached in /home/prism/.cache)
USER prism
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
USER root

EXPOSE 8000

# Alembic runs as root (needs DB perms), then switch to non-root for uvicorn
ENTRYPOINT ["sh", "-c", "alembic upgrade head && exec su prism -c 'uvicorn app.main:app --host 0.0.0.0 --port 8000'"]
