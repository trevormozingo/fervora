"""Profile routes."""

from datetime import date, datetime

from fastapi import APIRouter, Header, HTTPException
from pymongo.errors import DuplicateKeyError

from .database import (
    create_profile,
    get_db,
    soft_delete_profile,
    update_profile,
)
from .cache import get_profile, get_profile_counts, invalidate_profile
from .schema import get_fields, validate

router = APIRouter(prefix="/profiles", tags=["profiles"])

MIN_AGE = 18


def _assert_min_age(birthday: str | None) -> None:
    if not birthday:
        return
    try:
        dob = datetime.strptime(birthday, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid birthday format")
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < MIN_AGE:
        raise HTTPException(status_code=422, detail=f"Must be at least {MIN_AGE} years old")


_RESPONSE_FIELDS = None


def _get_response_fields() -> list[str]:
    global _RESPONSE_FIELDS
    if _RESPONSE_FIELDS is None:
        _RESPONSE_FIELDS = get_fields("profile_response")
    return _RESPONSE_FIELDS


async def _to_response(doc: dict) -> dict:
    """Build a response dict from a DB document using the response schema fields."""
    counts = await get_profile_counts(doc["_id"], get_db())
    out: dict = {}
    for field in _get_response_fields():
        if field == "id":
            out["id"] = doc["_id"]
        elif field in counts:
            out[field] = counts[field]
        else:
            out[field] = doc.get(field)
    return out


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create(request_body: dict, x_user_id: str = Header(...)):
    errors = validate("profile_create", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    _assert_min_age(request_body.get("birthday"))

    try:
        doc = await create_profile(x_user_id, request_body)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Username taken")

    await invalidate_profile(x_user_id)
    return await _to_response(doc)


@router.get("/me")
async def get_me(x_user_id: str = Header(...)):
    doc = await get_profile(x_user_id, get_db())
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return await _to_response(doc)


@router.get("/{id}")
async def get_by_id(id: str, x_user_id: str = Header(...)):
    doc = await get_profile(id, get_db())
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return await _to_response(doc)


@router.patch("/me")
async def update(request_body: dict, x_user_id: str = Header(...)):
    errors = validate("profile_update", request_body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    _assert_min_age(request_body.get("birthday"))

    doc = await update_profile(x_user_id, request_body)
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    await invalidate_profile(x_user_id)
    return await _to_response(doc)


@router.delete("/me", status_code=204)
async def delete(x_user_id: str = Header(...)):
    deleted = await soft_delete_profile(x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    await invalidate_profile(x_user_id)
