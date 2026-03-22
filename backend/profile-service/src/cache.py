import json
from redis.asyncio import Redis

TTL = 3600  # 1 hour


def _profile_key(user_id: str) -> str:
    return f"profile:{user_id}"


def _post_key(post_id: str) -> str:
    return f"post:{post_id}"


async def get_cached(redis: Redis, key: str) -> dict | None:
    raw = await redis.get(key)
    return json.loads(raw) if raw else None


async def set_cached(redis: Redis, key: str, doc: dict) -> None:
    await redis.setex(key, TTL, json.dumps(doc, default=str))


async def invalidate(redis: Redis, key: str) -> None:
    await redis.delete(key)
