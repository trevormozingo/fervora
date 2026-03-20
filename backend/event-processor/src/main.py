"""
Event Processor – application entry point.

A lightweight FastAPI app that:
  - Connects to RabbitMQ on startup
  - Subscribes to all event queues (x-single-active-consumer ensures
    only one consumer per queue across all instances)
  - Exposes a /health endpoint for Docker healthchecks
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import processor
from .database import connect as db_connect, disconnect as db_disconnect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(application: FastAPI):
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    num_queues = int(os.environ.get("NUM_QUEUES", "20"))
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    mongo_db = os.environ.get("MONGO_DB", "fervora")

    await db_connect(mongo_uri, mongo_db)
    await processor.connect(rabbitmq_url)
    await processor.start_consuming(num_queues)

    yield

    await processor.stop_consuming()
    await processor.disconnect()
    await db_disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "event-processor"}
