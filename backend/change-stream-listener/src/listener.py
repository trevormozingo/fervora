"""
MongoDB change-stream → RabbitMQ consistent-hash exchange.

Watches change streams on configured collections and publishes events to
a RabbitMQ consistent hash exchange. Routing key = entity owner ID so
all events for the same user land on the same queue (ordering guarantee).

Resume tokens are persisted in a MongoDB collection so the listener can
pick up where it left off after a restart.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aio_pika
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "events.consistent"
EXCHANGE_TYPE = "x-consistent-hash"
RESUME_TOKEN_COLLECTION = "change_stream_resume_tokens"

# Collections to watch and how to extract the routing key (owner ID).
# Value is the field name that holds the owner UID.
# "_id" means the document key itself is the owner (e.g. profiles).
WATCHED_COLLECTIONS: dict[str, str] = {
    "profiles": "_id",        # profile doc _id IS the user uid
    "posts": "authorUid",     # post owner is authorUid field
    "follows": "followerId",  # route follow events by acting user
}

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
_rmq_connection: aio_pika.abc.AbstractRobustConnection | None = None
_rmq_channel: aio_pika.abc.AbstractChannel | None = None
_rmq_exchange: aio_pika.abc.AbstractExchange | None = None
_tasks: list[asyncio.Task] = []
_running = False


# ── Connection management ─────────────────────────────────────────────

async def connect_rabbitmq(rabbitmq_url: str) -> None:
    global _rmq_connection, _rmq_channel, _rmq_exchange
    _rmq_connection = await aio_pika.connect_robust(rabbitmq_url)
    _rmq_channel = await _rmq_connection.channel()
    _rmq_exchange = await _rmq_channel.declare_exchange(
        EXCHANGE_NAME,
        type=EXCHANGE_TYPE,
        durable=True,
    )
    logger.info("RabbitMQ connected, exchange '%s' declared", EXCHANGE_NAME)


async def disconnect_rabbitmq() -> None:
    global _rmq_connection, _rmq_channel, _rmq_exchange
    if _rmq_connection and not _rmq_connection.is_closed:
        await _rmq_connection.close()
    _rmq_connection = None
    _rmq_channel = None
    _rmq_exchange = None


async def connect_mongo(mongo_uri: str, db_name: str) -> None:
    global _client, _db
    _client = AsyncIOMotorClient(mongo_uri)
    _db = _client[db_name]


async def disconnect_mongo() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


# ── Resume token persistence ─────────────────────────────────────────

async def _load_resume_token(collection_name: str) -> dict | None:
    if _db is None:
        raise RuntimeError("Database not connected")
    doc = await _db[RESUME_TOKEN_COLLECTION].find_one({"_id": collection_name})
    if doc and "token" in doc:
        return doc["token"]
    return None


async def _save_resume_token(collection_name: str, token: dict) -> None:
    if _db is None:
        raise RuntimeError("Database not connected")
    await _db[RESUME_TOKEN_COLLECTION].update_one(
        {"_id": collection_name},
        {"$set": {"token": token, "updatedAt": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


# ── Event publishing ─────────────────────────────────────────────────

async def _publish_event(routing_key: str, event: dict[str, Any]) -> None:
    if _rmq_exchange is None:
        raise RuntimeError("RabbitMQ not connected")
    await _rmq_exchange.publish(
        aio_pika.Message(
            body=json.dumps(event, default=str).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=routing_key,
    )


def _build_event(change: dict[str, Any], collection_name: str) -> dict[str, Any]:
    op = change["operationType"]
    doc_key = change["documentKey"]["_id"]
    event: dict[str, Any] = {
        "collection": collection_name,
        "operationType": op,
        "documentKey": doc_key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if op in ("insert", "replace") and "fullDocument" in change:
        event["fullDocument"] = change["fullDocument"]
    elif op == "update" and "updateDescription" in change:
        event["updatedFields"] = change["updateDescription"].get("updatedFields", {})
        event["removedFields"] = change["updateDescription"].get("removedFields", [])
        # Include full doc for soft-delete detection
        if "fullDocument" in change:
            event["fullDocument"] = change["fullDocument"]
    return event


def _extract_routing_key(change: dict[str, Any], collection_name: str) -> str:
    key_field = WATCHED_COLLECTIONS[collection_name]
    if key_field == "_id":
        return str(change["documentKey"]["_id"])
    # For other collections the owner ID is in the full document
    if "fullDocument" in change and key_field in change["fullDocument"]:
        return str(change["fullDocument"][key_field])
    return str(change["documentKey"]["_id"])


# ── Change stream watcher ────────────────────────────────────────────

async def _watch_collection(collection_name: str) -> None:
    if _db is None:
        raise RuntimeError("Database not connected")

    token = await _load_resume_token(collection_name)
    kwargs: dict[str, Any] = {"full_document": "updateLookup"}
    if token:
        kwargs["resume_after"] = token
        logger.info("Resuming %s from token %s", collection_name, token)

    collection = _db[collection_name]
    async with collection.watch(**kwargs) as stream:
        logger.info("Watching %s for changes", collection_name)
        async for change in stream:
            if not _running:
                break
            routing_key = _extract_routing_key(change, collection_name)
            event = _build_event(change, collection_name)
            await _publish_event(routing_key, event)
            await _save_resume_token(collection_name, stream.resume_token)
            logger.debug(
                "Published %s event for %s (key=%s)",
                event["operationType"], collection_name, routing_key,
            )


# ── Lifecycle ─────────────────────────────────────────────────────────

async def start_watching() -> None:
    global _running
    _running = True
    for collection_name in WATCHED_COLLECTIONS:
        task = asyncio.create_task(_watch_collection(collection_name))
        _tasks.append(task)
    logger.info("Change stream listener started for %s", list(WATCHED_COLLECTIONS.keys()))


async def stop_watching() -> None:
    global _running
    _running = False
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    logger.info("Change stream listener stopped")
