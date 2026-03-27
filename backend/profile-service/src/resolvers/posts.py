from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
import strawberry
from strawberry.types import Info
from strawberry.file_uploads import Upload

from pymongo import ReturnDocument
from ..types.post import Post, MediaItem, Workout, BodyMetrics, CreatePostInput, UpdatePostInput
from ..cache import cached_or_fetch, set_cached, _post_key, TTL
from ..storage import upload_image

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
        post_id = str(id)
        try:
            oid = ObjectId(post_id)
        except InvalidId:
            raise ValueError("invalid post id")
        doc = await cached_or_fetch(_post_key(post_id), db.posts, oid, redis)
        if doc is None:
            raise ValueError("post not found")
        return _post_from_doc(doc)


# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class PostMutation:

    @strawberry.mutation
    async def create_post(self, info: Info, input: CreatePostInput) -> Post:
        """Create a new post for the authenticated user."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        if not await db.profiles.find_one({"_id": user_id, "isDeleted": {"$ne": True}}, {"_id": 1}):
            raise ValueError("cannot publish post: profile does not exist or was deleted")

        if input.storage_post_id:
            existing = await db.posts.find_one({"authorUid": user_id, "storagePostId": input.storage_post_id})
            if existing:
                existing["_id"] = str(existing["_id"])
                return _post_from_doc(existing)

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
            "isDeleted": False
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
    async def update_post(self, info: Info, input: UpdatePostInput) -> Post:
        """Update an existing post (only the author can update)."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        try:
            oid = ObjectId(str(input.id))
        except InvalidId:
            raise ValueError("invalid post id")

        patch = {}

        if input.title is not strawberry.UNSET:
            patch["title"] = input.title
        if input.body is not strawberry.UNSET:
            patch["body"] = input.body

        if input.media is not strawberry.UNSET:
            if input.media is not None and len(input.media) > 10:
                raise ValueError("media may contain at most 10 items")
            patch["media"] = [{"url": m.url, "mimeType": m.mime_type} for m in input.media] if input.media else None

        if input.workout is not strawberry.UNSET:
            if input.workout:
                w = input.workout
                patch["workout"] = {
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
            else:
                patch["workout"] = None

        if input.body_metrics is not strawberry.UNSET:
            if input.body_metrics:
                bm = input.body_metrics
                patch["bodyMetrics"] = {
                    "weightLbs": bm.weight_lbs,
                    "bodyFatPercentage": bm.body_fat_percentage,
                    "restingHeartRate": bm.resting_heart_rate,
                    "leanBodyMassLbs": bm.lean_body_mass_lbs,
                }
            else:
                patch["bodyMetrics"] = None

        if not patch:
            raise ValueError("no valid fields provided for update")

        updated_doc = await db.posts.find_one_and_update(
            {"_id": oid, "authorUid": user_id, "isDeleted": {"$ne": True}},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )

        if not updated_doc:
            raise ValueError("post not found or unauthorized")

        updated_doc["_id"] = str(updated_doc["_id"])
        await set_cached(redis, _post_key(updated_doc["_id"]), updated_doc)

        return _post_from_doc(updated_doc)

    @strawberry.mutation
    async def delete_post(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a post (only the author can delete their own post)."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")

        try:
            oid = ObjectId(str(id))
        except InvalidId:
            raise ValueError("invalid post id")

        result = await db.posts.update_one(
            {"_id": oid, "authorUid": user_id},
            {"$set": {"isDeleted": True}},
        )

        if result.modified_count > 0:
            await redis.setex(_post_key(str(id)), TTL, "__nil__")
            return True

        return False

    @strawberry.mutation
    async def upload_post_media(self, info: Info, file: Upload) -> str:
        """Upload a media file for use in a post and return its public URL."""
        user_id = info.context.get("user_id")
        if not user_id:
            raise ValueError("authentication required")
        return await upload_image(file, f"posts/{user_id}")
