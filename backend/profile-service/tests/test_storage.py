"""
Storage / file-upload tests.

Tests the shared upload_image helper and the upload_profile_photo /
upload_post_media mutations.  Firebase Storage calls are mocked via
unittest.mock.patch so no real network or credentials are needed.
"""
import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── Fake Upload object ────────────────────────────────────────────────────────

class FakeUpload:
    def __init__(self, content: bytes = b"fake-image-bytes", content_type: str = "image/jpeg"):
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


# ── upload_image unit tests ───────────────────────────────────────────────────

async def test_upload_image_rejects_invalid_type():
    from src.storage import upload_image
    fake = FakeUpload(content_type="application/pdf")
    with pytest.raises(ValueError, match="invalid file type"):
        await upload_image(fake, "profiles/uid1")


async def test_upload_image_rejects_oversized_file():
    from src.storage import upload_image
    big = FakeUpload(content=b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="too large"):
        await upload_image(big, "profiles/uid1")


async def test_upload_image_returns_public_url():
    from src.storage import upload_image

    mock_blob = MagicMock()
    mock_blob.upload_from_string = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value = mock_bucket
        url = await upload_image(FakeUpload(), "profiles/uid1")

    assert url.startswith("https://firebasestorage.googleapis.com/v0/b/")
    assert "profiles" in url
    assert "uid1" in url
    assert "alt=media" in url


async def test_upload_image_encodes_path_slashes():
    """Slashes in the storage path must be encoded as %2F in the URL."""
    from src.storage import upload_image

    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value.blob.return_value.upload_from_string = MagicMock()
        url = await upload_image(FakeUpload(), "profiles/uid1")

    assert "%2F" in url
    assert "/" not in url.split("/o/")[1].split("?")[0]


async def test_upload_image_wraps_firebase_errors():
    from src.storage import upload_image

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value.upload_from_string.side_effect = RuntimeError("network error")

    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value = mock_bucket
        with pytest.raises(ValueError, match="failed to upload"):
            await upload_image(FakeUpload(), "profiles/uid1")


async def test_upload_image_normalises_jpeg_extension():
    from src.storage import upload_image
    captured_path = []

    def fake_blob(path):
        captured_path.append(path)
        b = MagicMock()
        b.upload_from_string = MagicMock()
        return b

    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value.blob.side_effect = fake_blob
        await upload_image(FakeUpload(content_type="image/jpeg"), "profiles/uid1")

    assert captured_path[0].endswith(".jpg")


# ── upload_profile_photo mutation ─────────────────────────────────────────────

async def test_upload_profile_photo_updates_profile(gql, make_profile):
    await make_profile("uid1", "alice")

    FAKE_URL = "https://firebasestorage.googleapis.com/fake/profile.jpg?alt=media"

    with patch("src.resolvers.profiles.upload_image", new=AsyncMock(return_value=FAKE_URL)):
        r = await gql(
            "mutation ($file: Upload!) { uploadProfilePhoto(file: $file) { id profilePhoto } }",
            {"file": FakeUpload()},
            user_id="uid1",
        )

    assert r.errors is None
    assert r.data["uploadProfilePhoto"]["profilePhoto"] == FAKE_URL


async def test_upload_profile_photo_refreshes_redis_cache(gql, make_profile, redis):
    await make_profile("uid1", "alice")
    FAKE_URL = "https://firebasestorage.googleapis.com/fake/profile2.jpg?alt=media"

    with patch("src.resolvers.profiles.upload_image", new=AsyncMock(return_value=FAKE_URL)):
        await gql(
            "mutation ($file: Upload!) { uploadProfilePhoto(file: $file) { id } }",
            {"file": FakeUpload()},
            user_id="uid1",
        )

    import json
    cached = json.loads(await redis.get("profile:uid1"))
    assert cached["profilePhoto"] == FAKE_URL


async def test_upload_profile_photo_requires_auth(gql):
    r = await gql(
        "mutation ($file: Upload!) { uploadProfilePhoto(file: $file) { id } }",
        {"file": FakeUpload()},
        user_id=None,
    )
    assert r.errors is not None
    assert "authentication required" in str(r.errors[0].message)


