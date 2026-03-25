from __future__ import annotations
from typing import Annotated, Optional, TYPE_CHECKING
from datetime import date
import re
import strawberry
from strawberry.types import Info

if TYPE_CHECKING:
    from .post import Post

# ── Scalars ───────────────────────────────────────────────────────────

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_MIN_AGE = 18

VALID_INTERESTS = {
    "Weightlifting", "Powerlifting", "Bodybuilding", "Strongman", "Olympic Lifting",
    "Calisthenics", "CrossFit", "Running", "Cycling", "Swimming", "Rowing",
    "Jump Rope", "Stair Climbing", "Boxing", "MMA", "Wrestling", "Jiu-Jitsu",
    "Muay Thai", "Yoga", "Pilates", "Stretching", "Mobility Work", "Hiking",
    "Rock Climbing", "Trail Running", "Obstacle Course Racing", "Functional Fitness",
    "Basketball", "Soccer", "Tennis", "Volleyball", "Pickleball", "Flag Football",
}

VALID_FITNESS_LEVELS = {"novice", "intermediate", "experienced", "pro", "olympian"}

def _parse_username(value: str) -> str:
    if not (3 <= len(value) <= 30):
        raise ValueError("username must be between 3 and 30 characters")
    if not _USERNAME_RE.match(value):
        raise ValueError("username may only contain letters, numbers, underscores, and hyphens")
    return value


def _parse_display_name(value: str) -> str:
    if not (1 <= len(value) <= 100):
        raise ValueError("displayName must be between 1 and 100 characters")
    return value


def _parse_bio(value: str) -> str:
    if len(value) > 500:
        raise ValueError("bio must be 500 characters or fewer")
    return value


def _parse_fitness_level(value: str) -> str:
    if value not in VALID_FITNESS_LEVELS:
        raise ValueError(f"fitnessLevel must be one of {sorted(VALID_FITNESS_LEVELS)}")
    return value


def _parse_interest(value: str) -> str:
    if value not in VALID_INTERESTS:
        raise ValueError(f"'{value}' is not a valid interest")
    return value


def _parse_interests_list(value: list) -> list:
    if len(value) > 20:
        raise ValueError("interests may contain at most 20 items")
    return [_parse_interest(v) for v in value]


def _parse_coordinates(value: list) -> list:
    if len(value) != 2:
        raise ValueError("coordinates must contain exactly two values: [longitude, latitude]")
    lon, lat = value
    if not (-180 <= lon <= 180):
        raise ValueError("longitude must be between -180 and 180")
    if not (-90 <= lat <= 90):
        raise ValueError("latitude must be between -90 and 90")
    return value


def _parse_birthday(value: str) -> date:
    try:
        birthday = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("birthday must be a valid date in YYYY-MM-DD format")
    today = date.today()
    age = today.year - birthday.year - (
        (today.month, today.day) < (birthday.month, birthday.day)
    )
    if age < _MIN_AGE:
        raise ValueError(f"must be at least {_MIN_AGE} years old")
    return birthday


Username = strawberry.scalar(str, name="Username", parse_value=_parse_username)
DisplayName = strawberry.scalar(str, name="DisplayName", parse_value=_parse_display_name)
Bio = strawberry.scalar(str, name="Bio", parse_value=_parse_bio)
Birthday = strawberry.scalar(date, name="Birthday", parse_value=_parse_birthday, serialize=lambda v: v.isoformat())
FitnessLevel = strawberry.scalar(str, name="FitnessLevel", parse_value=_parse_fitness_level)
Interest = strawberry.scalar(str, name="Interest", parse_value=_parse_interest)
InterestsList = strawberry.scalar(list, name="InterestsList", parse_value=_parse_interests_list)
GeoCoordinates = strawberry.scalar(list, name="GeoCoordinates", parse_value=_parse_coordinates)


@strawberry.type
class Location:
    coordinates: list[float]
    label: Optional[str] = None


@strawberry.input
class LocationInput:
    coordinates: GeoCoordinates
    label: Optional[str] = None


@strawberry.type
class Profile:
    id: strawberry.ID
    username: str
    display_name: str
    bio: Optional[str]
    birthday: Optional[date]
    profile_photo: Optional[str]
    location: Optional[Location]
    interests: Optional[list[str]]
    fitness_level: Optional[str]

    @strawberry.field
    async def posts(
        self,
        info: Info,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> list[Annotated["Post", strawberry.lazy(".post")]]:
        from bson import ObjectId
        from bson.errors import InvalidId
        db = info.context["db"]
        post_loader = info.context["post_loader"]
        query: dict = {"authorUid": str(self.id), "isDeleted": {"$ne": True}}
        if cursor:
            try:
                query["_id"] = {"$lt": ObjectId(cursor)}
            except InvalidId:
                raise ValueError("invalid cursor")
        docs = await db.posts.find(query, {"_id": 1}).sort("_id", -1).limit(limit).to_list(length=limit)
        if not docs:
            return []
        post_ids = [str(doc["_id"]) for doc in docs]
        hydrated = await post_loader.load_many(post_ids)
        return [p for p in hydrated if p is not None]

@strawberry.input
class CreateProfileInput:
    username: Username
    display_name: DisplayName
    profile_photo: str
    birthday: Birthday
    bio: Optional[Bio] = None
    location: Optional[LocationInput] = None
    interests: Optional[InterestsList] = None
    fitness_level: Optional[FitnessLevel] = None


@strawberry.input
class UpdateProfileInput:
    display_name: Optional[DisplayName] = strawberry.UNSET
    bio: Optional[Bio] = strawberry.UNSET
    birthday: Optional[Birthday] = strawberry.UNSET
    profile_photo: Optional[str] = strawberry.UNSET
    location: Optional[LocationInput] = strawberry.UNSET
    interests: Optional[InterestsList] = strawberry.UNSET
    fitness_level: Optional[FitnessLevel] = strawberry.UNSET
