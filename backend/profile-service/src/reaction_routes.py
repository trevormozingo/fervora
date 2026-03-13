"""
Reaction routes.

Emoji reactions on posts. One reaction per user per post.
Supported types: strong, fire, heart, smile, laugh, thumbsup, thumbsdown, angry.
"""

import asyncio

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from .database import get_reactions, get_push_tokens, create_notification, remove_reaction, set_reaction, get_profile_by_id
from .schema import validate

REACTION_EMOJI = {
    "strong": "💪", "fire": "🔥", "heart": "❤️", "smile": "😊",
    "laugh": "😂", "thumbsup": "👍", "thumbsdown": "👎", "angry": "😡",
}

router = APIRouter(prefix="/posts", tags=["reactions"])


async def _notify_post_author_reaction(post_id: str, reactor_uid: str, reaction_type: str):
    """Send push notification to the post author about a new reaction."""
    try:
        from .database import _posts
        from bson import ObjectId
        post = await _posts().find_one({"_id": ObjectId(post_id)})
        if not post or post["authorUid"] == reactor_uid:
            return
        reactor = await get_profile_by_id(reactor_uid)
        name = reactor.get("username", "Someone") if reactor else "Someone"
        photo = reactor.get("profilePhoto", "") if reactor else ""
        emoji = REACTION_EMOJI.get(reaction_type, reaction_type)
        title = f"{name} reacted {emoji} to your post"
        # Save in-app notification
        await create_notification(
            post["authorUid"], "reaction", title, "",
            {"postId": post_id, "reactorUid": reactor_uid, "reactionType": reaction_type, "profilePhoto": photo},
        )
        # Send push
        tokens = await get_push_tokens([post["authorUid"]])
        if not tokens:
            return
        messages = [
            {"to": t, "sound": "default", "title": title,
             "body": "", "data": {"type": "reaction", "postId": post_id}}
            for t in tokens
        ]
        async with httpx.AsyncClient() as client:
            await client.post("https://exp.host/--/api/v2/push/send", json=messages,
                              headers={"Content-Type": "application/json"})
    except Exception:
        pass


@router.put("/{post_id}/reactions", status_code=200)
async def react(post_id: str, request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("reaction_set", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await set_reaction(post_id, x_user_id, body["type"])
    if doc is None:
        raise HTTPException(status_code=404, detail="Post not found")
    # Fire-and-forget push notification to post author
    asyncio.ensure_future(_notify_post_author_reaction(post_id, x_user_id, body["type"]))
    return {"postId": post_id, "authorUid": x_user_id, "type": doc["type"]}


@router.delete("/{post_id}/reactions", status_code=204)
async def unreact(post_id: str, x_user_id: str = Header(...)):
    deleted = await remove_reaction(post_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reaction not found")


@router.get("/{post_id}/reactions")
async def list_reactions(post_id: str):
    reactions = await get_reactions(post_id)
    # Resolve usernames and profile photos
    uids = list({r["authorUid"] for r in reactions})
    profile_data = {}
    for uid in uids:
        p = await get_profile_by_id(uid)
        if p:
            profile_data[uid] = {
                "username": p.get("username", uid),
                "profilePhoto": p.get("profilePhoto"),
            }
    for r in reactions:
        info = profile_data.get(r["authorUid"], {})
        r["username"] = info.get("username", r["authorUid"])
        r["profilePhoto"] = info.get("profilePhoto")
    return {"reactions": reactions, "count": len(reactions)}
