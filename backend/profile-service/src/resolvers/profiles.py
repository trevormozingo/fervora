from datetime import datetime, timezone, date
from pymongo import ReturnDocument
import strawberry
from strawberry.types import Info

from ..types.profile import Profile, Location, CreateProfileInput, UpdateProfileInput
from ..cache import cached_or_fetch, set_cached, _profile_key, TTL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _profile_from_doc(doc: dict) -> Profile:
    location = None
    if doc.get("location"):
        loc = doc["location"]
        location = Location(coordinates=loc["coordinates"], label=loc.get("label"))
    raw_birthday = doc.get("birthday")
    return Profile(
        id=strawberry.ID(str(doc["_id"])),
        username=doc["username"],
        display_name=doc["displayName"],
        bio=doc.get("bio"),
        birthday=date.fromisoformat(raw_birthday) if raw_birthday else None,
        profile_photo=doc.get("profilePhoto"),
        location=location,
        interests=doc.get("interests"),
        fitness_level=doc.get("fitnessLevel"),
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@strawberry.type
class ProfileQuery:

    @strawberry.field
    async def me(self, info: Info) -> Profile:
        """Get the authenticated user's own profile."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]
        doc = await cached_or_fetch(_profile_key(user_id), db.profiles, user_id, redis)
        if doc is None:
            raise ValueError("profile not found")
        return _profile_from_doc(doc)

    @strawberry.field
    async def profile(self, info: Info, id: strawberry.ID) -> Profile:
        """Get any user's profile by ID."""
        db = info.context["db"]
        redis = info.context["redis"]
        doc = await cached_or_fetch(_profile_key(str(id)), db.profiles, str(id), redis)
        if doc is None:
            raise ValueError("profile not found")
        return _profile_from_doc(doc)


# ── Mutation ──────────────────────────────────────────────────────────────────

@strawberry.type
class ProfileMutation:

    @strawberry.mutation
    async def create_profile(self, info: Info, input: CreateProfileInput) -> Profile:
        """Create a profile for the authenticated user and cache it."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        doc = {
            "_id": user_id,
            "username": input.username,
            "displayName": input.display_name,
            "profilePhoto": input.profile_photo,
            "birthday": input.birthday.isoformat() if input.birthday else None,
            "bio": input.bio,
            "fitnessLevel": input.fitness_level,
            "interests": input.interests or [],
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "isDeleted": False,
        }

        if input.location:
            doc["location"] = {
                "type": "Point",
                "coordinates": input.location.coordinates,
                "label": input.location.label,
            }

        await db.profiles.insert_one(doc)
        await set_cached(redis, _profile_key(user_id), doc)

        return _profile_from_doc(doc)

    @strawberry.mutation
    async def update_profile(self, info: Info, input: UpdateProfileInput) -> Profile:
        """Update the authenticated user's profile and refresh the cache."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        patch = {}

        if input.display_name is not strawberry.UNSET:
            patch["displayName"] = input.display_name
        if input.bio is not strawberry.UNSET:
            patch["bio"] = input.bio
        if input.profile_photo is not strawberry.UNSET:
            patch["profilePhoto"] = input.profile_photo
        if input.birthday is not strawberry.UNSET:
            patch["birthday"] = input.birthday.isoformat() if input.birthday else None
        if input.fitness_level is not strawberry.UNSET:
            patch["fitnessLevel"] = input.fitness_level
        if input.interests is not strawberry.UNSET:
            patch["interests"] = input.interests
        if input.location is not strawberry.UNSET:
            patch["location"] = (
                {"type": "Point", "coordinates": input.location.coordinates, "label": input.location.label}
                if input.location else None
            )

        if not patch:
            raise ValueError("no valid fields provided for update")

        updated_doc = await db.profiles.find_one_and_update(
            {"_id": user_id, "isDeleted": {"$ne": True}},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )

        if not updated_doc:
            raise ValueError("profile not found or deleted")

        await set_cached(redis, _profile_key(user_id), updated_doc)

        return _profile_from_doc(updated_doc)

    @strawberry.mutation
    async def delete_profile(self, info: Info) -> bool:
        """Soft-delete the authenticated user's profile and purge the cache."""
        db = info.context["db"]
        redis = info.context["redis"]
        user_id = info.context["user_id"]

        result = await db.profiles.update_one(
            {"_id": user_id},
            {"$set": {"isDeleted": True}},
        )

        if result.modified_count > 0:
            await redis.setex(_profile_key(user_id), TTL, "__nil__")
            return True

        return False
