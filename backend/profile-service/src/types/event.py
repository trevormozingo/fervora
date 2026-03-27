from __future__ import annotations
from typing import Annotated, Optional, TYPE_CHECKING
import strawberry
from strawberry.types import Info
from .profile import Profile

if TYPE_CHECKING:
    pass


VALID_RSVP_STATUSES = {"going", "maybe", "not_going"}


def _parse_event_title(value: str) -> str:
    if not (1 <= len(value) <= 200):
        raise ValueError("title must be between 1 and 200 characters")
    return value


def _parse_event_description(value: str) -> str:
    if len(value) > 2000:
        raise ValueError("description must be 2000 characters or fewer")
    return value


def _parse_rsvp_status(value: str) -> str:
    if value not in VALID_RSVP_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_RSVP_STATUSES)}")
    return value


EventTitle = strawberry.scalar(str, name="EventTitle", parse_value=_parse_event_title)
EventDescription = strawberry.scalar(str, name="EventDescription", parse_value=_parse_event_description)
RsvpStatus = strawberry.scalar(str, name="RsvpStatus", parse_value=_parse_rsvp_status)


# ── Output types ──────────────────────────────────────────────────────────────

@strawberry.type
class RsvpSummary:
    status: str
    count: int


@strawberry.type
class Rsvp:
    id: strawberry.ID
    user_id: strawberry.Private[str]
    status: str

    @strawberry.field
    async def user(self, info: Info) -> Optional[Profile]:
        return await info.context["profile_loader"].load(self.user_id)


@strawberry.type
class RsvpPage:
    rsvps: list[Rsvp]
    next_cursor: Optional[str]


@strawberry.type
class Event:
    id: strawberry.ID
    organizer_uid: strawberry.Private[str]
    title: str
    description: Optional[str]
    location: Optional[str]
    starts_at: str
    ends_at: Optional[str]
    created_at: str

    @strawberry.field
    async def organizer(self, info: Info) -> Optional[Profile]:
        return await info.context["profile_loader"].load(self.organizer_uid)

    @strawberry.field
    async def rsvp_summaries(self, info: Info) -> list[RsvpSummary]:
        """Grouped RSVP counts for UI badges (e.g. [{status: 'going', count: 12}])."""
        loader = info.context["rsvp_summary_loader"]
        return await loader.load(str(self.id))

    @strawberry.field
    async def rsvps(
        self,
        info: Info,
        limit: int = 50,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> "RsvpPage":
        """Paginated list of RSVPs, optionally filtered by status."""
        from bson import ObjectId
        from bson.errors import InvalidId
        db = info.context["db"]
        query: dict = {"eventId": str(self.id), "isDeleted": {"$ne": True}}
        if status:
            query["status"] = status
        if cursor:
            try:
                query["_id"] = {"$gt": ObjectId(cursor)}
            except InvalidId:
                raise ValueError("invalid cursor")
        docs = await db.rsvps.find(query).sort("_id", 1).limit(limit).to_list(length=limit)
        rsvps = [
            Rsvp(id=strawberry.ID(str(d["_id"])), user_id=d["userId"], status=d["status"])
            for d in docs
        ]
        next_cursor = str(docs[-1]["_id"]) if len(docs) == limit else None
        return RsvpPage(rsvps=rsvps, next_cursor=next_cursor)

    @strawberry.field
    async def viewer_rsvp(self, info: Info) -> Optional[str]:
        """Returns the current user's RSVP status for this event, or None."""
        user_id = info.context.get("user_id")
        if not user_id:
            return None
        loader = info.context["viewer_rsvp_loader"]
        return await loader.load(str(self.id))


# ── Input types ───────────────────────────────────────────────────────────────

@strawberry.input
class CreateEventInput:
    title: EventTitle
    starts_at: str
    description: Optional[EventDescription] = None
    location: Optional[str] = None
    ends_at: Optional[str] = None
    invited_user_ids: Optional[list[strawberry.ID]] = None


@strawberry.input
class RsvpInput:
    event_id: strawberry.ID
    status: RsvpStatus
