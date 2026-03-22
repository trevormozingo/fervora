from strawberry.dataloader import DataLoader
import json

from .cache import _profile_key, set_cached
from .resolvers.profiles import _profile_from_doc


def make_profile_loader(db, redis):
    async def batch_fn(keys: list[str]) -> list:
        cached: dict[str, dict] = {}
        to_fetch = []

        redis_keys = [_profile_key(uid) for uid in keys]
        redis_results = await redis.mget(redis_keys)

        for uid, doc_str in zip(keys, redis_results):
            if doc_str:
                cached[uid] = json.loads(doc_str)
            else:
                to_fetch.append(uid)

        if to_fetch:
            async for doc in db.profiles.find({"_id": {"$in": to_fetch}, "isDeleted": False}):
                cached[doc["_id"]] = doc
                await set_cached(redis, _profile_key(doc["_id"]), doc)

        return [
            _profile_from_doc(cached[uid]) if uid in cached else None
            for uid in keys
        ]

    return DataLoader(load_fn=batch_fn)
