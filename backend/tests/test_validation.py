"""Validation tests — exercises every schema constraint for create and update."""

import os

import pymongo
import requests

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8000")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fervora_test")

_uid_counter = 0


def _url(path: str) -> str:
    return f"{SERVICE_URL}{path}"


def _unique_uid() -> str:
    global _uid_counter
    _uid_counter += 1
    return f"val-user-{_uid_counter}"


def _headers(uid: str | None = None) -> dict:
    return {"X-User-Id": uid or _unique_uid()}


def _valid_create(**overrides) -> dict:
    body = {
        "username": f"user{_uid_counter + 1}",
        "displayName": "Valid User",
        "profilePhoto": "https://example.com/photo.jpg",
        "birthday": "1998-05-14",
    }
    body.update(overrides)
    return body


def setup_module():
    client = pymongo.MongoClient(MONGO_URI)
    client[MONGO_DB].profiles.delete_many({})
    client.close()


def _create_profile_for_update() -> str:
    """Helper: create a profile and return its uid."""
    uid = _unique_uid()
    body = _valid_create(username=f"upd{uid.replace('-', '')}")
    r = requests.post(_url("/profiles"), json=body, headers={"X-User-Id": uid})
    assert r.status_code == 201
    return uid


# ═══════════════════════════════════════════════════════════════════════
# CREATE — required fields
# ═══════════════════════════════════════════════════════════════════════

