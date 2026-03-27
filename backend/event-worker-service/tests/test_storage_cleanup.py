"""
Tests for Firebase Storage cleanup in the event-worker handlers.

handle_post_deleted  → deletes every media blob attached to the post
handle_profile_deleted → deletes the profile photo blob
"""
from __future__ import annotations

import pytest
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch

from src.handlers import handle_post_deleted, handle_profile_deleted


# ─────────────────────────────────────────────────────────────────────────────
# handle_post_deleted — storage cleanup
# ─────────────────────────────────────────────────────────────────────────────

async def test_handle_post_deleted_deletes_media_blobs(mongo, redis):
    """Media URLs on the post must be deleted from Firebase Storage."""
    MEDIA_URL = (
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
        "/o/posts%2Fuid1%2Fsome-uuid.jpg?alt=media"
    )
    post_id = str(ObjectId())
    await mongo.posts.insert_one({
        "_id": ObjectId(post_id),
        "authorUid": "uid1",
        "title": "My post",
        "media": [{"url": MEDIA_URL, "mimeType": "image/jpeg"}],
        "isDeleted": True,
    })

    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_post_deleted({"postId": post_id, "authorUid": "uid1"}, mongo, redis)

    mock_delete.assert_called_once_with(MEDIA_URL)


async def test_handle_post_deleted_multiple_media_blobs(mongo, redis):
    """All media items on the post are individually deleted."""
    urls = [
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com/o/posts%2Fuid1%2Fa.jpg?alt=media",
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com/o/posts%2Fuid1%2Fb.jpg?alt=media",
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com/o/posts%2Fuid1%2Fc.jpg?alt=media",
    ]
    post_id = str(ObjectId())
    await mongo.posts.insert_one({
        "_id": ObjectId(post_id),
        "authorUid": "uid1",
        "title": "Gallery post",
        "media": [{"url": u, "mimeType": "image/jpeg"} for u in urls],
        "isDeleted": True,
    })

    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_post_deleted({"postId": post_id, "authorUid": "uid1"}, mongo, redis)

    assert mock_delete.call_count == 3
    called_urls = {c.args[0] for c in mock_delete.call_args_list}
    assert called_urls == set(urls)


async def test_handle_post_deleted_no_media_no_storage_call(mongo, redis):
    """Posts without media must not trigger any storage deletion."""
    post_id = str(ObjectId())
    await mongo.posts.insert_one({
        "_id": ObjectId(post_id),
        "authorUid": "uid1",
        "title": "Text only",
        "isDeleted": True,
    })

    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_post_deleted({"postId": post_id, "authorUid": "uid1"}, mongo, redis)

    mock_delete.assert_not_called()


async def test_handle_post_deleted_missing_post_no_crash(mongo, redis):
    """If the post record is gone, storage cleanup is skipped gracefully."""
    post_id = str(ObjectId())
    # Intentionally do NOT insert a post doc.

    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_post_deleted({"postId": post_id, "authorUid": "uid1"}, mongo, redis)

    mock_delete.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# handle_profile_deleted — storage cleanup
# ─────────────────────────────────────────────────────────────────────────────

async def test_handle_profile_deleted_deletes_photo(mongo, redis):
    """The profile photo URL must be deleted from Firebase Storage."""
    PHOTO_URL = (
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
        "/o/profiles%2Fuid1%2Favatar.jpg?alt=media"
    )
    await mongo.profiles.insert_one({
        "_id": "uid1",
        "username": "alice",
        "profilePhoto": PHOTO_URL,
        "isDeleted": True,
    })

    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_profile_deleted({"userId": "uid1"}, mongo, redis)

    mock_delete.assert_called_once_with(PHOTO_URL)


async def test_handle_profile_deleted_no_photo_no_storage_call(mongo, redis):
    """Profiles without a photo must not trigger any storage deletion."""
    await mongo.profiles.insert_one({
        "_id": "uid1",
        "username": "alice",
        "profilePhoto": None,
        "isDeleted": True,
    })

    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_profile_deleted({"userId": "uid1"}, mongo, redis)

    mock_delete.assert_not_called()


async def test_handle_profile_deleted_missing_profile_no_crash(mongo, redis):
    """If the profile record is gone, storage cleanup is skipped gracefully."""
    with patch("src.handlers.delete_storage_url", new=AsyncMock()) as mock_delete:
        await handle_profile_deleted({"userId": "uid_missing"}, mongo, redis)

    mock_delete.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# delete_storage_url unit tests
# ─────────────────────────────────────────────────────────────────────────────

async def test_delete_storage_url_calls_blob_delete():
    from src.storage import delete_storage_url

    URL = (
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
        "/o/posts%2Fuid1%2Fuuid.jpg?alt=media"
    )
    mock_blob = MagicMock()
    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value.blob.return_value = mock_blob
        await delete_storage_url(URL)

    mock_storage.bucket.assert_called_once_with("proj.appspot.com")
    mock_storage.bucket.return_value.blob.assert_called_once_with("posts/uid1/uuid.jpg")
    mock_blob.delete.assert_called_once()


async def test_delete_storage_url_swallows_errors():
    from src.storage import delete_storage_url

    URL = (
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
        "/o/posts%2Fuid1%2Fuuid.jpg?alt=media"
    )
    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value.blob.return_value.delete.side_effect = RuntimeError("blob gone")
        # Must not raise
        await delete_storage_url(URL)