async def test_upload_profile_photo_rejects_invalid_type(gql, make_profile):
    await make_profile("uid1", "alice")
    r = await gql(
        "mutation ($file: Upload!) { uploadProfilePhoto(file: $file) { id } }",
        {"file": FakeUpload(content_type="application/pdf")},
        user_id="uid1",
    )
    assert r.errors is not None


# ── upload_post_media mutation ────────────────────────────────────────────────

async def test_upload_post_media_returns_url(gql, make_profile):
    await make_profile("uid1", "alice")
    FAKE_URL = "https://firebasestorage.googleapis.com/fake/post_img.jpg?alt=media"

    with patch("src.resolvers.posts.upload_image", new=AsyncMock(return_value=FAKE_URL)):
        r = await gql(
            "mutation ($file: Upload!) { uploadPostMedia(file: $file) }",
            {"file": FakeUpload()},
            user_id="uid1",
        )

    assert r.errors is None
    assert r.data["uploadPostMedia"] == FAKE_URL


async def test_upload_post_media_requires_auth(gql):
    r = await gql(
        "mutation ($file: Upload!) { uploadPostMedia(file: $file) }",
        {"file": FakeUpload()},
        user_id=None,
    )
    assert r.errors is not None
    assert "authentication required" in str(r.errors[0].message)


async def test_upload_post_media_uses_post_folder(gql, make_profile):
    """Confirms the storage folder is scoped to posts/{user_id}."""
    await make_profile("uid1", "alice")
    captured = {}

    async def fake_upload(file, folder):
        captured["folder"] = folder
        return "https://fake.url"

    with patch("src.resolvers.posts.upload_image", new=fake_upload):
        await gql(
            "mutation ($file: Upload!) { uploadPostMedia(file: $file) }",
            {"file": FakeUpload()},
            user_id="uid1",
        )

    assert captured["folder"] == "posts/uid1"


# ── Worker storage cleanup (documented future requirement) ────────────────────

# ── Storage cleanup responsibility boundary ───────────────────────────────────

async def test_delete_post_does_not_call_storage_cleanup(gql, make_profile):
    """deletePost must NOT delete Firebase Storage blobs directly.
    Storage cleanup is the event-worker-service's responsibility (via the
    post.deleted RabbitMQ event).  Profile-service only soft-deletes in Mongo
    and tombstones Redis.
    """
    await make_profile("uid1", "alice")

    MEDIA_URL = (
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
        "/o/posts%2Fuid1%2Fsome-uuid.jpg?alt=media"
    )
    r = await gql(
        "mutation ($input: CreatePostInput!) { createPost(input: $input) { id } }",
        {"input": {"title": "With media", "media": [{"url": MEDIA_URL, "mimeType": "image/jpeg"}]}},
        user_id="uid1",
    )
    post_id = r.data["createPost"]["id"]

    with patch("src.storage.delete_storage_url", new=AsyncMock()) as mock_delete:
        r = await gql(f'mutation {{ deletePost(id: "{post_id}") }}', user_id="uid1")
        assert r.errors is None

    mock_delete.assert_not_called()


async def test_delete_storage_url_unit():
    """delete_storage_url parses the URL and calls blob.delete()."""
    from src.storage import delete_storage_url

    URL = (
        "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
        "/o/posts%2Fuid1%2Fsome-uuid.jpg?alt=media"
    )

    mock_blob = MagicMock()
    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value.blob.return_value = mock_blob
        await delete_storage_url(URL)

    mock_storage.bucket.assert_called_once_with("proj.appspot.com")
    mock_storage.bucket.return_value.blob.assert_called_once_with("posts/uid1/some-uuid.jpg")
    mock_blob.delete.assert_called_once()


async def test_delete_storage_url_swallows_errors():
    """delete_storage_url must not raise when Firebase fails."""
    from src.storage import delete_storage_url

    with patch("src.storage.storage") as mock_storage:
        mock_storage.bucket.return_value.blob.return_value.delete.side_effect = RuntimeError("gone")
        # Should not raise
        await delete_storage_url(
            "https://firebasestorage.googleapis.com/v0/b/proj.appspot.com"
            "/o/posts%2Fuid1%2Fuuid.jpg?alt=media"
        )
