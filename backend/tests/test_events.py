"""Event service integration tests."""

import os

import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _headers(uid: str = "event-test-user") -> dict:
    return {"X-User-Id": uid}


def _ensure_profile(uid: str = "event-test-user", username: str = "eventtester"):
    r = requests.get(_url(f"/profiles/{uid}"), headers=_headers(uid))
    if r.status_code == 404:
        body = {
            "username": username,
            "displayName": "Event Tester",
            "profilePhoto": "https://example.com/photo.jpg",
            "birthday": "1998-05-14",
        }
        r = requests.post(_url("/profiles"), json=body, headers=_headers(uid))
        assert r.status_code == 201


def setup_module():
    """Clear events collection and ensure test profiles exist."""
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].events.delete_many({})
    client.close()
    _ensure_profile()
    _ensure_profile("event-invitee", "eventinvitee")
    _ensure_profile("event-invitee2", "eventinvitee2")


def _base_event() -> dict:
    return {
        "title": "Morning Run",
        "startTime": "2026-04-01T08:00:00Z",
    }


# ── Create ────────────────────────────────────────────────────────────

def test_create_event():
    body = _base_event()
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Morning Run"
    assert data["authorUid"] == "event-test-user"
    assert data["startTime"] == "2026-04-01T08:00:00Z"
    assert data["authorUsername"] == "eventtester"
    assert data["id"] is not None


