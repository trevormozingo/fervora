"""
Profile routes.

Response shapes match public.schema.json and private.schema.json exactly:
  { id, username, displayName, bio, birthday }
"""

from fastapi import APIRouter, Header, HTTPException, Query, Request, UploadFile, File

from .database import (
    add_push_token,
    count_user_posts,
    create_profile,
    delete_profile,
    get_nearby_profiles,
    get_notifications,
    get_profile_by_id,
    get_profile_by_username,
    get_profiles_by_ids,
    get_push_tokens,
    get_unread_notification_count,
    is_following,
    mark_notifications_read,
    remove_push_token,
    search_profiles,
    update_profile,
)
from .schema import validate
from .storage import upload_profile_photo, delete_user_media

router = APIRouter(prefix="/profile", tags=["profile"])


def _to_public(doc: dict) -> dict:
    """Shape a DB doc into the public.schema.json response."""
    resp = {
        "id": doc["_id"],
        "username": doc["username"],
        "displayName": doc["displayName"],
        "bio": doc.get("bio"),
        "birthday": doc.get("birthday"),
        "profilePhoto": doc.get("profilePhoto"),
        "interests": doc.get("interests"),
        "fitnessLevel": doc.get("fitnessLevel"),
        "followersCount": doc.get("followersCount", 0),
        "followingCount": doc.get("followingCount", 0),
    }
    if doc.get("location"):
        resp["location"] = doc["location"]
    return resp


def _to_private(doc: dict) -> dict:
    """Shape a DB doc into the private.schema.json response."""
    resp = {
        "id": doc["_id"],
        "username": doc["username"],
        "displayName": doc["displayName"],
        "bio": doc.get("bio"),
        "birthday": doc.get("birthday"),
        "profilePhoto": doc.get("profilePhoto"),
        "interests": doc.get("interests"),
        "fitnessLevel": doc.get("fitnessLevel"),
        "followersCount": doc.get("followersCount", 0),
        "followingCount": doc.get("followingCount", 0),
    }
    if doc.get("location"):
        resp["location"] = doc["location"]
    return resp


@router.post("", status_code=201)
async def create(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("create", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    try:
        doc = await create_profile(x_user_id, body)
    except Exception:
        raise HTTPException(status_code=409, detail="Username already taken")
    return _to_private(doc)


@router.get("")
async def get_own(x_user_id: str = Header(...)):
    doc = await get_profile_by_id(x_user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    resp = _to_private(doc)
    resp["postCount"] = await count_user_posts(x_user_id)
    return resp


@router.get("/nearby")
async def nearby(
    x_user_id: str = Header(...),
    lng: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    radius: float = Query(default=50, ge=1, le=500, description="Radius in km"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Find profiles near a coordinate. Excludes the requesting user."""
    docs = await get_nearby_profiles(lng, lat, radius_km=radius, limit=limit, exclude_uid=x_user_id)
    return {"items": [_to_public(d) for d in docs], "count": len(docs)}


@router.put("/push-token")
async def register_push_token(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    token = body.get("token")
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=422, detail="Missing 'token' string")
    await add_push_token(x_user_id, token)
    return {"ok": True}


@router.delete("/push-token")
async def unregister_push_token(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    token = body.get("token")
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=422, detail="Missing 'token' string")
    await remove_push_token(x_user_id, token)
    return {"ok": True}


@router.post("/send-push")
async def send_push(request: Request, x_user_id: str = Header(...)):
    """Send push notifications to a list of recipient UIDs."""
    import httpx
    body = await request.json()
    recipient_uids: list[str] = body.get("recipientUids", [])
    title: str = body.get("title", "")
    message_body: str = body.get("body", "")
    data: dict = body.get("data", {})
    if not recipient_uids:
        return {"sent": 0}
    tokens = await get_push_tokens(recipient_uids)
    if not tokens:
        return {"sent": 0}
    # Build Expo push messages
    messages = [
        {
            "to": t,
            "sound": "default",
            "title": title,
            "body": message_body,
            "data": data,
        }
        for t in tokens
    ]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://exp.host/--/api/v2/push/send",
            json=messages,
            headers={"Content-Type": "application/json"},
        )
    return {"sent": len(messages), "status": resp.status_code}


@router.post("/batch")
async def batch_profiles(request: Request):
    body = await request.json()
    uids = body.get("uids", [])
    if not isinstance(uids, list) or len(uids) == 0 or len(uids) > 100:
        raise HTTPException(status_code=422, detail="Provide 1-100 uids")
    docs = await get_profiles_by_ids(uids)
    return [_to_public(doc) for doc in docs]


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    docs = await search_profiles(q, limit)
    return [_to_public(doc) for doc in docs]


@router.get("/notifications")
async def list_notifications(
    x_user_id: str = Header(...),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    """Get the current user's notifications."""
    docs = await get_notifications(x_user_id, limit=limit, cursor=cursor)
    items = [
        {
            "id": str(d["_id"]),
            "type": d["type"],
            "title": d["title"],
            "body": d["body"],
            "data": d.get("data", {}),
            "read": d["read"],
            "createdAt": d["createdAt"],
        }
        for d in docs
    ]
    return {"items": items, "count": len(items), "cursor": items[-1]["id"] if items else None}


@router.get("/notifications/unread-count")
async def unread_count(x_user_id: str = Header(...)):
    count = await get_unread_notification_count(x_user_id)
    return {"count": count}


@router.post("/notifications/mark-read")
async def mark_read(x_user_id: str = Header(...)):
    updated = await mark_notifications_read(x_user_id)
    return {"updated": updated}


@router.get("/uid/{uid}")
async def get_by_uid(uid: str, x_user_id: str | None = Header(default=None)):
    doc = await get_profile_by_id(uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    resp = _to_public(doc)
    resp["postCount"] = await count_user_posts(uid)
    if x_user_id and x_user_id != uid:
        resp["isFollowing"] = await is_following(x_user_id, uid)
    return resp


@router.get("/{username}")
async def get_public(username: str, x_user_id: str | None = Header(default=None)):
    doc = await get_profile_by_username(username)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    resp = _to_public(doc)
    target_uid = doc["_id"]
    resp["postCount"] = await count_user_posts(target_uid)
    if x_user_id and x_user_id != target_uid:
        resp["isFollowing"] = await is_following(x_user_id, target_uid)
    return resp


@router.patch("")
async def update(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("update", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await update_profile(x_user_id, body)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_private(doc)


@router.delete("", status_code=204)
async def delete(x_user_id: str = Header(...)):
    deleted = await delete_profile(x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    # Clean up all media (profile photo + post images) from Storage
    try:
        delete_user_media(x_user_id)
    except Exception:
        pass  # best-effort — profile is already deleted


@router.post("/photo")
async def upload_photo(
    file: UploadFile = File(...),
    x_user_id: str = Header(...),
):
    """Upload or replace the user's profile photo. Returns { url }."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="File must be an image")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=422, detail="File too large (max 10 MB)")

    url = upload_profile_photo(x_user_id, data, file.content_type, file.filename or "photo.jpg")

    # Persist the URL on the profile document
    await update_profile(x_user_id, {"profilePhoto": url})

    return {"url": url}
