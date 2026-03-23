import asyncio
import json
from strawberry.dataloader import DataLoader

from .cache import _profile_key, set_cached, TTL, TOMBSTONE
from .resolvers.profiles import _profile_from_doc


def make_profile_loader(db, redis):
    async def batch_fn(keys: list[str]) -> list:
        cached: dict[str, dict | None] = {}
        to_fetch = []

        redis_keys = [_profile_key(uid) for uid in keys]
        redis_results = await redis.mget(redis_keys)

        for uid, doc_str in zip(keys, redis_results):
            if doc_str == "__nil__":
                cached[uid] = TOMBSTONE
            elif doc_str:
                cached[uid] = json.loads(doc_str)
            else:
                to_fetch.append(uid)

        if to_fetch:
            async for doc in db.profiles.find({"_id": {"$in": to_fetch}, "isDeleted": {"$ne": True}}):
                cached[doc["_id"]] = doc

            write_tasks = []
            for uid in to_fetch:
                if uid in cached and cached[uid] is not TOMBSTONE:
                    write_tasks.append(set_cached(redis, _profile_key(uid), cached[uid]))
                else:
                    cached[uid] = TOMBSTONE
                    write_tasks.append(redis.setex(_profile_key(uid), TTL, "__nil__"))

            if write_tasks:
                await asyncio.gather(*write_tasks)

        return [
            _profile_from_doc(cached[uid]) if cached.get(uid) is not TOMBSTONE and cached.get(uid) is not None else None
            for uid in keys
        ]

    return DataLoader(load_fn=batch_fn)
