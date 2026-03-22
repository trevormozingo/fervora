from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
import strawberry
from strawberry.types import Info

from ..types.post import Post, MediaItem, Workout, BodyMetrics, CreatePostInput
from ..cache import get_cached, set_cached, invalidate, _post_key


# ── Helpers ───────────────────────────────────────────────────────────────────

def _post_from_doc(doc: dict) -> Post:
    media = None
    if doc.get("media"):
        media = [MediaItem(url=m["url"], mime_type=m["mimeType"]) for m in doc["media"]]

    workout = None
    if doc.get("workout"):
        w = doc["workout"]
        workout = Workout(
            activity_type=w["activityType"],
            duration_seconds=w.get("durationSeconds"),
            calories_burned=w.get("caloriesBurned"),
            distance_miles=w.get("distanceMiles"),
            avg_heart_rate=w.get("avgHeartRate"),
            max_heart_rate=w.get("maxHeartRate"),
            elevation_feet=w.get("elevationFeet"),
            start_date=w.get("startDate"),
            end_date=w.get("endDate"),
        )

    body_metrics = None
    if doc.get("bodyMetrics"):
        bm = doc["bodyMetrics"]
        body_metrics = BodyMetrics(
            weight_lbs=bm.get("weightLbs"),
            body_fat_percentage=bm.get("bodyFatPercentage"),
            resting_heart_rate=bm.get("restingHeartRate"),
            lean_body_mass_lbs=bm.get("leanBodyMassLbs"),
        )

    return Post(
        id=strawberry.ID(str(doc["_id"])),
        author_uid=doc["authorUid"],
        title=doc.get("title"),
        body=doc.get("body"),
        media=media,
        workout=workout,
        body_metrics=body_metrics,
        health_kit_id=doc.get("healthKitId"),
        created_at=doc["createdAt"],
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@strawberry.type
class PostQuery:

    @strawberry.field
    async def post(self, info: Info, id: strawberry.ID) -> Post:
        """Get a single post by ID."""
        db = info.context["db"]
        redis = info.context["redis"]
        try:
            oid = ObjectId(str(id))
        except InvalidId:
            raise ValueError("invalid post id")
        key = _post_key(str(id))
        doc = await get_cached(redis, key)
        if not doc:
            doc = await db.posts.find_one({"_id": oid})
            if not doc:
                raise ValueError("post not found")
            doc["_id"] = str(doc["_id"])
            await set_cached(redis, key, doc)
        return _post_from_doc(doc)

    @strawberry.field
    async def user_posts(
        self,
        info: Info,
        user_id: strawberry.ID,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> list[Post]:
        """Get posts by a user, newest first, with cursor-based pagination."""
        db = info.context["db"]
        query: dict = {"authorUid": str(user_id)}
        if cursor:
            try:
                query["_id"] = {"$lt": ObjectId(cursor)}
            except InvalidId:
                raise ValueError("invalid cursor")
        db_cursor = db.posts.find(query).sort("_id", -1).limit(limit)
        docs = await db_cursor.to_list(length=limit)
        return [_post_from_doc({**d, "_id": str(d["_id"])}) for d in docs]



# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class PostMutation:

    @strawberry.mutation
    async def create_post(self, info: Info, input: CreatePostInput) -> Post:
        """Create a new post for the authenticated user."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        # At least one content field must be present
        if not any([input.title, input.body, input.media, input.workout, input.body_metrics]):
            raise ValueError("post must contain at least one content field")

        doc = {
            "authorUid": user_id,
            "title": input.title,
            "body": input.body,
            "healthKitId": input.health_kit_id,
            "storagePostId": input.storage_post_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

        if input.media:
            if len(input.media) > 10:
                raise ValueError("media may contain at most 10 items")
            doc["media"] = [{"url": m.url, "mimeType": m.mime_type} for m in input.media]

        if input.workout:
            w = input.workout
            doc["workout"] = {
                "activityType": w.activity_type,
                "durationSeconds": w.duration_seconds,
                "caloriesBurned": w.calories_burned,
                "distanceMiles": w.distance_miles,
                "avgHeartRate": w.avg_heart_rate,
                "maxHeartRate": w.max_heart_rate,
                "elevationFeet": w.elevation_feet,
                "startDate": w.start_date,
                "endDate": w.end_date,
            }

        if input.body_metrics:
            bm = input.body_metrics
            if not any([bm.weight_lbs, bm.body_fat_percentage, bm.resting_heart_rate, bm.lean_body_mass_lbs]):
                raise ValueError("bodyMetrics must contain at least one field")
            doc["bodyMetrics"] = {
                "weightLbs": bm.weight_lbs,
                "bodyFatPercentage": bm.body_fat_percentage,
                "restingHeartRate": bm.resting_heart_rate,
                "leanBodyMassLbs": bm.lean_body_mass_lbs,
            }

        result = await db.posts.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        await set_cached(redis, _post_key(doc["_id"]), doc)

        return _post_from_doc(doc)

    @strawberry.mutation
    async def delete_post(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a post (only the author can delete their own post)."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        result = await db.posts.delete_one({"_id": ObjectId(str(id)), "authorUid": user_id})

        if result.deleted_count > 0:
            await invalidate(redis, _post_key(str(id)))
            return True

        return False
