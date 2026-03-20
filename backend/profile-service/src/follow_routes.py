"""Follow routes — one-way follow model (Instagram-style)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from .database import get_db
from .follow_database import create_follow, create_follow_in_session, remove_follow
from .transaction import run_transaction
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

    async def _txn(session):
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        result = await db.profiles.update_one(
            {"_id": x_user_id, "isDeleted": {"$ne": True}},
            {"$set": {"lastActivityAt": now}},
            session=session,
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=403, detail="Profile is deleted or does not exist")

        target_result = await db.profiles.update_one(
            {"_id": uid, "isDeleted": {"$ne": True}},
            {"$set": {"lastActivityAt": now}},
            session=session,
        )
        if target_result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Target profile not found")

        doc = await create_follow_in_session(x_user_id, uid, session)
        if doc is None:
            raise HTTPException(status_code=409, detail="Already following")
        return doc

    await run_transaction(_txn)
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