def test_create_event_all_fields():
    body = {
        "title": "Full Event",
        "description": "A detailed description",
        "location": "Central Park",
        "startTime": "2026-04-01T08:00:00Z",
        "endTime": "2026-04-01T10:00:00Z",
        "rrule": "FREQ=WEEKLY;BYDAY=MO",
        "inviteeUids": ["event-invitee"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Full Event"
    assert data["description"] == "A detailed description"
    assert data["location"] == "Central Park"
    assert data["endTime"] == "2026-04-01T10:00:00Z"
    assert data["rrule"] == "FREQ=WEEKLY;BYDAY=MO"
    assert len(data["invitees"]) == 1
    assert data["invitees"][0]["uid"] == "event-invitee"
    assert data["invitees"][0]["status"] == "pending"


def test_create_event_with_multiple_invitees():
    body = {
        "title": "Group Workout",
        "startTime": "2026-04-02T09:00:00Z",
        "inviteeUids": ["event-invitee", "event-invitee2"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    invitees = r.json()["invitees"]
    assert len(invitees) == 2
    assert all(i["status"] == "pending" for i in invitees)


# ── Read ──────────────────────────────────────────────────────────────

def test_get_event_by_id():
    body = _base_event()
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    r = requests.get(_url(f"/events/{event_id}"), headers=_headers())
    assert r.status_code == 200
    assert r.json()["id"] == event_id
    assert r.json()["title"] == "Morning Run"


def test_get_event_not_found():
    r = requests.get(_url("/events/nonexistent123"), headers=_headers())
    assert r.status_code == 404


def test_list_events_by_author():
    # Create events under a unique user
    uid = "event-list-user"
    _ensure_profile(uid, "eventlistuser")

    for i in range(3):
        body = {"title": f"Event {i}", "startTime": f"2026-05-0{i+1}T08:00:00Z"}
        r = requests.post(_url("/events"), json=body, headers=_headers(uid))
        assert r.status_code == 201

    r = requests.get(_url(f"/events?author={uid}"), headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3


def test_list_events_returns_newest_first():
    uid = "event-order-user"
    _ensure_profile(uid, "eventorderuser")

    titles = ["First", "Second", "Third"]
    for i, t in enumerate(titles):
        body = {"title": t, "startTime": f"2026-06-0{i+1}T08:00:00Z"}
        r = requests.post(_url("/events"), json=body, headers=_headers(uid))
        assert r.status_code == 201

    r = requests.get(_url(f"/events?author={uid}"), headers=_headers())
    data = r.json()
    assert data[0]["title"] == "Third"
    assert data[2]["title"] == "First"


# ── Update ────────────────────────────────────────────────────────────

def test_update_event():
    body = _base_event()
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    update = {"title": "Evening Run", "startTime": "2026-04-01T18:00:00Z"}
    r = requests.patch(_url(f"/events/{event_id}"), json=update, headers=_headers())
    assert r.status_code == 200
    assert r.json()["title"] == "Evening Run"
    assert r.json()["startTime"] == "2026-04-01T18:00:00Z"


def test_update_event_not_found():
    update = {"title": "Ghost", "startTime": "2026-04-01T08:00:00Z"}
    r = requests.patch(_url("/events/nonexistent123"), json=update, headers=_headers())
    assert r.status_code == 404


def test_cannot_update_other_users_event():
    body = _base_event()
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    update = {"title": "Hijack", "startTime": "2026-04-01T08:00:00Z"}
    r = requests.patch(_url(f"/events/{event_id}"), json=update, headers=_headers("other-user"))
    assert r.status_code == 404


# ── RSVP ──────────────────────────────────────────────────────────────

def test_rsvp_accept():
    body = {
        "title": "RSVP Test",
        "startTime": "2026-04-01T08:00:00Z",
        "inviteeUids": ["event-invitee"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    r = requests.post(
        _url(f"/events/{event_id}/rsvp"),
        json={"status": "accepted"},
        headers=_headers("event-invitee"),
    )
    assert r.status_code == 200
    invitees = r.json()["invitees"]
    match = [i for i in invitees if i["uid"] == "event-invitee"]
    assert len(match) == 1
    assert match[0]["status"] == "accepted"


def test_rsvp_decline():
    body = {
        "title": "Decline Test",
        "startTime": "2026-04-01T08:00:00Z",
        "inviteeUids": ["event-invitee"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    r = requests.post(
        _url(f"/events/{event_id}/rsvp"),
        json={"status": "declined"},
        headers=_headers("event-invitee"),
    )
    assert r.status_code == 200
    invitees = r.json()["invitees"]
    match = [i for i in invitees if i["uid"] == "event-invitee"]
    assert match[0]["status"] == "declined"


def test_rsvp_not_invited():
    body = {
        "title": "No Invite",
        "startTime": "2026-04-01T08:00:00Z",
        "inviteeUids": ["event-invitee"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    r = requests.post(
        _url(f"/events/{event_id}/rsvp"),
        json={"status": "accepted"},
        headers=_headers("not-invited-user"),
    )
    assert r.status_code == 403


def test_rsvp_nonexistent_event():
    r = requests.post(
        _url("/events/nonexistent123/rsvp"),
        json={"status": "accepted"},
        headers=_headers("event-invitee"),
    )
    assert r.status_code == 404


def test_rsvp_does_not_affect_other_invitee():
    body = {
        "title": "Multi RSVP",
        "startTime": "2026-04-01T08:00:00Z",
        "inviteeUids": ["event-invitee", "event-invitee2"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    # First invitee accepts
    r = requests.post(
        _url(f"/events/{event_id}/rsvp"),
        json={"status": "accepted"},
        headers=_headers("event-invitee"),
    )
    assert r.status_code == 200
    invitees = r.json()["invitees"]
    other = [i for i in invitees if i["uid"] == "event-invitee2"]
    assert other[0]["status"] == "pending"


# ── Delete ────────────────────────────────────────────────────────────

def test_soft_delete_event():
    body = _base_event()
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    r = requests.delete(_url(f"/events/{event_id}"), headers=_headers())
    assert r.status_code == 204

    r = requests.get(_url(f"/events/{event_id}"), headers=_headers())
    assert r.status_code == 404


def test_cannot_delete_other_users_event():
    body = _base_event()
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    event_id = r.json()["id"]

    r = requests.delete(_url(f"/events/{event_id}"), headers=_headers("other-user"))
    assert r.status_code == 404

    # Original user can still get it
    r = requests.get(_url(f"/events/{event_id}"), headers=_headers())
    assert r.status_code == 200


def test_delete_nonexistent_event():
    r = requests.delete(_url("/events/nonexistent123"), headers=_headers())
    assert r.status_code == 404


# ── Validation ────────────────────────────────────────────────────────

def test_create_missing_title_rejected():
    body = {"startTime": "2026-04-01T08:00:00Z"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_missing_start_time_rejected():
    body = {"title": "No Start"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_empty_title_rejected():
    body = {"title": "", "startTime": "2026-04-01T08:00:00Z"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_title_too_long_rejected():
    body = {"title": "x" * 201, "startTime": "2026-04-01T08:00:00Z"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_title_max_length():
    body = {"title": "x" * 200, "startTime": "2026-04-01T08:00:00Z"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_description_too_long_rejected():
    body = {"title": "Test", "startTime": "2026-04-01T08:00:00Z", "description": "x" * 2001}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_extra_field_rejected():
    body = {"title": "Test", "startTime": "2026-04-01T08:00:00Z", "spam": True}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_invalid_start_time_rejected():
    body = {"title": "Test", "startTime": "not-a-date"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_invalid_rrule_rejected():
    body = {"title": "Test", "startTime": "2026-04-01T08:00:00Z", "rrule": "INVALID"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_valid_rrule():
    body = {"title": "Test", "startTime": "2026-04-01T08:00:00Z", "rrule": "FREQ=DAILY;COUNT=5"}
    r = requests.post(_url("/events"), json=body, headers=_headers())
    assert r.status_code == 201
    assert r.json()["rrule"] == "FREQ=DAILY;COUNT=5"


def test_rsvp_invalid_status_rejected():
    body = {
        "title": "RSVP Val",
        "startTime": "2026-04-01T08:00:00Z",
        "inviteeUids": ["event-invitee"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    event_id = r.json()["id"]

    r = requests.post(
        _url(f"/events/{event_id}/rsvp"),
        json={"status": "pending"},
        headers=_headers("event-invitee"),
    )
    assert r.status_code == 422


def test_rsvp_extra_field_rejected():
    body = {
        "title": "RSVP Val2",
        "startTime": "2026-04-01T08:00:00Z",
        "inviteeUids": ["event-invitee"],
    }
    r = requests.post(_url("/events"), json=body, headers=_headers())
    event_id = r.json()["id"]

    r = requests.post(
        _url(f"/events/{event_id}/rsvp"),
        json={"status": "accepted", "extra": True},
        headers=_headers("event-invitee"),
    )
    assert r.status_code == 422


def test_missing_user_id_header():
    body = _base_event()
    r = requests.post(_url("/events"), json=body)
    assert r.status_code == 422
