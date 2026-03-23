from __future__ import annotations
from typing import Optional
import strawberry
from strawberry.types import Info
from .profile import Profile
from .comment import Comment


VALID_ACTIVITY_TYPES = {
    "running", "cycling", "swimming", "weightlifting", "crossfit",
    "yoga", "pilates", "hiking", "rowing", "boxing", "martial_arts",
    "climbing", "dance", "stretching", "cardio", "hiit", "walking",
    "sports", "other",
}


def _parse_title(value: str) -> str:
    if not (1 <= len(value) <= 200):
        raise ValueError("title must be between 1 and 200 characters")
    return value


def _parse_post_body(value: str) -> str:
    if not (1 <= len(value) <= 5000):
        raise ValueError("body must be between 1 and 5000 characters")
    return value


def _parse_activity_type(value: str) -> str:
    if value not in VALID_ACTIVITY_TYPES:
        raise ValueError(f"activityType must be one of {sorted(VALID_ACTIVITY_TYPES)}")
    return value


PostTitle = strawberry.scalar(str, name="PostTitle", parse_value=_parse_title)
PostBody = strawberry.scalar(str, name="PostBody", parse_value=_parse_post_body)
ActivityType = strawberry.scalar(str, name="ActivityType", parse_value=_parse_activity_type)


# ── Output types ──────────────────────────────────────────────────────────────

@strawberry.type
class MediaItem:
    url: str
    mime_type: str


@strawberry.type
class Workout:
    activity_type: str
    duration_seconds: Optional[int] = None
    calories_burned: Optional[float] = None
    distance_miles: Optional[float] = None
    avg_heart_rate: Optional[float] = None
    max_heart_rate: Optional[float] = None
    elevation_feet: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@strawberry.type
class BodyMetrics:
    weight_lbs: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    lean_body_mass_lbs: Optional[float] = None


@strawberry.type
class Post:
    id: strawberry.ID
    author_uid: strawberry.Private[str]
    title: Optional[str] = None
    body: Optional[str] = None
    media: Optional[list[MediaItem]] = None
    workout: Optional[Workout] = None
    body_metrics: Optional[BodyMetrics] = None
    health_kit_id: Optional[str] = None
    created_at: str

    @strawberry.field
    async def author(self, info: Info) -> Optional[Profile]:
        return await info.context["profile_loader"].load(self.author_uid)

    @strawberry.field
    async def comments(
        self,
        info: Info,
        limit: int = 10,
        cursor: Optional[str] = None,
    ) -> list[Comment]:
        from ..resolvers.comments import _comment_from_doc
        from bson import ObjectId
        from bson.errors import InvalidId
        db = info.context["db"]
        query: dict = {"postId": str(self.id), "isDeleted": {"$ne": True}}
        if cursor:
            try:
                query["_id"] = {"$gt": ObjectId(cursor)}
            except InvalidId:
                raise ValueError("invalid cursor")
        docs = await db.comments.find(query).sort("_id", 1).limit(limit).to_list(length=limit)
        return [_comment_from_doc({**d, "_id": str(d["_id"])}) for d in docs]


# ── Input types ───────────────────────────────────────────────────────────────

@strawberry.input
class MediaItemInput:
    url: str
    mime_type: str


@strawberry.input
class WorkoutInput:
    activity_type: ActivityType
    duration_seconds: Optional[int] = None
    calories_burned: Optional[float] = None
    distance_miles: Optional[float] = None
    avg_heart_rate: Optional[float] = None
    max_heart_rate: Optional[float] = None
    elevation_feet: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@strawberry.input
class BodyMetricsInput:
    weight_lbs: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    lean_body_mass_lbs: Optional[float] = None


@strawberry.input
class CreatePostInput:
    title: Optional[PostTitle] = None
    body: Optional[PostBody] = None
    media: Optional[list[MediaItemInput]] = None
    workout: Optional[WorkoutInput] = None
    body_metrics: Optional[BodyMetricsInput] = None
    health_kit_id: Optional[str] = None
    storage_post_id: Optional[str] = None
