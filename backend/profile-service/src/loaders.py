from strawberry.dataloader import DataLoader

from .cache import get_cached, _profile_key
from .resolvers.profiles import _profile_from_doc


def make_profile_loader(db, redis):
    async def batch_fn(keys: list[str]) -> list:
        cached: dict[str, dict] = {}
        to_fetch = []

        for uid in keys:
            doc = await get_cached(redis, _profile_key(uid))
            if doc:
                cached[uid] = doc
            else:
                to_fetch.append(uid)

        if to_fetch:
            async for doc in db.profiles.find({"_id": {"$in": to_fetch}, "isDeleted": False}):
                cached[doc["_id"]] = doc

        return [
            _profile_from_doc(cached[uid]) if uid in cached else None
            for uid in keys
        ]

    return DataLoader(load_fn=batch_fn)
