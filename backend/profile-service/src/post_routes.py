"""
Post routes.

Response shape matches post/base.schema.json:
  { id, authorUid, title, body, media, workout, bodyMetrics, createdAt }

Only users with an existing profile can create or delete posts.
"""

from fastapi import APIRouter, Header, HTTPException, Query, Request

from .database import create_post, delete_post, get_user_posts
from .schema import validate

router = APIRouter(prefix="/posts", tags=["posts"])


def _to_response(doc: dict) -> dict:
    """Shape a DB doc into the base.schema.json response."""
    resp = {
        "id": str(doc["_id"]),
        "authorUid": doc["authorUid"],
        "title": doc.get("title"),
        "body": doc.get("body"),
        "media": doc.get("media"),
        "workout": doc.get("workout"),
        "bodyMetrics": doc.get("bodyMetrics"),
        "createdAt": doc["createdAt"],
    }
    # Enrichment fields (present on list queries)
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
async def list_my_posts(
    x_user_id: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    """Return the caller's own posts, newest first."""
    docs = await get_user_posts(x_user_id, limit=limit, cursor=cursor)
    items = [_to_response(d) for d in docs]
    next_cursor = items[-1]["createdAt"] if items else None
    return {"items": items, "count": len(items), "cursor": next_cursor}


@router.post("", status_code=201)
async def create(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("post_create", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await create_post(x_user_id, body)
    if doc is None:
        raise HTTPException(status_code=403, detail="Profile required to create posts")
    return _to_response(doc)


@router.delete("/{post_id}", status_code=204)
async def delete(post_id: str, x_user_id: str = Header(...)):
    deleted = await delete_post(post_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found or not owned by you")
