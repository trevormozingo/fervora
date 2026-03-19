"""API Gateway — reverse proxy to backend services."""

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from .proxy import proxy_router

PROFILE_SERVICE_URL = os.getenv("PROFILE_SERVICE_URL", "http://profile-service:8000")


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    await application.state.http_client.aclose()


app = FastAPI(title="Fervora API Gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(proxy_router)
