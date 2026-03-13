"""
Comment routes.

Comments on posts. Only users with a profile can comment.
"""

import asyncio

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request

from .database import create_comment, create_notification, delete_comment, get_comments, get_profile_by_id, get_push_tokens
from .schema import validate

router = APIRouter(prefix="/posts", tags=["comments"])


def _to_response(doc: dict) -> dict:
    """Shape a DB doc into the response.schema.json response."""
    return {
        "id": str(doc["_id"]),
        "postId": str(doc["postId"]),
        "authorUid": doc["authorUid"],
        "authorUsername": doc.get("authorUsername", doc["authorUid"]),
        "authorProfilePhoto": doc.get("authorProfilePhoto"),
        "body": doc["body"],
        "createdAt": doc["createdAt"],
    }


async def _notify_post_author_comment(post_id: str, commenter_uid: str, comment_body: str):
    """Send push notification to the post author about a new comment."""
    try:
        from .database import _posts
        from bson import ObjectId
        post = await _posts().find_one({"_id": ObjectId(post_id)})
        if not post or post["authorUid"] == commenter_uid:
            return
        commenter = await get_profile_by_id(commenter_uid)
        name = commenter.get("username", "Someone") if commenter else "Someone"
        preview = comment_body[:100]
        title = f"{name} commented on your post"
        # Save in-app notification
        await create_notification(
            post["authorUid"], "comment", title, preview,
            {"postId": post_id, "commenterUid": commenter_uid},
        )
        # Send push
        tokens = await get_push_tokens([post["authorUid"]])
        if not tokens:
            return
        messages = [
            {"to": t, "sound": "default", "title": title,
             "body": preview, "data": {"type": "comment", "postId": post_id}}
            for t in tokens
        ]
        async with httpx.AsyncClient() as client:
            await client.post("https://exp.host/--/api/v2/push/send", json=messages,
                              headers={"Content-Type": "application/json"})
    except Exception:
        pass


@router.post("/{post_id}/comments", status_code=201)
async def comment(post_id: str, request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("comment_create", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await create_comment(post_id, x_user_id, body)
    if doc is None:
        raise HTTPException(status_code=404, detail="Post not found or profile required")
    # Fire-and-forget push notification to post author
    asyncio.ensure_future(_notify_post_author_comment(post_id, x_user_id, body.get("body", "")))
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
