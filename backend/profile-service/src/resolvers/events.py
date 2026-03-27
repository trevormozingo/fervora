from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
import strawberry
from strawberry.types import Info

from ..types.event import Event, CreateEventInput, RsvpInput
from ..cache import cached_or_fetch, set_cached, _event_key, TTL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_from_doc(doc: dict) -> Event:
    return Event(
        id=strawberry.ID(str(doc["_id"])),
        organizer_uid=doc["organizerUid"],
        title=doc["title"],
        description=doc.get("description"),
        location=doc.get("location"),
        starts_at=doc["startsAt"],
        ends_at=doc.get("endsAt"),
        created_at=doc["createdAt"],
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@strawberry.type
class EventQuery:

    @strawberry.field
    async def event(self, info: Info, id: strawberry.ID) -> Event:
        """Get a single event by ID."""
        db = info.context["db"]
        redis = info.context["redis"]
        event_id = str(id)
        try:
            oid = ObjectId(event_id)
        except InvalidId:
            raise ValueError("invalid event id")
        doc = await cached_or_fetch(_event_key(event_id), db.events, oid, redis)
        if doc is None:
            raise ValueError("event not found")
        return _event_from_doc(doc)


# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class EventMutation:

    @strawberry.mutation
    async def create_event(self, info: Info, input: CreateEventInput) -> Event:
        """Create an event and optionally invite users."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        if not await db.profiles.find_one({"_id": user_id, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("cannot create event: your profile does not exist or was deleted")

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "organizerUid": user_id,
            "title": input.title,
            "description": input.description,
            "location": input.location,
            "startsAt": input.starts_at,
            "endsAt": input.ends_at,
            "createdAt": now,
            "isDeleted": False,
        }

        result = await db.events.insert_one(doc)
        event_id = str(result.inserted_id)
        doc["_id"] = event_id
        await set_cached(redis, _event_key(event_id), doc)

        # Organizer is auto-RSVPed as "going"
        await db.rsvps.insert_one({
            "eventId": event_id,
            "userId": user_id,
            "status": "going",
            "createdAt": now,
            "isDeleted": False,
        })

        # Insert invites ONLY for users who actually exist in the DB
        if input.invited_user_ids:
            raw_invited = list({str(uid) for uid in input.invited_user_ids} - {user_id})
            if raw_invited:
                valid_profiles_cursor = db.profiles.find(
                    {"_id": {"$in": raw_invited}, "isDeleted": {"$ne": True}}, 
                    {"_id": 1}
                )
                valid_invited_docs = await valid_profiles_cursor.to_list(length=None)
                valid_invited_ids = [d["_id"] for d in valid_invited_docs]

                if valid_invited_ids:
                    await db.rsvps.insert_many([
                        {
                            "eventId": event_id,
                            "userId": uid,
                            "status": "maybe",
                            "createdAt": now,
                            "isDeleted": False,
                        }
                        for uid in valid_invited_ids
                    ])

        return _event_from_doc(doc)

    @strawberry.mutation
    async def rsvp_event(self, info: Info, input: RsvpInput) -> bool:
        """Set or update the current user's RSVP status for an event."""
        db = info.context["db"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        # Ensure the user has an active profile
        if not await db.profiles.find_one({"_id": user_id, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("cannot rsvp: your profile does not exist or was deleted")

        try:
            event_oid = ObjectId(str(input.event_id))
        except InvalidId:
            raise ValueError("invalid event id")

        if not await db.events.find_one({"_id": event_oid, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("cannot rsvp: event does not exist or was deleted")

        now = datetime.now(timezone.utc).isoformat()
        await db.rsvps.find_one_and_update(
            {"eventId": str(input.event_id), "userId": user_id},
            {
                "$set": {"status": input.status, "isDeleted": False},
                "$setOnInsert": {"createdAt": now}
            },
            upsert=True,
        )
        return True

    @strawberry.mutation
    async def delete_event(self, info: Info, id: strawberry.ID) -> bool:
        """Soft-delete an event (organizer only)."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        try:
            oid = ObjectId(str(id))
        except InvalidId:
            raise ValueError("invalid event id")

        result = await db.events.update_one(
            {"_id": oid, "organizerUid": user_id},
            {"$set": {"isDeleted": True}},
        )

        if result.modified_count > 0:
            await redis.setex(_event_key(str(id)), TTL, "__nil__")
            return True

        return False
