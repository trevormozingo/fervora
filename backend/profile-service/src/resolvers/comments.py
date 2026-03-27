from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
import strawberry
from strawberry.types import Info

from ..types.comment import Comment, CreateCommentInput
from ..cache import cached_or_fetch, set_cached, _comment_key, TTL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _comment_from_doc(doc: dict) -> Comment:
    return Comment(
        id=strawberry.ID(str(doc["_id"])),
        author_uid=doc["authorUid"],
        post_id=doc["postId"],
        body=doc["body"],
        created_at=doc["createdAt"],
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@strawberry.type
class CommentQuery:

    @strawberry.field
    async def comment(self, info: Info, id: strawberry.ID) -> Comment:
        """Get a single comment by ID."""
        db = info.context["db"]
        redis = info.context["redis"]
        comment_id = str(id)
        try:
            oid = ObjectId(comment_id)
        except InvalidId:
            raise ValueError("invalid comment id")
        doc = await cached_or_fetch(_comment_key(comment_id), db.comments, oid, redis)
        if doc is None:
            raise ValueError("comment not found")
        return _comment_from_doc(doc)


# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class CommentMutation:

    @strawberry.mutation
    async def create_comment(self, info: Info, input: CreateCommentInput) -> Comment:
        """Create a comment on a post."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        try:
            post_oid = ObjectId(str(input.post_id))
        except InvalidId:
            raise ValueError("invalid post id")

        if not await db.posts.find_one({"_id": post_oid, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("cannot comment: the post does not exist or was deleted")

        if not await db.profiles.find_one({"_id": user_id, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("cannot comment: your profile does not exist or was deleted")

        doc = {
            "authorUid": user_id,
            "postId": str(input.post_id),
            "body": input.body,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "isDeleted": False,
        }

        result = await db.comments.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        await set_cached(redis, _comment_key(doc["_id"]), doc)

        return _comment_from_doc(doc)

    @strawberry.mutation
    async def delete_comment(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a comment (only the author can delete their own comment)."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        try:
            oid = ObjectId(str(id))
        except InvalidId:
            raise ValueError("invalid comment id")

        result = await db.comments.update_one(
            {"_id": oid, "authorUid": user_id},
            {"$set": {"isDeleted": True}},
        )

        if result.modified_count > 0:
            await redis.setex(_comment_key(str(id)), TTL, "__nil__")
            return True

        return False
