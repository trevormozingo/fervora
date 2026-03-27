from datetime import datetime, timezone
from typing import Optional
import strawberry
from strawberry.types import Info

from ..types.profile import Profile


# ── Helpers ───────────────────────────────────────────────────────────────────

@strawberry.type
class FollowersPage:
    users: list[Profile]
    next_cursor: Optional[str]


# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class FollowMutation:

    @strawberry.mutation
    async def follow_user(self, info: Info, user_id: str) -> bool:
        """Follow a user. Returns True if the follow was created."""
        db = info.context["db"]
        uid = info.context.get("user_id")
        if not uid:
            raise ValueError("authentication required")

        if uid == user_id:
            raise ValueError("cannot follow yourself")

        # Verify target exists
        if not await db.profiles.find_one({"_id": user_id, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("user not found")

        now = datetime.now(timezone.utc).isoformat()

        # Upsert: create or un-soft-delete
        result = await db.follows.update_one(
            {"followerUid": uid, "followingUid": user_id},
            {
                "$set": {"isDeleted": False},
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )

        return result.upserted_id is not None or result.modified_count > 0

    @strawberry.mutation
    async def unfollow_user(self, info: Info, user_id: str) -> bool:
        """Unfollow a user. Returns True if the follow was removed."""
        db = info.context["db"]
        uid = info.context.get("user_id")
        if not uid:
            raise ValueError("authentication required")

        result = await db.follows.update_one(
            {"followerUid": uid, "followingUid": user_id, "isDeleted": {"$ne": True}},
            {"$set": {"isDeleted": True}},
        )

        return result.modified_count > 0
