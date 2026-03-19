"""Follow routes — one-way follow model (Instagram-style)."""

from fastapi import APIRouter, Header, HTTPException

from .database import get_db
from .follow_database import create_follow, remove_follow
from .cache import (
    get_profile,
    invalidate_profile_counts,
    list_followers,
    list_following,
    invalidate_followers,
    invalidate_following,
)

router = APIRouter(prefix="/follows", tags=["follows"])


# ── Response helpers ──────────────────────────────────────────────────

async def _resolve_profiles(uids: list[str]) -> list[dict]:
    """Resolve UIDs to minimal profile dicts."""
    db = get_db()
    results = []
    for uid in uids:
        doc = await get_profile(uid, db)
        if doc:
            results.append({
                "id": doc["_id"],
                "username": doc["username"],
                "displayName": doc["displayName"],
                "profilePhoto": doc.get("profilePhoto"),
            })
    return results


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/{uid}", status_code=201)
async def follow(uid: str, x_user_id: str = Header(...)):
    if x_user_id == uid:
        raise HTTPException(status_code=422, detail="Cannot follow yourself")

    db = get_db()

    # Both follower and target must have profiles
    follower_profile = await get_profile(x_user_id, db)
    if not follower_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    target_profile = await get_profile(uid, db)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    doc = await create_follow(x_user_id, uid)
    if doc is None:
        raise HTTPException(status_code=409, detail="Already following")

    # Invalidate counts + follow lists for both users
    await invalidate_profile_counts(x_user_id)
    await invalidate_profile_counts(uid)
    await invalidate_following(x_user_id)
    await invalidate_followers(uid)

    return {"followerUid": x_user_id, "followingUid": uid}


@router.delete("/{uid}", status_code=204)
async def unfollow(uid: str, x_user_id: str = Header(...)):
    removed = await remove_follow(x_user_id, uid)
    if not removed:
        raise HTTPException(status_code=404, detail="Not following this user")

    await invalidate_profile_counts(x_user_id)
    await invalidate_profile_counts(uid)
    await invalidate_following(x_user_id)
    await invalidate_followers(uid)


@router.get("/following")
async def my_following(x_user_id: str = Header(...)):
    uids = await list_following(x_user_id, get_db())
    profiles = await _resolve_profiles(uids)
    return {"following": profiles, "count": len(profiles)}


@router.get("/followers")
async def my_followers(x_user_id: str = Header(...)):
    uids = await list_followers(x_user_id, get_db())
    profiles = await _resolve_profiles(uids)
    return {"followers": profiles, "count": len(profiles)}


@router.get("/{uid}/following")
async def user_following(uid: str, x_user_id: str = Header(...)):
    uids = await list_following(uid, get_db())
    profiles = await _resolve_profiles(uids)
    return {"following": profiles, "count": len(profiles)}


@router.get("/{uid}/followers")
async def user_followers(uid: str, x_user_id: str = Header(...)):
    uids = await list_followers(uid, get_db())
    profiles = await _resolve_profiles(uids)
    return {"followers": profiles, "count": len(profiles)}
