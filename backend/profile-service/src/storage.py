import asyncio
import logging
import os
import uuid
from firebase_admin import storage
from strawberry.file_uploads import Upload

logger = logging.getLogger(__name__)

ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def upload_image(file: Upload, folder: str) -> str:
    """Validate, upload an image to Firebase Storage, and return its public URL.

    Args:
        file:   The uploaded file from GraphQL.
        folder: The storage path prefix (e.g. "profiles/uid123" or "posts/uid123").

    Returns:
        The public HTTPS URL of the uploaded file.

    Raises:
        ValueError: On invalid content type or file too large.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise ValueError(f"invalid file type — allowed: {ALLOWED_TYPES}")

    contents = await file.read()
    if len(contents) > MAX_SIZE_BYTES:
        raise ValueError("file is too large — maximum size is 5 MB")

    extension = file.content_type.split("/")[-1]
    if extension == "jpeg":
        extension = "jpg"

    file_path = f"{folder}/{uuid.uuid4()}.{extension}"
    bucket_name = f"{os.environ.get('FIREBASE_PROJECT_ID', 'fervora-local')}.appspot.com"

    def _upload():
        bucket = storage.bucket(bucket_name)
        blob = bucket.blob(file_path)
        blob.upload_from_string(contents, content_type=file.content_type)

    try:
        await asyncio.to_thread(_upload)
    except Exception as e:
        raise ValueError(f"failed to upload image: {e}")

    encoded_path = file_path.replace("/", "%2F")
    return f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}?alt=media"


async def delete_storage_url(url: str) -> None:
    """Delete a Firebase Storage blob given its public URL.

    Parses the bucket and path from the URL produced by upload_image and calls
    blob.delete().  Any error is logged as a warning and swallowed so that
    storage cleanup never causes a mutation to fail.
    """
    try:
        # URL format: .../v0/b/{bucket}/o/{encoded_path}?alt=media
        bucket_name = url.split("/b/")[1].split("/o/")[0]
        encoded_path = url.split("/o/")[1].split("?")[0]
        storage_path = encoded_path.replace("%2F", "/")

        def _delete() -> None:
            bucket = storage.bucket(bucket_name)
            blob = bucket.blob(storage_path)
            blob.delete()

        await asyncio.to_thread(_delete)
    except Exception as exc:
        logger.warning("failed to delete storage blob url=%s error=%s", url, exc)
