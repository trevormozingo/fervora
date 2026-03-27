"""Event CRUD, RSVP, pagination, and DataLoader tests."""
import pytest
from bson import ObjectId

CREATE = """
mutation CreateEvent($input: CreateEventInput!) {
  createEvent(input: $input) { id title startsAt }
}
"""
RSVP = "mutation ($input: RsvpInput!) { rsvpEvent(input: $input) }"
DELETE = "mutation ($id: ID!) { deleteEvent(id: $id) }"
EVENT_Q = """
query ($id: ID!) {
  event(id: $id) {
    id title
    organizer { id username }
    rsvpSummaries { status count }
    viewerRsvp
    rsvps(limit: 5) { rsvps { id status } nextCursor }
  }
}
"""


async def test_create_event_success(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "Morning Run", "startsAt": "2026-06-01T07:00:00Z"}},
                  user_id="uid1")
    assert r.errors is None
    assert r.data["createEvent"]["title"] == "Morning Run"

async def test_create_event_caches_in_redis(gql, make_profile, redis):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "Yoga Class", "startsAt": "2026-06-10T08:00:00Z"}},
                  user_id="uid1")
    eid = r.data["createEvent"]["id"]
    assert await redis.get(f"event:{eid}") is not None

async def test_create_event_organizer_auto_rsvped_going(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "Bike Ride", "startsAt": "2026-07-01T06:00:00Z"}},
                  user_id="uid1")
    eid = r.data["createEvent"]["id"]
    rsvp = await mongo.rsvps.find_one({"eventId": eid, "userId": "uid1"})
    assert rsvp is not None
    assert rsvp["status"] == "going"

