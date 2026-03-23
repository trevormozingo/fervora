import json
from redis.asyncio import Redis

TTL = 3600  # 1 hour
TOMBSTONE = object()  # sentinel for deleted/nil cache entries


def _profile_key(user_id: str) -> str:
    return f"profile:{user_id}"


def _post_key(post_id: str) -> str:
    return f"post:{post_id}"


def _comment_key(comment_id: str) -> str:
    return f"comment:{comment_id}"


def _reaction_key(reaction_id: str) -> str:
    return f"reaction:{reaction_id}"


async def get_cached(redis: Redis, key: str):
    raw = await redis.get(key)
    if raw is None:
        return None
    if raw == "__nil__":
        return TOMBSTONE
    return json.loads(raw)


async def set_cached(redis: Redis, key: str, doc: dict) -> None:
    await redis.setex(key, TTL, json.dumps(doc, default=str))


async def cached_or_fetch(key: str, collection, doc_id, redis) -> dict | None:
    """Check cache first; on miss query MongoDB (excluding isDeleted), cache or write tombstone."""
    doc = await get_cached(redis, key)
    if doc is TOMBSTONE:
        return None
    if doc:
        return doc
    doc = await collection.find_one({"_id": doc_id, "isDeleted": {"$ne": True}})
    if doc is not None:
        doc["_id"] = str(doc["_id"])
        await set_cached(redis, key, doc)
        return doc
    await redis.setex(key, TTL, "__nil__")
    return None