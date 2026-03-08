"""
Event routes.

CRUD for events with iCalendar (.ics) export.
Events support invitees with RSVP (pending/accepted/declined).
Recurrence via iCal RRULE strings.
"""

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from icalendar import Calendar, Event as ICalEvent
from datetime import datetime

from .database import (
    create_event,
    delete_event,
    get_event,
    get_invited_events,
    get_user_events,
    rsvp_event,
)
from .schema import validate

router = APIRouter(prefix="/events", tags=["events"])


def _to_response(doc: dict) -> dict:
    """Shape a DB doc into the base.schema.json response."""
    return {
        "id": str(doc["_id"]),
        "creatorUid": doc["creatorUid"],
        "title": doc["title"],
        "description": doc.get("description"),
        "location": doc.get("location"),
        "startTime": doc["startTime"],
        "endTime": doc.get("endTime"),
        "rrule": doc.get("rrule"),
        "invitees": doc.get("invitees", []),
    }


@router.post("", status_code=201)
async def create(request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("event_create", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await create_event(x_user_id, body)
    if doc is None:
        raise HTTPException(status_code=403, detail="Profile required to create events")
    return _to_response(doc)


@router.get("", summary="List events created by the caller")
async def list_own(x_user_id: str = Header(...)):
    events = await get_user_events(x_user_id)
    items = [_to_response(e) for e in events]
    return {"items": items, "count": len(items)}


@router.get("/invited", summary="List events the caller is invited to")
async def list_invited(x_user_id: str = Header(...)):
    events = await get_invited_events(x_user_id)
    items = [_to_response(e) for e in events]
    return {"items": items, "count": len(items)}


@router.get("/{event_id}")
async def get(event_id: str):
    doc = await get_event(event_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _to_response(doc)


@router.delete("/{event_id}", status_code=204)
async def delete(event_id: str, x_user_id: str = Header(...)):
    deleted = await delete_event(event_id, x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found or not owned by you")


@router.put("/{event_id}/rsvp")
async def rsvp(event_id: str, request: Request, x_user_id: str = Header(...)):
    body = await request.json()
    errors = validate("event_rsvp", body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    doc = await rsvp_event(event_id, x_user_id, body["status"])
    if doc is None:
        raise HTTPException(status_code=404, detail="Event not found or you are not invited")
    return _to_response(doc)


@router.get("/{event_id}/ical", summary="Export event as .ics file")
async def export_ical(event_id: str):
    doc = await get_event(event_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Event not found")

    cal = Calendar()
    cal.add("prodid", "-//IronGuild//Events//EN")
    cal.add("version", "2.0")

    event = ICalEvent()
    event.add("uid", str(doc["_id"]) + "@ironguild")
    event.add("summary", doc["title"])
    event.add("dtstart", datetime.fromisoformat(doc["startTime"]))

    if doc.get("endTime"):
        event.add("dtend", datetime.fromisoformat(doc["endTime"]))
    if doc.get("description"):
        event.add("description", doc["description"])
    if doc.get("location"):
        event.add("location", doc["location"])
    if doc.get("rrule"):
        # Parse RRULE string into components for icalendar lib
        event.add("rrule", _parse_rrule(doc["rrule"]))

    cal.add_component(event)

    return Response(
        content=cal.to_ical(),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="event-{event_id}.ics"'},
    )


def _parse_rrule(rrule_str: str) -> dict:
    """Parse an RRULE string like FREQ=WEEKLY;BYDAY=MO into a dict for icalendar."""
    parts = rrule_str.split(";")
    result = {}
    for part in parts:
        key, value = part.split("=", 1)
        key = key.strip().upper()
        value = value.strip()
        if "," in value:
            result[key] = value.split(",")
        else:
            result[key] = value
    return result
