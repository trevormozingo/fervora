"""
Firebase Storage helper — upload and delete media files.

Uses ``google-cloud-storage`` directly so we can pass anonymous
credentials when targeting the Storage emulator (no service-account
JSON required during local development).

Path conventions:
    users/{uid}/profile.{ext}               — profile photo
    users/{uid}/posts/{postId}/{index}.{ext} — post media

In local dev the STORAGE_EMULATOR_HOST env var tells the client
to target the emulator instead of production GCS.
"""

import os
import uuid
from urllib.parse import quote

from google.auth.credentials import AnonymousCredentials
from google.cloud import storage as gcs

_bucket = None
_emulator_host: str | None = None
_public_host: str | None = None


def init_storage(bucket_name: str | None = None) -> None:
    """
    Initialise the GCS storage bucket.

    Call once at app startup (from lifespan).
    """
    global _bucket, _emulator_host, _public_host

    bucket_name = bucket_name or os.getenv(
        "FIREBASE_STORAGE_BUCKET", "fervora-local.appspot.com"
    )
    project_id = os.getenv("FIREBASE_PROJECT_ID", "fervora-local")

    _emulator_host = os.getenv("STORAGE_EMULATOR_HOST")
    # Public host is the externally-reachable URL for the emulator
    # (e.g. http://<mac-lan-ip>:9199). Falls back to the emulator host.
    _public_host = os.getenv("STORAGE_PUBLIC_HOST", _emulator_host)
    if _emulator_host:
        # Emulator mode — use anonymous credentials
        client = gcs.Client(
            project=project_id,
            credentials=AnonymousCredentials(),
        )
        # Point the client at the emulator
        client._connection.API_BASE_URL = _emulator_host
    else:
        # Production — uses ADC or GOOGLE_APPLICATION_CREDENTIALS
        client = gcs.Client(project=project_id)

    _bucket = client.bucket(bucket_name)


def _get_bucket():
    if _bucket is None:
        raise RuntimeError("Storage not initialised — call init_storage() first")
    return _bucket


def _download_url(path: str) -> str:
    """
    Build a download URL for the uploaded file.

    Emulator:   http://{host}/v0/b/{bucket}/o/{encoded_path}?alt=media
    Production: https://storage.googleapis.com/{bucket}/{path}
    """
    bucket_name = _get_bucket().name
    encoded = quote(path, safe="")
    if _emulator_host:
        host = _public_host or _emulator_host
        return f"{host}/v0/b/{bucket_name}/o/{encoded}?alt=media"
    return f"https://storage.googleapis.com/{bucket_name}/{encoded}"


def upload_file(
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Upload bytes to Firebase Storage at *path* and return the download URL.
    """
    blob = _get_bucket().blob(path)
    blob.upload_from_string(data, content_type=content_type)
    return _download_url(path)


def upload_profile_photo(uid: str, data: bytes, content_type: str, filename: str) -> str:
    """Upload (or replace) a user's profile photo. Returns the public URL."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    path = f"users/{uid}/profile.{ext}"
    return upload_file(path, data, content_type)


def upload_post_media(
    uid: str, post_id: str, index: int, data: bytes, content_type: str, filename: str
) -> dict:
    """Upload a single post media file. Returns { url, mimeType }."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    path = f"users/{uid}/posts/{post_id}/{index}.{ext}"
    url = upload_file(path, data, content_type)
    return {"url": url, "mimeType": content_type}


def generate_post_id() -> str:
    """Generate a unique post media folder ID."""
    return uuid.uuid4().hex[:16]


def delete_prefix(prefix: str) -> None:
    """
    Delete every object under a given prefix (folder).

    e.g. delete_prefix("users/abc123/") deletes profile photo + all posts.
    """
    bucket = _get_bucket()
    blobs = list(bucket.list_blobs(prefix=prefix))
    for blob in blobs:
        try:
            blob.delete()
        except Exception:
            pass


def delete_user_media(uid: str) -> None:
    """Delete ALL media for a user (profile photo + post images)."""
    delete_prefix(f"users/{uid}/")


def delete_post_media(uid: str, post_id: str) -> None:
    """Delete all media for a specific post."""
    delete_prefix(f"users/{uid}/posts/{post_id}/")
