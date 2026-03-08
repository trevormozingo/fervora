"""
Event integration tests.

Events with iCalendar export, RSVP, recurrence.

Cascade rules:
  - Delete profile → events created by user removed,
    user pulled from invitee lists on other events
"""

import os
import uuid

import pymongo
from bson import ObjectId
from icalendar import Calendar
import requests

BASE = os.environ.get("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "ironguild_test")

EVENT_FIELDS = {"id", "creatorUid", "title", "description", "location",
                "startTime", "endTime", "rrule", "invitees"}


def _uid() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def _username() -> str:
    return f"user_{uuid.uuid4().hex[:10]}"


def _headers(uid: str) -> dict:
    return {"X-User-Id": uid, "Content-Type": "application/json"}


def _create_profile(uid: str, username: str):
    return requests.post(
        f"{BASE}/profile", json={"username": username}, headers=_headers(uid)
    )


def _create_event(uid: str, data: dict) -> requests.Response:
    return requests.post(f"{BASE}/events", json=data, headers=_headers(uid))


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    db.profiles.delete_many({})
    db.posts.delete_many({})
    db.follows.delete_many({})
    db.feed.delete_many({})
    db.reactions.delete_many({})
    db.comments.delete_many({})
    db.events.delete_many({})
    client.close()


# ── Create Event ──────────────────────────────────────────────────────


class TestCreateEvent:
    def test_create_basic_event(self):
        a = _uid()
        _create_profile(a, _username())
        r = _create_event(a, {
            "title": "Morning Workout",
            "startTime": "2026-04-01T08:00:00Z",
        })
        assert r.status_code == 201
        data = r.json()
        assert set(data.keys()) == EVENT_FIELDS
        assert data["creatorUid"] == a
        assert data["title"] == "Morning Workout"
        assert data["startTime"] == "2026-04-01T08:00:00Z"
        assert data["invitees"] == []

    def test_create_event_with_all_fields(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        r = _create_event(a, {
            "title": "Team Lift",
            "description": "Heavy squat day",
            "location": "Iron Gym",
            "startTime": "2026-04-01T08:00:00Z",
            "endTime": "2026-04-01T09:30:00Z",
            "rrule": "FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "inviteeUids": [b],
        })
        assert r.status_code == 201
        data = r.json()
        assert data["description"] == "Heavy squat day"
        assert data["location"] == "Iron Gym"
        assert data["endTime"] == "2026-04-01T09:30:00Z"
        assert data["rrule"] == "FREQ=WEEKLY;BYDAY=MO,WE,FR"
        assert len(data["invitees"]) == 1
        assert data["invitees"][0]["uid"] == b
        assert data["invitees"][0]["status"] == "pending"

    def test_create_event_without_profile(self):
        a = _uid()
        r = _create_event(a, {
            "title": "No Profile Event",
            "startTime": "2026-04-01T08:00:00Z",
        })
        assert r.status_code == 403

    def test_create_event_missing_title(self):
        a = _uid()
        _create_profile(a, _username())
        r = _create_event(a, {"startTime": "2026-04-01T08:00:00Z"})
        assert r.status_code == 422

    def test_create_event_missing_start_time(self):
        a = _uid()
        _create_profile(a, _username())
        r = _create_event(a, {"title": "No Time"})
        assert r.status_code == 422

    def test_create_event_extra_fields_rejected(self):
        a = _uid()
        _create_profile(a, _username())
        r = _create_event(a, {
            "title": "Bad",
            "startTime": "2026-04-01T08:00:00Z",
            "extra": "nope",
        })
        assert r.status_code == 422

    def test_create_event_invalid_rrule(self):
        a = _uid()
        _create_profile(a, _username())
        r = _create_event(a, {
            "title": "Bad Recurrence",
            "startTime": "2026-04-01T08:00:00Z",
            "rrule": "INVALID_RULE",
        })
        assert r.status_code == 422


# ── Get Event ─────────────────────────────────────────────────────────


class TestGetEvent:
    def test_get_event_by_id(self):
        a = _uid()
        _create_profile(a, _username())
        created = _create_event(a, {
            "title": "Get Me",
            "startTime": "2026-04-01T08:00:00Z",
        }).json()
        r = requests.get(f"{BASE}/events/{created['id']}")
        assert r.status_code == 200
        assert r.json()["title"] == "Get Me"

    def test_get_nonexistent_event(self):
        r = requests.get(f"{BASE}/events/{str(ObjectId())}")
        assert r.status_code == 404

    def test_list_own_events(self):
        a = _uid()
        _create_profile(a, _username())
        _create_event(a, {"title": "E1", "startTime": "2026-04-01T08:00:00Z"})
        _create_event(a, {"title": "E2", "startTime": "2026-04-02T08:00:00Z"})
        r = requests.get(f"{BASE}/events", headers=_headers(a))
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        # Should be sorted by startTime
        assert data["items"][0]["title"] == "E1"
        assert data["items"][1]["title"] == "E2"

    def test_list_invited_events(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_event(a, {
            "title": "Invite B",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [b],
        })
        _create_event(a, {
            "title": "No Invite",
            "startTime": "2026-04-02T08:00:00Z",
        })
        r = requests.get(f"{BASE}/events/invited", headers=_headers(b))
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["title"] == "Invite B"


# ── Delete Event ──────────────────────────────────────────────────────


class TestDeleteEvent:
    def test_delete_own_event(self):
        a = _uid()
        _create_profile(a, _username())
        ev = _create_event(a, {
            "title": "Delete Me",
            "startTime": "2026-04-01T08:00:00Z",
        }).json()
        r = requests.delete(f"{BASE}/events/{ev['id']}", headers=_headers(a))
        assert r.status_code == 204
        assert requests.get(f"{BASE}/events/{ev['id']}").status_code == 404

    def test_cannot_delete_others_event(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "A's Event",
            "startTime": "2026-04-01T08:00:00Z",
        }).json()
        r = requests.delete(f"{BASE}/events/{ev['id']}", headers=_headers(b))
        assert r.status_code == 404
        # Still exists
        assert requests.get(f"{BASE}/events/{ev['id']}").status_code == 200

    def test_delete_nonexistent_event(self):
        a = _uid()
        _create_profile(a, _username())
        r = requests.delete(
            f"{BASE}/events/{str(ObjectId())}", headers=_headers(a)
        )
        assert r.status_code == 404


# ── RSVP ──────────────────────────────────────────────────────────────


class TestRSVP:
    def test_accept_invite(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "RSVP Test",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [b],
        }).json()
        r = requests.put(
            f"{BASE}/events/{ev['id']}/rsvp",
            json={"status": "accepted"},
            headers=_headers(b),
        )
        assert r.status_code == 200
        invitee = next(i for i in r.json()["invitees"] if i["uid"] == b)
        assert invitee["status"] == "accepted"

    def test_decline_invite(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "Decline Test",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [b],
        }).json()
        r = requests.put(
            f"{BASE}/events/{ev['id']}/rsvp",
            json={"status": "declined"},
            headers=_headers(b),
        )
        assert r.status_code == 200
        invitee = next(i for i in r.json()["invitees"] if i["uid"] == b)
        assert invitee["status"] == "declined"

    def test_rsvp_not_invited(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "Not Invited",
            "startTime": "2026-04-01T08:00:00Z",
        }).json()
        r = requests.put(
            f"{BASE}/events/{ev['id']}/rsvp",
            json={"status": "accepted"},
            headers=_headers(b),
        )
        assert r.status_code == 404

    def test_rsvp_invalid_status(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "Bad Status",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [b],
        }).json()
        r = requests.put(
            f"{BASE}/events/{ev['id']}/rsvp",
            json={"status": "pending"},
            headers=_headers(b),
        )
        assert r.status_code == 422

    def test_rsvp_change_status(self):
        """Can change RSVP from accepted to declined."""
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "Change RSVP",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [b],
        }).json()
        requests.put(
            f"{BASE}/events/{ev['id']}/rsvp",
            json={"status": "accepted"},
            headers=_headers(b),
        )
        r = requests.put(
            f"{BASE}/events/{ev['id']}/rsvp",
            json={"status": "declined"},
            headers=_headers(b),
        )
        assert r.status_code == 200
        invitee = next(i for i in r.json()["invitees"] if i["uid"] == b)
        assert invitee["status"] == "declined"


