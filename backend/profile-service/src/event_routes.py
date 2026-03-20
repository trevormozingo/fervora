"""Event routes — CRUD + RSVP."""

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from .database import get_db
from .event_database import (
    create_event,
    create_event_in_session,
    rsvp_event,
    soft_delete_event,
    update_event,
)
from .transaction import run_transaction
from .cache import (
    get_event,
    get_profile,
    invalidate_event,
    invalidate_event_list,
    list_events_by_author,
)
from .schema import get_fields, validate

router = APIRouter(prefix="/events", tags=["events"])


# ── Response builder ──────────────────────────────────────────────────

_RESPONSE_FIELDS: set[str] | None = None


def _get_response_fields() -> set[str]:
    global _RESPONSE_FIELDS
    if _RESPONSE_FIELDS is None:
        _RESPONSE_FIELDS = set(get_fields("event_base"))
    return _RESPONSE_FIELDS


async def _to_response(doc: dict) -> dict:
    """Build a response dict from a DB document."""
    fields = _get_response_fields()

    author_profile = await get_profile(doc["authorUid"], get_db())
    author_username = author_profile["username"] if author_profile else None

    out: dict = {}
    for field in fields:
        if field == "id":
            out["id"] = doc["_id"]
        else:
            out[field] = doc.get(field)
    out["authorUsername"] = author_username
    return out


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create(request_body: dict, x_user_id: str = Header(...)):
    errors = validate("event_create", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

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
        return await create_event_in_session(x_user_id, request_body, session)

    doc = await run_transaction(_txn)
    await invalidate_event_list(x_user_id)
    return await _to_response(doc)


@router.get("/{event_id}")
async def get_by_id(event_id: str, x_user_id: str = Header(...)):
    doc = await get_event(event_id, get_db())
    if not doc:
        raise HTTPException(status_code=404, detail="Event not found")
    return await _to_response(doc)


@router.get("")
async def list_by_author(author: str, x_user_id: str = Header(...)):
    """List events by a specific author. Query param: ?author=<uid>"""
    docs = await list_events_by_author(author, get_db())
    return [await _to_response(d) for d in docs]


@router.patch("/{event_id}")
async def update(event_id: str, request_body: dict, x_user_id: str = Header(...)):
    errors = validate("event_create", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    doc = await update_event(event_id, x_user_id, request_body)
    if not doc:
        raise HTTPException(status_code=404, detail="Event not found")

    await invalidate_event(event_id)
    await invalidate_event_list(x_user_id)
    return await _to_response(doc)


@router.post("/{event_id}/rsvp", status_code=200)
async def rsvp(event_id: str, request_body: dict, x_user_id: str = Header(...)):
    errors = validate("event_rsvp", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    doc = await get_event(event_id, get_db())
    if not doc:
        raise HTTPException(status_code=404, detail="Event not found")

    # Verify user is an invitee
    invitee_uids = [i["uid"] for i in (doc.get("invitees") or [])]
    if x_user_id not in invitee_uids:
        raise HTTPException(status_code=403, detail="Not invited to this event")

    updated = await rsvp_event(event_id, x_user_id, request_body["status"])
    if not updated:
        raise HTTPException(status_code=404, detail="Event not found")

    await invalidate_event(event_id)

    refreshed = await get_event(event_id, get_db())
    return await _to_response(refreshed)


@router.delete("/{event_id}", status_code=204)
async def delete(event_id: str, x_user_id: str = Header(...)):
    deleted = await soft_delete_event(event_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    await invalidate_event(event_id)
    await invalidate_event_list(x_user_id)
