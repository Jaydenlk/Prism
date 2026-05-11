"""
Prism v2 — API v1 Router Aggregator

Registers all v1 sub-routers and mounts them under /api/v1.

Routers:
  health     — /health/live + /health/ready + /health/detailed (DOC-12 Task 12.3, ADR-114)
  auth       — JWT login / register / refresh / logout / me / sse-ticket (DOC-06 Task 6.1)
  admin      — User management + invite codes + usage + audit logs (DOC-06 Task 6.2)
  providers  — Provider CRUD + presets + test (DOC-02 Task 2.3)
  harness    — GET /harness/config readonly (DOC-03 Task 3.6)
  skills     — Skills Market search/install/uninstall (DOC-05 Task 5.6)
  plugins    — Plugin load/validate/export-cc (DOC-05 Task 5.7)
  sessions   — Session CRUD + message incremental + SSE stream + permission-answer (DOC-07 Task 7.1/7.3)
  tasks      — POST /tasks + queue + cancel (DOC-07 Task 7.2)
  runs       — GET /runs/{id} + /sessions/{id}/runs + POST /runs/{id}/resume (DOC-07 Task 7.2/7.4)
  internal   — Callback + run-crashed (DOC-07 Task 7.3, ADR-063)
  im         — IM channels config + Webhook + bindings (DOC-08 Task 8.1)
  mcp        — MCP Server CRUD + install/uninstall (DOC-09 Task 9.1)
  frontend   — POST /frontend-errors receiver (DOC-12 Task 12.7, ADR-119)
  memories   — Memory CRUD + search via mem0 (GET/POST/DELETE/search)
"""
from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.providers import router as providers_router
from app.api.v1 import harness
from app.api.v1.marketplaces import router as marketplaces_router
from app.api.v1.skills import router as skills_router
from app.api.v1.plugins import router as plugins_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.runs import router as runs_router
from app.api.v1.internal import router as internal_router
from app.api.v1.im import router as im_router
from app.api.v1.mcp import router as mcp_router
from app.api.v1.frontend import router as frontend_router
from app.api.v1.memories import router as memories_router

# Master v1 router
api_v1_router = APIRouter(prefix="/api/v1")

# Register sub-routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(providers_router)
api_v1_router.include_router(harness.router)
api_v1_router.include_router(marketplaces_router)
api_v1_router.include_router(skills_router)
api_v1_router.include_router(plugins_router)
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(runs_router)
api_v1_router.include_router(internal_router)
api_v1_router.include_router(im_router)
api_v1_router.include_router(mcp_router)
api_v1_router.include_router(frontend_router)
api_v1_router.include_router(memories_router)
