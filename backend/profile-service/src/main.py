"""Profile service entry point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import connect, disconnect
from .cache import connect as cache_connect, disconnect as cache_disconnect
from .routes import router
from .post_routes import router as post_router
from .comment_routes import router as comment_router
from .reaction_routes import router as reaction_router
from .event_routes import router as event_router
from .follow_routes import router as follow_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", "fervora")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    await connect(mongo_uri, db_name)
    await cache_connect(redis_url)
    yield
    await cache_disconnect()
    await disconnect()


app = FastAPI(
    title="Fervora Profile Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(post_router)
app.include_router(comment_router)
app.include_router(reaction_router)
app.include_router(event_router)
app.include_router(follow_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