# ── iCal Export ───────────────────────────────────────────────────────


class TestICalExport:
    def test_ical_basic(self):
        a = _uid()
        _create_profile(a, _username())
        ev = _create_event(a, {
            "title": "iCal Test",
            "startTime": "2026-04-01T08:00:00Z",
        }).json()
        r = requests.get(f"{BASE}/events/{ev['id']}/ical")
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/calendar; charset=utf-8"
        cal = Calendar.from_ical(r.content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1
        assert str(events[0]["summary"]) == "iCal Test"

    def test_ical_with_all_fields(self):
        a = _uid()
        _create_profile(a, _username())
        ev = _create_event(a, {
            "title": "Full iCal",
            "description": "Detailed event",
            "location": "Iron Gym",
            "startTime": "2026-04-01T08:00:00Z",
            "endTime": "2026-04-01T09:30:00Z",
            "rrule": "FREQ=WEEKLY;BYDAY=MO",
        }).json()
        r = requests.get(f"{BASE}/events/{ev['id']}/ical")
        cal = Calendar.from_ical(r.content)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["summary"]) == "Full iCal"
        assert str(event["description"]) == "Detailed event"
        assert str(event["location"]) == "Iron Gym"
        assert event.get("rrule") is not None

    def test_ical_nonexistent_event(self):
        r = requests.get(f"{BASE}/events/{str(ObjectId())}/ical")
        assert r.status_code == 404


# ── Cascade Delete ────────────────────────────────────────────────────


class TestEventCascade:
    def test_delete_profile_removes_created_events(self):
        a = _uid()
        _create_profile(a, _username())
        ev = _create_event(a, {
            "title": "Will Vanish",
            "startTime": "2026-04-01T08:00:00Z",
        }).json()
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # Verify at DB level
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        assert db.events.count_documents({"creatorUid": a}) == 0
        client.close()

    def test_delete_profile_removes_from_invitee_lists(self):
        a, b = _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        ev = _create_event(a, {
            "title": "Invite B Then Delete B",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [b],
        }).json()
        requests.delete(f"{BASE}/profile", headers=_headers(b))
        # Event still exists but B is removed from invitees
        r = requests.get(f"{BASE}/events/{ev['id']}")
        assert r.status_code == 200
        invitee_uids = [i["uid"] for i in r.json()["invitees"]]
        assert b not in invitee_uids

    def test_cascade_does_not_affect_other_events(self):
        a, b, c = _uid(), _uid(), _uid()
        _create_profile(a, _username())
        _create_profile(b, _username())
        _create_profile(c, _username())
        _create_event(a, {
            "title": "A's Event",
            "startTime": "2026-04-01T08:00:00Z",
            "inviteeUids": [c],
        })
        ev_b = _create_event(b, {
            "title": "B's Event",
            "startTime": "2026-04-02T08:00:00Z",
            "inviteeUids": [c],
        }).json()
        requests.delete(f"{BASE}/profile", headers=_headers(a))
        # B's event is untouched, C still invited
        r = requests.get(f"{BASE}/events/{ev_b['id']}")
        assert r.status_code == 200
        assert r.json()["invitees"][0]["uid"] == c
