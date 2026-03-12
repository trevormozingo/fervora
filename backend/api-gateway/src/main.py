"""
API Gateway — main entrypoint.

Starts the FastAPI application with:
  - Auth middleware (Firebase or mock)
  - Reverse proxy routes to backend services
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .proxy import close_client
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the shared HTTP client."""
    yield
    await close_client()


app = FastAPI(title="Fervora API Gateway", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}
