"""
Profile routes.

Response shapes match public.schema.json and private.schema.json exactly:
  { id, username, displayName, bio, birthday }
"""

from fastapi import APIRouter, Header, HTTPException, Request

from .database import (
    create_profile,
    delete_profile,
    get_profile_by_id,
    get_profile_by_username,
    update_profile,
)
from .schema import validate

router = APIRouter(prefix="/profile", tags=["profile"])


def _to_public(doc: dict) -> dict:
    """Shape a DB doc into the public.schema.json response."""
    return {
        "id": doc["_id"],
        "username": doc["username"],
        "displayName": doc["displayName"],
        "bio": doc.get("bio"),
        "birthday": doc.get("birthday"),
    }


def _to_private(doc: dict) -> dict:
    """Shape a DB doc into the private.schema.json response."""
    return {
        "id": doc["_id"],
        "username": doc["username"],
        "displayName": doc["displayName"],
        "bio": doc.get("bio"),
        "birthday": doc.get("birthday"),
    }


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