def test_create_missing_username():
    body = _valid_create()
    del body["username"]
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_missing_display_name():
    body = _valid_create()
    del body["displayName"]
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_missing_profile_photo():
    body = _valid_create()
    del body["profilePhoto"]
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_missing_birthday():
    body = _valid_create()
    del body["birthday"]
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_all_required_missing():
    r = requests.post(_url("/profiles"), json={}, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — username constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_username_too_short():
    body = _valid_create(username="ab")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_username_min_length():
    body = _valid_create(username="abc")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_username_max_length():
    body = _valid_create(username="a" * 30)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_username_too_long():
    body = _valid_create(username="a" * 31)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_username_invalid_chars_spaces():
    body = _valid_create(username="bad user")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_username_invalid_chars_special():
    body = _valid_create(username="bad@user!")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_username_valid_hyphens_underscores():
    body = _valid_create(username="valid_user-1")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_username_wrong_type():
    body = _valid_create(username=123)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — displayName constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_display_name_empty():
    body = _valid_create(displayName="")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_display_name_too_long():
    body = _valid_create(displayName="x" * 101)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_display_name_max_length():
    body = _valid_create(displayName="x" * 100)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


# ═══════════════════════════════════════════════════════════════════════
# CREATE — bio constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_bio_null():
    body = _valid_create(bio=None)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_bio_valid():
    body = _valid_create(bio="Just a regular bio")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_bio_too_long():
    body = _valid_create(bio="x" * 501)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_bio_max_length():
    body = _valid_create(bio="x" * 500)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_bio_wrong_type():
    body = _valid_create(bio=42)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — birthday / age constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_birthday_null():
    body = _valid_create(birthday=None)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    # birthday is required in create schema, null should fail
    assert r.status_code == 422


def test_create_birthday_underage():
    body = _valid_create(birthday="2015-06-01")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_birthday_exactly_18():
    # Someone who turns 18 today
    from datetime import date, timedelta
    today = date.today()
    eighteenth = today.replace(year=today.year - 18)
    body = _valid_create(birthday=eighteenth.isoformat())
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_birthday_invalid_format():
    body = _valid_create(birthday="14-05-1998")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_birthday_wrong_type():
    body = _valid_create(birthday=19980514)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — profilePhoto constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_profile_photo_null():
    body = _valid_create(profilePhoto=None)
    # required field, null should fail
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_profile_photo_not_uri():
    body = _valid_create(profilePhoto="not a url")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_profile_photo_wrong_type():
    body = _valid_create(profilePhoto=123)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — fitnessLevel constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_fitness_level_valid_values():
    for level in ["novice", "intermediate", "experienced", "pro", "olympian"]:
        body = _valid_create(fitnessLevel=level)
        r = requests.post(_url("/profiles"), json=body, headers=_headers())
        assert r.status_code == 201, f"Failed for fitnessLevel={level}"


def test_create_fitness_level_null():
    body = _valid_create(fitnessLevel=None)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_fitness_level_invalid():
    body = _valid_create(fitnessLevel="godlike")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — interests constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_interests_valid():
    body = _valid_create(interests=["Weightlifting", "Running", "Yoga"])
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_interests_null():
    body = _valid_create(interests=None)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_interests_empty_array():
    body = _valid_create(interests=[])
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_interests_invalid_value():
    body = _valid_create(interests=["Weightlifting", "NotASport"])
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_interests_too_many():
    # maxItems is 20
    body = _valid_create(interests=["Weightlifting"] * 21)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_interests_max_items():
    all_interests = [
        "Weightlifting", "Powerlifting", "Bodybuilding", "Strongman",
        "Olympic Lifting", "Calisthenics", "CrossFit", "Running",
        "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing",
        "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai",
        "Yoga", "Pilates",
    ]
    body = _valid_create(interests=all_interests)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_interests_wrong_type():
    body = _valid_create(interests="Weightlifting")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — location constraints
# ═══════════════════════════════════════════════════════════════════════

def test_create_location_valid():
    body = _valid_create(location={
        "type": "Point",
        "coordinates": [-73.935242, 40.730610],
        "label": "New York",
    })
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_location_null():
    body = _valid_create(location=None)
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


def test_create_location_missing_coordinates():
    body = _valid_create(location={"type": "Point"})
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_location_missing_type():
    body = _valid_create(location={"coordinates": [-73.9, 40.7]})
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_location_invalid_type():
    body = _valid_create(location={
        "type": "Polygon",
        "coordinates": [-73.9, 40.7],
    })
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_location_too_few_coordinates():
    body = _valid_create(location={"type": "Point", "coordinates": [-73.9]})
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_location_too_many_coordinates():
    body = _valid_create(location={"type": "Point", "coordinates": [-73.9, 40.7, 100]})
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_location_coordinates_wrong_type():
    body = _valid_create(location={"type": "Point", "coordinates": ["a", "b"]})
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_location_without_label():
    body = _valid_create(location={"type": "Point", "coordinates": [-73.9, 40.7]})
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 201


# ═══════════════════════════════════════════════════════════════════════
# CREATE — additionalProperties
# ═══════════════════════════════════════════════════════════════════════

def test_create_extra_field_rejected():
    body = _valid_create(hackerField="pwned")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


def test_create_id_field_rejected():
    body = _valid_create(id="injected-id")
    r = requests.post(_url("/profiles"), json=body, headers=_headers())
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# CREATE — missing header
# ═══════════════════════════════════════════════════════════════════════

def test_create_missing_user_id_header():
    body = _valid_create()
    r = requests.post(_url("/profiles"), json=body)
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# UPDATE — field constraints (same rules as create)
# ═══════════════════════════════════════════════════════════════════════

def test_update_empty_body():
    uid = _create_profile_for_update()
    r = requests.patch(_url("/profiles/me"), json={}, headers={"X-User-Id": uid})
    assert r.status_code == 422


def test_update_extra_field_rejected():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"hackerField": "pwned"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_username_not_allowed():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"username": "newname"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_display_name_empty():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"displayName": ""},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_display_name_too_long():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"displayName": "x" * 101},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_bio_too_long():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"bio": "x" * 501},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_bio_null():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"bio": None},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200


def test_update_fitness_level_invalid():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"fitnessLevel": "godlike"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_fitness_level_valid():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"fitnessLevel": "pro"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["fitnessLevel"] == "pro"


def test_update_interests_invalid_value():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"interests": ["NotASport"]},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_interests_too_many():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"interests": ["Weightlifting"] * 21},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_location_invalid():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"location": {"type": "Polygon", "coordinates": [1, 2]}},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_location_valid():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"location": {"type": "Point", "coordinates": [-73.9, 40.7], "label": "NYC"}},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["location"]["label"] == "NYC"


def test_update_birthday_underage():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"birthday": "2015-06-01"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_birthday_valid():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"birthday": "1990-01-01"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["birthday"] == "1990-01-01"


def test_update_profile_photo_not_uri():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"profilePhoto": "not a url"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 422


def test_update_profile_photo_valid():
    uid = _create_profile_for_update()
    r = requests.patch(
        _url("/profiles/me"),
        json={"profilePhoto": "https://example.com/new.jpg"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["profilePhoto"] == "https://example.com/new.jpg"


def test_update_missing_user_id_header():
    r = requests.patch(_url("/profiles/me"), json={"bio": "test"})
    assert r.status_code == 422
