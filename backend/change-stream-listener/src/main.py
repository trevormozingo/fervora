"""
Change Stream Listener – application entry point.

A lightweight FastAPI app that:
  - Connects to MongoDB and RabbitMQ on startup
  - Starts watching change streams, publishing events to a consistent hash exchange
  - Exposes a /health endpoint for Docker healthchecks
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import listener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(application: FastAPI):
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
    db_name = os.environ.get("MONGO_DB", "fervora")
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    await listener.connect_mongo(mongo_uri, db_name)
    await listener.connect_rabbitmq(rabbitmq_url)
    await listener.start_watching()

    yield

    await listener.stop_watching()
    await listener.disconnect_rabbitmq()
    await listener.disconnect_mongo()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "change-stream-listener"}
