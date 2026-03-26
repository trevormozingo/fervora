"""
Background worker — subscribes to all five RabbitMQ queues and dispatches
messages to their respective handlers.

Delivery contract
-----------------
- prefetch_count=1 per consumer: the broker holds back the next message until
  the current one is ack'd, preventing one slow handler from starving others.
- On success  → message.ack()
- On bad payload (invalid JSON, missing required fields) → message.nack(requeue=False)
  The message is dropped; a malformed payload will never succeed on retry.
- On unexpected handler error → log + message.ack() to avoid infinite requeue loops.
  Use a dead-letter exchange in production if you need to inspect failed messages.
"""

import asyncio
import json
import logging
import os

import aio_pika
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient

from .handlers import (
    handle_profile_deleted,
    handle_post_created,
    handle_post_deleted,
    handle_follow_created,
    handle_follow_deleted,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MONGO_URI = os.environ["MONGO_URI"]
MONGO_DB = os.environ.get("MONGO_DB", "fervora")
RABBITMQ_URL = os.environ["RABBITMQ_URL"]
REDIS_URL = os.environ["REDIS_URL"]

# Map each queue name to its handler function.
QUEUE_HANDLERS = {
    "profile.deleted": handle_profile_deleted,
    "post.created":    handle_post_created,
    "post.deleted":    handle_post_deleted,
    "follow.created":  handle_follow_created,
    "follow.deleted":  handle_follow_deleted,
}


def _make_consumer(queue_name: str, handler, db, redis_client):
    """Return an aio-pika message callback bound to the given handler."""
    async def on_message(message: aio_pika.IncomingMessage) -> None:
        async with message.process(ignore_processed=True):
            try:
                data = json.loads(message.body)
            except json.JSONDecodeError as exc:
                logger.error("bad JSON on %s: %s  body=%r", queue_name, exc, message.body)
                await message.nack(requeue=False)
                return

            try:
                await handler(data, db, redis_client)
                await message.ack()
            except (KeyError, TypeError, ValueError) as exc:
                # Payload is structurally wrong — drop it.
                logger.error("unrecoverable payload error on %s: %s  data=%s", queue_name, exc, data)
                await message.nack(requeue=False)
            except Exception as exc:  # noqa: BLE001
                # Unexpected error — ack to avoid infinite requeue; investigate via logs.
                logger.exception("unexpected error on %s: %s  data=%s", queue_name, exc, data)
                await message.ack()

    return on_message


async def consume_queue(channel: aio_pika.Channel, queue_name: str, handler, db, redis_client) -> None:
    """Declare (idempotent) and start consuming a single durable queue."""
    queue = await channel.declare_queue(queue_name, durable=True)
    await queue.consume(_make_consumer(queue_name, handler, db, redis_client))
    logger.info("subscribed to queue: %s", queue_name)


async def main() -> None:
    logger.info("connecting to MongoDB ...")
    mongo = AsyncIOMotorClient(MONGO_URI)
    db = mongo[MONGO_DB]

    logger.info("connecting to Redis ...")
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    logger.info("connecting to RabbitMQ ...")
    conn = await aio_pika.connect_robust(RABBITMQ_URL)

    # Each queue gets its own channel so a slow queue doesn't stall the others.
    consumers = []
    for queue_name, handler in QUEUE_HANDLERS.items():
        channel = await conn.channel()
        await channel.set_qos(prefetch_count=1)
        consumers.append(consume_queue(channel, queue_name, handler, db, redis_client))

    logger.info("all connections established — worker is running")
    await asyncio.gather(*consumers)

    # Block forever; shutdown is handled by Docker SIGTERM → process exit.
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
