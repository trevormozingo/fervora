"""
Profile service entry point.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import connect, disconnect
from .routes import router
from .storage import init_storage
from .post_routes import router as post_router
from .follow_routes import router as follow_router
from .feed_routes import router as feed_router
from .reaction_routes import router as reaction_router
from .comment_routes import router as comment_router
from .event_routes import router as event_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", "fervora")
    await connect(mongo_uri, db_name)
    init_storage()
    yield
    await disconnect()


app = FastAPI(
    title="Fervora Profile Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(post_router)
app.include_router(follow_router)
app.include_router(feed_router)
app.include_router(reaction_router)
app.include_router(comment_router)
app.include_router(event_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
