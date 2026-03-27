import asyncio
import logging

from firebase_admin import storage

logger = logging.getLogger(__name__)


async def delete_storage_url(url: str) -> None:
    """Delete a Firebase Storage blob given its public URL.

    Parses the bucket and path from the URL produced by the profile-service
    upload_image helper and calls blob.delete().  Any error is logged as a
    warning and swallowed — storage cleanup must never block event processing.

    Expected URL format:
        https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded_path}?alt=media
    """
    try:
        bucket_name = url.split("/b/")[1].split("/o/")[0]
        encoded_path = url.split("/o/")[1].split("?")[0]
        storage_path = encoded_path.replace("%2F", "/")

        def _delete() -> None:
            bucket = storage.bucket(bucket_name)
            blob = bucket.blob(storage_path)
            blob.delete()

        await asyncio.to_thread(_delete)
        logger.debug("storage blob deleted  path=%s", storage_path)
    except Exception as exc:
        logger.warning("failed to delete storage blob url=%s error=%s", url, exc)
