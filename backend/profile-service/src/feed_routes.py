"""
Feed routes.

Returns posts from users the caller follows, newest first.
Cursor-based pagination via ?cursor=<createdAt>&limit=<n>.
"""

from fastapi import APIRouter, Header, Query

from .database import get_feed

router = APIRouter(prefix="/feed", tags=["feed"])


def _to_post(doc: dict) -> dict:
    """Shape a DB post doc into the response.schema.json response."""
    resp = {
        "id": str(doc["_id"]),
        "authorUid": doc["authorUid"],
        "authorUsername": doc.get("authorUsername"),
        "authorProfilePhoto": doc.get("authorProfilePhoto"),
        "title": doc.get("title"),
        "body": doc.get("body"),
        "media": doc.get("media"),
        "workout": doc.get("workout"),
        "bodyMetrics": doc.get("bodyMetrics"),
        "createdAt": doc["createdAt"],
    }
    if "feedCreatedAt" in doc:
        resp["feedCreatedAt"] = doc["feedCreatedAt"]
    if "reactionSummary" in doc:
        resp["reactionSummary"] = doc["reactionSummary"]
    if "recentComments" in doc:
        resp["recentComments"] = doc["recentComments"]
    if "commentCount" in doc:
        resp["commentCount"] = doc["commentCount"]
    if "myReaction" in doc:
        resp["myReaction"] = doc["myReaction"]
    return resp


@router.get("")
async def feed(
    x_user_id: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    posts = await get_feed(x_user_id, limit=limit, cursor=cursor)
    items = [_to_post(p) for p in posts]
    next_cursor = items[-1]["feedCreatedAt"] if items else None
    return {"items": items, "count": len(items), "cursor": next_cursor}
