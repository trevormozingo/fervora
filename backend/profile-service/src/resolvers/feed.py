from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
import strawberry
from strawberry.types import Info

from ..types.post import Post


@strawberry.type
class FeedPage:
    posts: list[Post]
    next_cursor: Optional[str]


@strawberry.type
class FeedQuery:

    @strawberry.field
    async def feed(
        self,
        info: Info,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> FeedPage:
        """Paginated feed for the authenticated user, newest first."""
        db = info.context["db"]
        user_id = info.context["user_id"]
        post_loader = info.context["post_loader"]

        if not user_id:
            raise ValueError("authentication required")

        query: dict = {"followerUid": user_id, "isDeleted": {"$ne": True}}
        if cursor:
            try:
                query["_id"] = {"$lt": ObjectId(cursor)}
            except InvalidId:
                raise ValueError("invalid cursor")

        docs = (
            await db.feed.find(query, {"postId": 1, "_id": 1})
            .sort("_id", -1)
            .limit(limit)
            .to_list(length=limit)
        )

        if not docs:
            return FeedPage(posts=[], next_cursor=None)

        post_ids = [doc["postId"] for doc in docs]
        hydrated = await post_loader.load_many(post_ids)
        valid_posts = [p for p in hydrated if p is not None]

        next_cursor = str(docs[-1]["_id"]) if len(docs) == limit else None

        return FeedPage(posts=valid_posts, next_cursor=next_cursor)
