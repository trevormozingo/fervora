"""
Firebase authentication module.

Uses firebase-admin SDK to verify ID tokens. In local/test environments,
set FIREBASE_AUTH_EMULATOR_HOST to point at the Firebase Auth Emulator
(e.g. "firebase-emulator:9099") — the SDK auto-detects it and skips
real credential checks.
"""

import os

import firebase_admin
from firebase_admin import auth, credentials

_initialized = False


def _init_firebase():
    """Initialize the Firebase Admin SDK (once)."""
    global _initialized
    if _initialized:
        return

    project_id = os.getenv("FIREBASE_PROJECT_ID", "fervora-local")

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        # When using the emulator or Application Default Credentials,
        # no key file is needed — just a project ID.
        firebase_admin.initialize_app(options={"projectId": project_id})

    _initialized = True


def verify_token(token: str) -> dict:
    """
    Verify a Firebase ID token and return the decoded claims.

    Args:
        token: The raw Bearer token string.

    Returns:
        Decoded token dict with at least a "uid" key.

    Raises:
        ValueError: If token is invalid or expired.
    """
    _init_firebase()

    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        raise ValueError(f"Invalid Firebase token: {e}")
