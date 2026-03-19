"""
MongoDB database layer for events.

Soft-delete pattern: documents are never hard-deleted. Instead, `isDeleted`
is set to True and a `deletedAt` timestamp is recorded. All queries exclude
soft-deleted documents by default.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from .schema import get_fields
from .database import get_db


def _events():
    return get_db().events


def _active(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    q: dict[str, Any] = {"isDeleted": {"$ne": True}}
    if extra:
        q.update(extra)
    return q


async def create_event(author_uid: str, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc: dict[str, Any] = {
        "_id": str(ObjectId()),
        "authorUid": author_uid,
    }
    for field in get_fields("event_create"):
        if field == "inviteeUids":
            # Convert inviteeUids list into invitees with pending status
            uids = data.get("inviteeUids") or []
            doc["invitees"] = [{"uid": uid, "status": "pending"} for uid in uids]
        elif field in data:
            doc[field] = data[field]
    doc["createdAt"] = now
    await _events().insert_one(doc)
    return doc


async def update_event(event_id: str, author_uid: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Update an event. Only the author can update."""
    now = datetime.now(timezone.utc).isoformat()
    update_fields: dict[str, Any] = {"updatedAt": now}
    for field in get_fields("event_create"):
        if field == "inviteeUids" and "inviteeUids" in data:
            uids = data.get("inviteeUids") or []
            update_fields["invitees"] = [{"uid": uid, "status": "pending"} for uid in uids]
        elif field in data:
            update_fields[field] = data[field]

    result = await _events().find_one_and_update(
        _active({"_id": event_id, "authorUid": author_uid}),
        {"$set": update_fields},
        return_document=True,
    )
    return result


async def rsvp_event(event_id: str, user_uid: str, status: str) -> bool:
    """Update the RSVP status of an invitee."""
    result = await _events().update_one(
        _active({"_id": event_id, "invitees.uid": user_uid}),
        {"$set": {"invitees.$.status": status}},
    )
    return result.modified_count > 0


async def soft_delete_event(event_id: str, author_uid: str) -> bool:
    """Soft-delete an event. Only the author can delete."""
    now = datetime.now(timezone.utc).isoformat()
    result = await _events().update_one(
        _active({"_id": event_id, "authorUid": author_uid}),
        {"$set": {"isDeleted": True, "deletedAt": now}},
    )
    return result.modified_count > 0
