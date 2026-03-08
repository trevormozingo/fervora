"""
API Gateway route handlers.

All incoming requests go through:
  1. Auth extraction — Bearer token → Firebase UID
  2. Proxy — forward to the appropriate backend service with X-User-Id header

Routes:
  /profile/**                      → profile-service
  /posts/**                        → profile-service
  /follows/**                      → profile-service
  /feed                            → profile-service
  /events/**                       → profile-service
  /health                          → gateway health check (no auth)
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from .auth import verify_token
from .proxy import forward_request

router = APIRouter()


def _extract_bearer_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _require_auth(request: Request) -> str:
    """
    Verify the Bearer token and return the Firebase UID.
    Raises 401 if missing/invalid.
    """
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    try:
        claims = verify_token(token)
        return claims["uid"]
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def _optional_auth(request: Request) -> str | None:
    """
    Try to extract a UID from the Bearer token. Returns None if no token present.
    Raises 401 only if a token IS present but invalid.
    """
    token = _extract_bearer_token(request)
    if not token:
        return None
    try:
        claims = verify_token(token)
        return claims["uid"]
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def _proxy_to_service(
    service: str,
    path: str,
    request: Request,
    uid: str | None = None,
):
    """
    Forward the request to a backend service and return the response.
    Injects X-User-Id if a UID is provided.
    """
    # Build headers to forward
    headers = dict(request.headers)
    if uid:
        headers["x-user-id"] = uid
    # Remove the original Authorization header — backend services don't need it
    headers.pop("authorization", None)

    body = await request.body() if request.method in ("POST", "PATCH", "PUT") else None

    # Forward query parameters
    query_string = str(request.url.query) if request.url.query else ""

    try:
        resp = await forward_request(
            service=service,
            path=path,
            method=request.method,
            headers=headers,
            body=body,
            query_string=query_string,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Backend service unavailable")

    # Forward the backend response as-is
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in ("transfer-encoding", "connection")
        },
    )


# ─────────────────────────────────────────────────────────────────────
# Profile routes — auth required for mutations, optional for public
# ─────────────────────────────────────────────────────────────────────


@router.post("/profile")
async def create_profile(request: Request):
    """Create a profile — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("profile", "", request, uid)


@router.get("/profile")
async def get_my_profile(request: Request):
    """Get own profile — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("profile", "", request, uid)


@router.patch("/profile")
async def update_my_profile(request: Request):
    """Update own profile — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("profile", "", request, uid)


@router.delete("/profile")
async def delete_my_profile(request: Request):
    """Delete own profile — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("profile", "", request, uid)


@router.get("/profile/{username}")
async def get_public_profile(username: str, request: Request):
    """Get a public profile by username — no auth required."""
    return await _proxy_to_service("profile", f"/{username}", request)


# ─────────────────────────────────────────────────────────────────────
# Post routes — auth required
# ─────────────────────────────────────────────────────────────────────


@router.post("/posts")
async def create_post(request: Request):
    """Create a post — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("posts", "", request, uid)


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, request: Request):
    """Delete a post — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("posts", f"/{post_id}", request, uid)


# ─────────────────────────────────────────────────────────────────────
# Follow routes — auth required
# ─────────────────────────────────────────────────────────────────────


@router.post("/follows/{uid}")
async def follow_user(uid: str, request: Request):
    """Follow a user — requires auth."""
    caller_uid = _require_auth(request)
    return await _proxy_to_service("follows", f"/{uid}", request, caller_uid)


@router.delete("/follows/{uid}")
async def unfollow_user(uid: str, request: Request):
    """Unfollow a user — requires auth."""
    caller_uid = _require_auth(request)
    return await _proxy_to_service("follows", f"/{uid}", request, caller_uid)


@router.get("/follows/following")
async def get_following(request: Request):
    """Get the list of users the caller follows — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("follows", "/following", request, uid)


@router.get("/follows/followers")
async def get_followers(request: Request):
    """Get the list of users who follow the caller — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("follows", "/followers", request, uid)


# ─────────────────────────────────────────────────────────────────────
# Feed routes — auth required
# ─────────────────────────────────────────────────────────────────────


@router.get("/feed")
async def get_feed(request: Request):
    """Get the caller's feed — requires auth. Supports ?limit=&cursor= query params."""
    uid = _require_auth(request)
    return await _proxy_to_service("feed", "", request, uid)


# ─────────────────────────────────────────────────────────────────────
# Reaction routes — auth required for mutations, public for reads
# ─────────────────────────────────────────────────────────────────────


@router.put("/posts/{post_id}/reactions")
async def set_reaction(post_id: str, request: Request):
    """Set a reaction on a post — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("posts", f"/{post_id}/reactions", request, uid)


@router.delete("/posts/{post_id}/reactions")
async def remove_reaction(post_id: str, request: Request):
    """Remove a reaction from a post — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("posts", f"/{post_id}/reactions", request, uid)


@router.get("/posts/{post_id}/reactions")
async def get_reactions(post_id: str, request: Request):
    """Get reactions on a post — no auth required."""
    return await _proxy_to_service("posts", f"/{post_id}/reactions", request)


# ─────────────────────────────────────────────────────────────────────
# Comment routes — auth required for mutations, public for reads
# ─────────────────────────────────────────────────────────────────────


@router.post("/posts/{post_id}/comments")
async def create_comment(post_id: str, request: Request):
    """Create a comment on a post — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("posts", f"/{post_id}/comments", request, uid)


@router.delete("/posts/{post_id}/comments/{comment_id}")
async def delete_comment(post_id: str, comment_id: str, request: Request):
    """Delete a comment — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service(
        "posts", f"/{post_id}/comments/{comment_id}", request, uid
    )


@router.get("/posts/{post_id}/comments")
async def get_comments(post_id: str, request: Request):
    """Get comments on a post — no auth required. Supports ?limit=&cursor= query params."""
    return await _proxy_to_service("posts", f"/{post_id}/comments", request)


# ─────────────────────────────────────────────────────────────────────
# Event routes — auth required for mutations, public for reads
# ─────────────────────────────────────────────────────────────────────


@router.post("/events")
async def create_event(request: Request):
    """Create an event — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("events", "", request, uid)


@router.get("/events")
async def list_own_events(request: Request):
    """List events created by the caller — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("events", "", request, uid)


@router.get("/events/invited")
async def list_invited_events(request: Request):
    """List events the caller is invited to — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("events", "/invited", request, uid)


@router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request):
    """Get an event by ID — no auth required."""
    return await _proxy_to_service("events", f"/{event_id}", request)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, request: Request):
    """Delete an event — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("events", f"/{event_id}", request, uid)


@router.put("/events/{event_id}/rsvp")
async def rsvp_event(event_id: str, request: Request):
    """RSVP to an event — requires auth."""
    uid = _require_auth(request)
    return await _proxy_to_service("events", f"/{event_id}/rsvp", request, uid)


@router.get("/events/{event_id}/ical")
async def export_ical(event_id: str, request: Request):
    """Export event as .ics file — no auth required."""
    return await _proxy_to_service("events", f"/{event_id}/ical", request)
