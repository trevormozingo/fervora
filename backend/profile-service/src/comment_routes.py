"""
Comment routes.

Comments on posts. Only users with a profile can comment.
"""

from fastapi import APIRouter, Header, HTTPException, Query, Request

from .database import create_comment, delete_comment, get_comments
from .schema import validate

router = APIRouter(prefix="/posts", tags=["comments"])


def _to_response(doc: dict) -> dict:
    """Shape a DB doc into the base.schema.json response."""
    return {
        "id": str(doc["_id"]),
        "postId": str(doc["postId"]),
        "authorUid": doc["authorUid"],
        "authorUsername": doc.get("authorUsername", doc["authorUid"]),
        "body": doc["body"],
        "createdAt": doc["createdAt"],
    }


@router.post("/{post_id}/comments", status_code=201)
async def comment(post_id: str, request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("comment_create", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await create_comment(post_id, x_user_id, body)
    if doc is None:
        raise HTTPException(status_code=404, detail="Post not found or profile required")
    return _to_response(doc)


@router.delete("/{post_id}/comments/{comment_id}", status_code=204)
async def remove(post_id: str, comment_id: str, x_user_id: str = Header(...)):
    deleted = await delete_comment(comment_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found or not owned by you")


@router.get("/{post_id}/comments")
async def list_comments(
    post_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    comments = await get_comments(post_id, limit=limit, cursor=cursor)
    items = [_to_response(c) for c in comments]
    next_cursor = items[-1]["id"] if items else None
    return {"items": items, "count": len(items), "cursor": next_cursor}
