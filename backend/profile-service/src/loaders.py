from __future__ import annotations
import asyncio
import json
from bson import ObjectId
from bson.errors import InvalidId
from strawberry.dataloader import DataLoader

from .cache import _profile_key, _post_key, set_cached, TTL, TOMBSTONE
from .resolvers.profiles import _profile_from_doc
from .resolvers.posts import _post_from_doc
from .types.reaction import ReactionSummary


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


def make_post_loader(db, redis):
    async def batch_fn(keys: list[str]) -> list:
        cached: dict[str, dict | None] = {}
        to_fetch = []

        redis_keys = [_post_key(pid) for pid in keys]
        redis_results = await redis.mget(redis_keys)

        for pid, doc_str in zip(keys, redis_results):
            if doc_str == "__nil__":
                cached[pid] = TOMBSTONE
            elif doc_str:
                cached[pid] = json.loads(doc_str)
            else:
                to_fetch.append(pid)

        if to_fetch:
            oids = []
            valid_pids = []
            for pid in to_fetch:
                try:
                    oids.append(ObjectId(pid))
                    valid_pids.append(pid)
                except InvalidId:
                    cached[pid] = TOMBSTONE

            if oids:
                async for doc in db.posts.find({"_id": {"$in": oids}, "isDeleted": {"$ne": True}}):
                    cached[str(doc["_id"])] = doc

            write_tasks = []
            for pid in valid_pids:
                if pid in cached and cached[pid] is not TOMBSTONE:
                    write_tasks.append(set_cached(redis, _post_key(pid), cached[pid]))
                else:
                    cached[pid] = TOMBSTONE
                    write_tasks.append(redis.setex(_post_key(pid), TTL, "__nil__"))

            if write_tasks:
                await asyncio.gather(*write_tasks)

        return [
            _post_from_doc(cached[pid]) if cached.get(pid) is not TOMBSTONE and cached.get(pid) is not None else None
            for pid in keys
        ]

    return DataLoader(load_fn=batch_fn)


def make_reaction_summary_loader(db):
    async def batch_fn(post_ids: list[str]) -> list[list[ReactionSummary]]:
        pipeline = [
            {"$match": {"postId": {"$in": post_ids}, "isDeleted": {"$ne": True}}},
            {"$group": {"_id": {"postId": "$postId", "reactionType": "$reactionType"}, "count": {"$sum": 1}}},
        ]
        docs = await db.reactions.aggregate(pipeline).to_list(length=None)

        by_post: dict[str, list[ReactionSummary]] = {pid: [] for pid in post_ids}
        for d in docs:
            pid = d["_id"]["postId"]
            if pid in by_post:
                by_post[pid].append(ReactionSummary(reaction_type=d["_id"]["reactionType"], count=d["count"]))

        return [by_post[pid] for pid in post_ids]

    return DataLoader(load_fn=batch_fn)


def make_viewer_reaction_loader(db, user_id: str | None):
    async def batch_fn(post_ids: list[str]) -> list[str | None]:
        if not user_id:
            return [None] * len(post_ids)

        docs = await db.reactions.find(
            {"postId": {"$in": post_ids}, "authorUid": user_id, "isDeleted": {"$ne": True}},
            {"postId": 1, "reactionType": 1},
        ).to_list(length=None)

        by_post: dict[str, str] = {d["postId"]: d["reactionType"] for d in docs}
        return [by_post.get(pid) for pid in post_ids]

    return DataLoader(load_fn=batch_fn)


def make_rsvp_summary_loader(db):
    from .types.event import RsvpSummary

    async def batch_fn(event_ids: list[str]) -> list[list[RsvpSummary]]:
        pipeline = [
            {"$match": {"eventId": {"$in": event_ids}, "isDeleted": {"$ne": True}}},
            {"$group": {"_id": {"eventId": "$eventId", "status": "$status"}, "count": {"$sum": 1}}},
        ]
        docs = await db.rsvps.aggregate(pipeline).to_list(length=None)

        by_event: dict[str, list[RsvpSummary]] = {eid: [] for eid in event_ids}
        for d in docs:
            eid = d["_id"]["eventId"]
            if eid in by_event:
                by_event[eid].append(RsvpSummary(status=d["_id"]["status"], count=d["count"]))

        return [by_event[eid] for eid in event_ids]

    return DataLoader(load_fn=batch_fn)


def make_viewer_rsvp_loader(db, user_id: str | None):
    async def batch_fn(event_ids: list[str]) -> list[str | None]:
        if not user_id:
            return [None] * len(event_ids)

        docs = await db.rsvps.find(
            {"eventId": {"$in": event_ids}, "userId": user_id, "isDeleted": {"$ne": True}},
            {"eventId": 1, "status": 1},
        ).to_list(length=None)

        by_event: dict[str, str] = {d["eventId"]: d["status"] for d in docs}
        return [by_event.get(eid) for eid in event_ids]

    return DataLoader(load_fn=batch_fn)
