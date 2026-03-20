"""
Feed routes.

Returns posts from users the caller follows, newest first.
Cursor-based pagination via ?cursor=<createdAt>&limit=<n>.
"""

from fastapi import APIRouter, Header, Query

from .database import get_db
from .cache import (
    get_feed_page,
    get_post,
    get_profile,
    get_post_counts,
    get_recent_comments,
    get_my_reaction,
    list_following,
)

router = APIRouter(prefix="/feed", tags=["feed"])


async def _to_post(doc: dict, feed_created_at: str, viewer_uid: str) -> dict:
    """Shape a cached post doc into an enriched feed response."""
    db = get_db()
    post_id = doc["_id"]

    # Author info
    author_profile = await get_profile(doc["authorUid"], db)
    author_username = author_profile["username"] if author_profile else None
    author_photo = author_profile.get("profilePhoto") if author_profile else None

    # Aggregations
    counts = await get_post_counts(post_id, db)
    recent = await get_recent_comments(post_id, db)
    my_reaction = await get_my_reaction(post_id, viewer_uid, db)

    resp: dict = {
        "id": post_id,
        "authorUid": doc["authorUid"],
        "authorUsername": author_username,
        "authorProfilePhoto": author_photo,
        "title": doc.get("title"),
        "body": doc.get("body"),
        "media": doc.get("media"),
        "workout": doc.get("workout"),
        "bodyMetrics": doc.get("bodyMetrics"),
        "createdAt": doc["createdAt"],
        "feedCreatedAt": feed_created_at,
        "reactionSummary": counts.get("reactionSummary", {}),
        "commentCount": counts.get("commentCount", 0),
        "recentComments": recent,
        "myReaction": my_reaction,
    }
    return resp


@router.get("")
async def feed(
    x_user_id: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    db = get_db()
    following_uids = await list_following(x_user_id, db)
    feed_entries = await get_feed_page(x_user_id, db, following_uids, limit=limit, cursor=cursor)

    if not feed_entries:
        return {"items": [], "count": 0, "cursor": None}

    feed_ts_by_post = {e["postId"]: e["createdAt"] for e in feed_entries}

    # Fetch each post through the cache
    items = []
    for entry in feed_entries:
        post = await get_post(entry["postId"], db)
        if post:
            items.append(await _to_post(post, feed_ts_by_post[post["_id"]], x_user_id))

    next_cursor = items[-1]["feedCreatedAt"] if items else None
    return {"items": items, "count": len(items), "cursor": next_cursor}
