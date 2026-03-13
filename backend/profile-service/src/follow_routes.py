"""
Follow routes.

One-way follow model (Instagram-style).
Both follower and target must have existing profiles.
"""

import asyncio

import httpx
from fastapi import APIRouter, Header, HTTPException

from .database import create_notification, follow_user, get_followers, get_following, get_push_tokens, unfollow_user, get_profile_by_id

router = APIRouter(prefix="/follows", tags=["follows"])


async def _notify_new_follower(follower_uid: str, target_uid: str):
    """Send push + in-app notification when someone gains a follower."""
    try:
        follower = await get_profile_by_id(follower_uid)
        name = follower.get("username", "Someone") if follower else "Someone"
        title = f"{name} started following you"
        await create_notification(
            target_uid, "follow", title, "",
            {"followerUid": follower_uid, "followerUsername": name},
        )
        tokens = await get_push_tokens([target_uid])
        if not tokens:
            return
        messages = [
            {"to": t, "sound": "default", "title": title,
             "body": "", "data": {"type": "follow", "followerUsername": name}}
            for t in tokens
        ]
        async with httpx.AsyncClient() as client:
            await client.post("https://exp.host/--/api/v2/push/send", json=messages,
                              headers={"Content-Type": "application/json"})
    except Exception:
        pass


@router.post("/{uid}", status_code=201)
async def follow(uid: str, x_user_id: str = Header(...)):
    if x_user_id == uid:
        raise HTTPException(status_code=422, detail="Cannot follow yourself")
    result = await follow_user(x_user_id, uid)
    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if result is False:
        raise HTTPException(status_code=409, detail="Already following")
    # Fire-and-forget notification
    asyncio.ensure_future(_notify_new_follower(x_user_id, uid))
    return {"followerUid": x_user_id, "followingUid": uid}


@router.delete("/{uid}", status_code=204)
async def unfollow(uid: str, x_user_id: str = Header(...)):
    deleted = await unfollow_user(x_user_id, uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Not following this user")


async def _resolve_profiles(uids: list[str]) -> list[dict]:
    """Resolve UIDs to minimal profile dicts."""
    results = []
    for uid in uids:
        doc = await get_profile_by_id(uid)
        if doc:
            entry: dict = {
                "id": doc["_id"],
                "username": doc["username"],
                "displayName": doc["displayName"],
                "profilePhoto": doc.get("profilePhoto"),
            }
            if doc.get("location"):
                entry["location"] = doc["location"]
            results.append(entry)
    return results


@router.get("/following")
async def list_following(x_user_id: str = Header(...)):
    uids = await get_following(x_user_id)
    profiles = await _resolve_profiles(uids)
    return {"following": profiles, "count": len(profiles)}


@router.get("/followers")
async def list_followers(x_user_id: str = Header(...)):
    uids = await get_followers(x_user_id)
    profiles = await _resolve_profiles(uids)
    return {"followers": profiles, "count": len(profiles)}


@router.get("/{uid}/following")
async def list_user_following(uid: str):
    uids = await get_following(uid)
    profiles = await _resolve_profiles(uids)
    return {"following": profiles, "count": len(profiles)}


@router.get("/{uid}/followers")
async def list_user_followers(uid: str):
    uids = await get_followers(uid)
    profiles = await _resolve_profiles(uids)
    return {"followers": profiles, "count": len(profiles)}
