"""
Profile routes.

Response shapes match public.schema.json and private.schema.json exactly:
  { id, username, displayName, bio, birthday }
"""

from fastapi import APIRouter, Header, HTTPException, Query, Request, UploadFile, File

from .database import (
    create_profile,
    delete_profile,
    get_nearby_profiles,
    get_profile_by_id,
    get_profile_by_username,
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
    return _to_private(doc)


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


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    docs = await search_profiles(q, limit)
    return [_to_public(doc) for doc in docs]


@router.get("/uid/{uid}")
async def get_by_uid(uid: str):
    doc = await get_profile_by_id(uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_public(doc)


@router.get("/{username}")
async def get_public(username: str):
    doc = await get_profile_by_username(username)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_public(doc)


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
