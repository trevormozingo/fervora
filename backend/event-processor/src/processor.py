"""
Event processor – consumes events from RabbitMQ queues.

Each queue has x-single-active-consumer enabled, so RabbitMQ ensures only
one consumer is active per queue across all processor instances. This lets
you scale to N containers and RabbitMQ will partition the 20 queues among them.

Within a container, each assigned queue gets its own asyncio task with
prefetch_count=1, guaranteeing strict per-user event ordering.
"""

import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from .handlers import dispatch
# Import handler modules so @register decorators execute at import time
from .handlers import profiles, posts, follows  # noqa: F401

logger = logging.getLogger(__name__)

QUEUE_PREFIX = "events-"

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_consumer_tags: list[str] = []


# ── Event handlers ────────────────────────────────────────────────────

async def _handle_event(event: dict[str, Any]) -> None:
    """Dispatch an event to its registered handler."""
    await dispatch(event)


async def _on_message(message: AbstractIncomingMessage) -> None:
    """Callback for each consumed message. Acks after successful processing."""
    async with message.process():
        try:
            event = json.loads(message.body)
            await _handle_event(event)
        except Exception:
            logger.exception("Failed to process message from %s", message.routing_key)


# ── Connection / consumer lifecycle ───────────────────────────────────

async def connect(rabbitmq_url: str) -> None:
    global _connection, _channel
    _connection = await aio_pika.connect_robust(rabbitmq_url)
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=1)
    logger.info("RabbitMQ connected")


async def start_consuming(num_queues: int) -> None:
    if _channel is None:
        raise RuntimeError("RabbitMQ not connected")

    for i in range(num_queues):
        queue_name = f"{QUEUE_PREFIX}{i}"
        queue = await _channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-single-active-consumer": True},
        )
        tag = await queue.consume(_on_message)
        _consumer_tags.append(tag)
        logger.info("Subscribed to %s", queue_name)

    logger.info("Consuming from %d queues", num_queues)


async def stop_consuming() -> None:
    _consumer_tags.clear()
    logger.info("Stopped consuming")


async def disconnect() -> None:
    global _connection, _channel
    if _connection and not _connection.is_closed:
        await _connection.close()
    _connection = None
    _channel = None