async def test_create_event_invites_valid_users_only(gql, make_profile, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    r = await gql(CREATE, {"input": {
        "title": "Track Session",
        "startsAt": "2026-08-01T07:00:00Z",
        "invitedUserIds": ["uid2", "uid_nonexistent"],
    }}, user_id="uid1")
    eid = r.data["createEvent"]["id"]
    rsvp_count = await mongo.rsvps.count_documents({"eventId": eid})
    # organizer (going) + uid2 (maybe) = 2; uid_nonexistent excluded
    assert rsvp_count == 2

async def test_create_event_title_too_long(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(CREATE, {"input": {"title": "x" * 201, "startsAt": "2026-06-01T07:00:00Z"}},
                  user_id="uid1")
    assert r.errors is not None

async def test_create_event_no_profile_rejected(gql):
    r = await gql(CREATE, {"input": {"title": "Ghost Event", "startsAt": "2026-06-01T07:00:00Z"}},
                  user_id="uid_ghost")
    assert r.errors is not None
    assert "profile does not exist" in r.errors[0].message

# ── RSVP ─────────────────────────────────────────────────────────────────────

async def test_rsvp_event_success(gql, make_profile, make_event, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")

    r = await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id="uid2")
    assert r.errors is None
    assert r.data["rsvpEvent"] is True

async def test_rsvp_upsert_changes_status(gql, make_profile, make_event, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")

    await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id="uid2")
    await gql(RSVP, {"input": {"eventId": eid, "status": "maybe"}}, user_id="uid2")

    doc = await mongo.rsvps.find_one({"eventId": eid, "userId": "uid2"})
    assert doc["status"] == "maybe"
    count = await mongo.rsvps.count_documents({"eventId": eid, "userId": "uid2"})
    assert count == 1

async def test_rsvp_invalid_status_rejected(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")
    r = await gql(RSVP, {"input": {"eventId": eid, "status": "dunno"}}, user_id="uid2")
    assert r.errors is not None

async def test_rsvp_deleted_event_rejected(gql, make_profile, make_event, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")
    await mongo.events.update_one({"_id": ObjectId(eid)}, {"$set": {"isDeleted": True}})
    r = await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id="uid2")
    assert r.errors is not None
    assert "does not exist or was deleted" in r.errors[0].message

async def test_rsvp_no_profile_rejected(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    eid = await make_event("uid1")
    r = await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id="uid_ghost")
    assert r.errors is not None

# ── Delete ────────────────────────────────────────────────────────────────────

async def test_delete_event_soft_deletes(gql, make_profile, make_event, mongo):
    await make_profile("uid1", "alice")
    eid = await make_event("uid1")
    r = await gql(DELETE, {"id": eid}, user_id="uid1")
    assert r.errors is None
    assert r.data["deleteEvent"] is True
    doc = await mongo.events.find_one({"_id": ObjectId(eid)})
    assert doc["isDeleted"] is True

async def test_delete_event_tombstones_redis(gql, make_profile, make_event, redis):
    await make_profile("uid1", "alice")
    eid = await make_event("uid1")
    await gql(DELETE, {"id": eid}, user_id="uid1")
    assert await redis.get(f"event:{eid}") == "__nil__"

async def test_delete_event_wrong_owner_returns_false(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")
    r = await gql(DELETE, {"id": eid}, user_id="uid2")
    assert r.errors is None
    assert r.data["deleteEvent"] is False

# ── Queries ───────────────────────────────────────────────────────────────────

async def test_event_query(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    eid = await make_event("uid1", title="Group Run")
    r = await gql(EVENT_Q, {"id": eid}, user_id="uid1")
    assert r.errors is None
    assert r.data["event"]["title"] == "Group Run"
    assert r.data["event"]["organizer"]["username"] == "alice"

async def test_event_rsvp_summaries_via_dataloader(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    for i in range(2, 5):
        await make_profile(f"uid{i}", f"user{i}")
    eid = await make_event("uid1")

    await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id="uid2")
    await gql(RSVP, {"input": {"eventId": eid, "status": "maybe"}}, user_id="uid3")
    await gql(RSVP, {"input": {"eventId": eid, "status": "maybe"}}, user_id="uid4")

    r = await gql(EVENT_Q, {"id": eid}, user_id="uid1")
    assert r.errors is None
    summaries = {s["status"]: s["count"] for s in r.data["event"]["rsvpSummaries"]}
    # organizer auto-RSVPed as "going" + uid2 = 2 going, uid3+uid4 = 2 maybe
    assert summaries.get("going", 0) == 2
    assert summaries.get("maybe", 0) == 2

async def test_event_viewer_rsvp_via_dataloader(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")
    await gql(RSVP, {"input": {"eventId": eid, "status": "not_going"}}, user_id="uid2")

    r = await gql(EVENT_Q, {"id": eid}, user_id="uid2")
    assert r.errors is None
    assert r.data["event"]["viewerRsvp"] == "not_going"

async def test_event_viewer_rsvp_none_when_not_rsvped(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid = await make_event("uid1")

    r = await gql(EVENT_Q, {"id": eid}, user_id="uid2")
    assert r.errors is None
    assert r.data["event"]["viewerRsvp"] is None

async def test_event_rsvps_pagination(gql, make_profile, make_event):
    await make_profile("uid1", "alice")
    for i in range(2, 9):
        await make_profile(f"uid{i}", f"user{i}")
    eid = await make_event("uid1")
    for i in range(2, 9):
        await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id=f"uid{i}")

    r = await gql(
        """query ($id: ID!) { event(id: $id) { rsvps(limit: 3) { rsvps { id } nextCursor } } }""",
        {"id": eid}, user_id="uid1",
    )
    assert r.errors is None
    page = r.data["event"]["rsvps"]
    assert len(page["rsvps"]) == 3
    assert page["nextCursor"] is not None

async def test_event_rsvps_filter_by_status(gql, make_profile, make_event, mongo):
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    await make_profile("uid3", "carol")
    eid = await make_event("uid1")
    await gql(RSVP, {"input": {"eventId": eid, "status": "going"}}, user_id="uid2")
    await gql(RSVP, {"input": {"eventId": eid, "status": "maybe"}}, user_id="uid3")

    r = await gql(
        """query ($id: ID!) { event(id: $id) { rsvps(limit: 50, status: "going") { rsvps { id status } } } }""",
        {"id": eid}, user_id="uid1",
    )
    assert r.errors is None
    for rsvp in r.data["event"]["rsvps"]["rsvps"]:
        assert rsvp["status"] == "going"

async def test_two_events_dataloader_batch(gql, make_profile, make_event):
    """Both events' rsvpSummaries and viewerRsvp resolve correctly in one execution."""
    await make_profile("uid1", "alice")
    await make_profile("uid2", "bob")
    eid1 = await make_event("uid1", title="Event A")
    eid2 = await make_event("uid1", title="Event B")
    await gql(RSVP, {"input": {"eventId": eid1, "status": "going"}}, user_id="uid2")
    await gql(RSVP, {"input": {"eventId": eid2, "status": "maybe"}}, user_id="uid2")

    r = await gql(f"""
        query {{
          e1: event(id: "{eid1}") {{ viewerRsvp rsvpSummaries {{ status count }} }}
          e2: event(id: "{eid2}") {{ viewerRsvp rsvpSummaries {{ status count }} }}
        }}
    """, user_id="uid2")
    assert r.errors is None
    assert r.data["e1"]["viewerRsvp"] == "going"
    assert r.data["e2"]["viewerRsvp"] == "maybe"
