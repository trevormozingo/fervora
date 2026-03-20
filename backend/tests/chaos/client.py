"""Async HTTP client wrapper for every Fervora API endpoint."""

import httpx

from .config import SERVICE_URL


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid, "Content-Type": "application/json"}


class ApiClient:
    """Thin async wrapper around the Fervora REST API."""

    def __init__(self, base_url: str = SERVICE_URL, timeout: float = 30.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def close(self):
        await self._client.aclose()

    # ── Profiles ──────────────────────────────────────────────────────

    async def create_profile(self, uid: str, username: str) -> httpx.Response:
        return await self._client.post(
            "/profiles",
            json={
                "username": username,
                "displayName": f"User {username}",
                "profilePhoto": f"https://example.com/{username}.jpg",
                "birthday": "1998-05-14",
            },
            headers=_headers(uid),
        )

    async def get_profile(self, uid: str, target_uid: str | None = None) -> httpx.Response:
        path = f"/profiles/{target_uid}" if target_uid else "/profiles/me"
        return await self._client.get(path, headers=_headers(uid))

    async def delete_profile(self, uid: str) -> httpx.Response:
        return await self._client.delete("/profiles/me", headers=_headers(uid))

    # ── Posts ─────────────────────────────────────────────────────────

    async def create_post(self, uid: str, title: str) -> httpx.Response:
        return await self._client.post(
            "/posts",
            json={"title": title},
            headers=_headers(uid),
        )

    async def get_post(self, uid: str, post_id: str) -> httpx.Response:
        return await self._client.get(f"/posts/{post_id}", headers=_headers(uid))

    async def delete_post(self, uid: str, post_id: str) -> httpx.Response:
        return await self._client.delete(f"/posts/{post_id}", headers=_headers(uid))

    # ── Comments ──────────────────────────────────────────────────────

    async def create_comment(self, uid: str, post_id: str, body: str) -> httpx.Response:
        return await self._client.post(
            f"/posts/{post_id}/comments",
            json={"body": body},
            headers=_headers(uid),
        )

    async def delete_comment(self, uid: str, post_id: str, comment_id: str) -> httpx.Response:
        return await self._client.delete(
            f"/posts/{post_id}/comments/{comment_id}",
            headers=_headers(uid),
        )

    # ── Reactions ─────────────────────────────────────────────────────

    async def set_reaction(self, uid: str, post_id: str, reaction_type: str) -> httpx.Response:
        return await self._client.put(
            f"/posts/{post_id}/reactions",
            json={"type": reaction_type},
            headers=_headers(uid),
        )

    async def remove_reaction(self, uid: str, post_id: str) -> httpx.Response:
        return await self._client.delete(
            f"/posts/{post_id}/reactions",
            headers=_headers(uid),
        )

    # ── Events ────────────────────────────────────────────────────────

    async def create_event(
        self, uid: str, title: str, start_time: str, invitee_uids: list[str] | None = None
    ) -> httpx.Response:
        body: dict = {"title": title, "startTime": start_time}
        if invitee_uids:
            body["inviteeUids"] = invitee_uids
        return await self._client.post("/events", json=body, headers=_headers(uid))

    async def delete_event(self, uid: str, event_id: str) -> httpx.Response:
        return await self._client.delete(f"/events/{event_id}", headers=_headers(uid))

    # ── Follows ───────────────────────────────────────────────────────

    async def follow(self, uid: str, target_uid: str) -> httpx.Response:
        return await self._client.post(f"/follows/{target_uid}", headers=_headers(uid))

    async def unfollow(self, uid: str, target_uid: str) -> httpx.Response:
        return await self._client.delete(f"/follows/{target_uid}", headers=_headers(uid))

    # ── Feed ──────────────────────────────────────────────────────────

    async def get_feed(self, uid: str, limit: int = 20, cursor: str | None = None) -> httpx.Response:
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._client.get("/feed", headers=_headers(uid), params=params)
