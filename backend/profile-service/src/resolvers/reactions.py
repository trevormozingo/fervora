from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
import strawberry
from strawberry.types import Info

from ..types.reaction import Reaction, SetReactionInput
from ..cache import cached_or_fetch, set_cached, _reaction_key, TTL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reaction_from_doc(doc: dict) -> Reaction:
    return Reaction(
        id=strawberry.ID(str(doc["_id"])),
        author_uid=doc["authorUid"],
        post_id=doc["postId"],
        reaction_type=doc["reactionType"],
        created_at=doc["createdAt"],
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@strawberry.type
class ReactionQuery:

    @strawberry.field
    async def reaction(self, info: Info, id: strawberry.ID) -> Reaction:
        """Get a single reaction by ID."""
        db = info.context["db"]
        redis = info.context["redis"]
        reaction_id = str(id)
        try:
            oid = ObjectId(reaction_id)
        except InvalidId:
            raise ValueError("invalid reaction id")
        doc = await cached_or_fetch(_reaction_key(reaction_id), db.reactions, oid, redis)
        if doc is None:
            raise ValueError("reaction not found")
        return _reaction_from_doc(doc)


# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class ReactionMutation:

    @strawberry.mutation
    async def set_reaction(self, info: Info, input: SetReactionInput) -> Reaction:
        """Set (or replace) the current user's reaction on a post."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        now = datetime.now(timezone.utc).isoformat()
        doc = await db.reactions.find_one_and_update(
            {"postId": str(input.post_id), "authorUid": user_id},
            {
                "$set": {"reactionType": input.reaction_type, "createdAt": now, "isDeleted": False},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc["_id"] = str(doc["_id"])
        await set_cached(redis, _reaction_key(doc["_id"]), doc)
        return _reaction_from_doc(doc)

    @strawberry.mutation
    async def delete_reaction(self, info: Info, post_id: strawberry.ID) -> bool:
        """Remove the current user's reaction from a post."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        doc = await db.reactions.find_one_and_update(
            {"postId": str(post_id), "authorUid": user_id, "isDeleted": {"$ne": True}},
            {"$set": {"isDeleted": True}},
        )
        if doc:
            await redis.setex(_reaction_key(str(doc["_id"])), TTL, "__nil__")
            return True
        return False
