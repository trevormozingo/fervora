"""
Post routes.

Response shape matches post/response.schema.json:
  { id, authorUid, authorUsername, title, body, media, workout, bodyMetrics,
    createdAt, reactionSummary, recentComments, commentCount, myReaction }

Only users with an existing profile can create or delete posts.
"""

from fastapi import APIRouter, Header, HTTPException, Query, Request, UploadFile, File
from typing import List
from pymongo.errors import DuplicateKeyError

from .database import create_post, delete_post, get_user_posts, get_post_by_id, get_user_tracking, get_user_post_stats, check_synced_healthkit_ids
from .schema import validate
from .storage import upload_post_media, generate_post_id, delete_post_media

router = APIRouter(prefix="/posts", tags=["posts"])


def _to_response(doc: dict) -> dict:
    """Shape a DB doc into the response.schema.json response."""
    resp = {
        "id": str(doc["_id"]),
        "authorUid": doc["authorUid"],
        "authorProfilePhoto": doc.get("authorProfilePhoto"),
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


@router.get("/stats")
async def my_post_stats(x_user_id: str = Header(...)):
    """Return aggregate post, reaction, and comment counts for the caller."""
    return await get_user_post_stats(x_user_id)


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


@router.get("/user/{uid}")
async def list_user_posts(
    uid: str,
    x_user_id: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    """Return a user's posts (public). Viewer UID used for myReaction."""
    docs = await get_user_posts(uid, limit=limit, cursor=cursor, viewer_uid=x_user_id)
    items = [_to_response(d) for d in docs]
    next_cursor = items[-1]["createdAt"] if items else None
    return {"items": items, "count": len(items), "cursor": next_cursor}


@router.get("/user/{uid}/tracking")
async def user_tracking(
    uid: str,
    x_user_id: str = Header(...),
    start: str | None = None,
    end: str | None = None,
):
    """Return workout and body-metrics history for a user within a date range."""
    return await get_user_tracking(uid, start=start, end=end)


@router.get("/user/{uid}/stats")
async def user_post_stats(uid: str, x_user_id: str = Header(...)):
    """Return aggregate post, reaction, and comment counts for a user."""
    return await get_user_post_stats(uid)


@router.post("/check-synced")
async def check_synced(request: Request, x_user_id: str = Header(...)):
    """Return which HealthKit workout UUIDs are already synced as posts."""
    body = await request.json()
    ids = body.get("healthKitIds", [])
    if not isinstance(ids, list) or len(ids) > 100:
        raise HTTPException(status_code=422, detail="healthKitIds must be a list of up to 100 strings")
    synced = await check_synced_healthkit_ids(x_user_id, ids)
    return {"syncedIds": synced}


@router.get("/{post_id}")
async def get_single_post(post_id: str, x_user_id: str = Header(...)):
    """Return a single post by ID, enriched with reactions and comments."""
    doc = await get_post_by_id(post_id, viewer_uid=x_user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return _to_response(doc)


@router.post("", status_code=201)
async def create(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("post_create", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    try:
        doc = await create_post(x_user_id, body)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Workout already synced")
    if doc is None:
        raise HTTPException(status_code=403, detail="Profile required to create posts")
    return _to_response(doc)


@router.delete("/{post_id}", status_code=204)
async def delete(post_id: str, x_user_id: str = Header(...)):
    doc = await delete_post(post_id, x_user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found or not owned by you")
    # Clean up media files from Storage
    storage_post_id = doc.get("storagePostId")
    if storage_post_id:
        try:
            delete_post_media(x_user_id, storage_post_id)
        except Exception:
            pass  # best-effort


@router.post("/media", status_code=201)
async def upload_media(
    files: List[UploadFile] = File(...),
    x_user_id: str = Header(...),
):
    """
    Upload post media files before creating the post.

    Returns { postId, media: [{ url, mimeType }, ...] }.
    The postId should be included as storagePostId when creating the post
    so the backend can clean up storage on post deletion.
    """
    if len(files) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 files allowed")

    post_id = generate_post_id()
    results = []

    for index, file in enumerate(files):
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:  # 20 MB per file
            raise HTTPException(
                status_code=422,
                detail=f"File {file.filename} too large (max 20 MB)",
            )

        content_type = file.content_type or "application/octet-stream"
        item = upload_post_media(
            x_user_id, post_id, index, data, content_type, file.filename or f"media_{index}"
        )
        results.append(item)

    return {"postId": post_id, "media": results}
