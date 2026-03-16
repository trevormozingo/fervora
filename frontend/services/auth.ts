/**
 * Auth service — Firebase phone auth.
 *
 * Verification codes are sent via the Identity Toolkit REST endpoint
 * (same on emulator & production).  Sign-in is done through the
 * Firebase Auth SDK's signInWithCredential, which:
 *   1. Verifies the code
 *   2. Sets auth.currentUser (required by Storage rules)
 *   3. Persists the session via getReactNativePersistence
 *
 * In emulator mode, the verification code is auto-fetched for convenience.
 */

import { config } from '@/config';
import {
  signInWithCredential,
  PhoneAuthProvider,
  onAuthStateChanged,
  onIdTokenChanged,
  signOut as firebaseSignOut,
} from 'firebase/auth';
import { auth } from './firebase';

const AUTH_URL = config.firebaseAuthUrl;
const API_KEY = config.firebaseApiKey;

// Cached auth state for synchronous access via getIdToken() / getUid()
let _idToken: string | null = null;
let _uid: string | null = null;
let _restored = false;

/**
 * Wait for the Firebase Auth SDK to restore its persisted session.
 * Returns true if a user session exists.
 */
export async function restoreAuth(): Promise<boolean> {
  if (_restored) return !!_idToken;

  // onAuthStateChanged fires once immediately with the restored user (or null)
  const user = await new Promise<import('firebase/auth').User | null>((resolve) => {
    const unsubscribe = onAuthStateChanged(auth, (u) => {
      unsubscribe();
      resolve(u);
    });
  });

  if (user) {
    _idToken = await user.getIdToken();
    _uid = user.uid;
  }

  // Keep the cached token fresh when Firebase refreshes it (~1 hour)
  onIdTokenChanged(auth, async (u) => {
    if (u) {
      _idToken = await u.getIdToken();
      _uid = u.uid;
    } else {
      _idToken = null;
      _uid = null;
    }
  });

  _restored = true;
  return !!_idToken;
}

/**
 * Send a verification code to the given phone number.
 * @returns sessionInfo, and in emulator mode, the auto-fetched code.
 */
export async function sendVerificationCode(
  phoneNumber: string,
): Promise<{ sessionInfo: string; code?: string }> {
  const res = await fetch(
    `${AUTH_URL}/accounts:sendVerificationCode?key=${API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phoneNumber }),
    },
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.error?.message ?? `Failed to send code (${res.status})`);
  }

  const data = await res.json();
  const sessionInfo: string = data.sessionInfo;

  // Dev convenience: auto-fetch the code from the emulator
  let code: string | undefined;
  if (config.emulatorHost) {
    code = await fetchEmulatorCode(sessionInfo);
  }

  return { sessionInfo, code };
}

/**
 * Verify the SMS code and sign the user in via Firebase Auth SDK.
 * This sets auth.currentUser — required by Firebase Storage rules.
 * Returns the user's UID and ID token.
 */
export async function verifyCode(
  sessionInfo: string,
  code: string,
): Promise<{ uid: string; idToken: string }> {
  const credential = PhoneAuthProvider.credential(sessionInfo, code);
  const userCredential = await signInWithCredential(auth, credential);

  _idToken = await userCredential.user.getIdToken();
  _uid = userCredential.user.uid;

  return { uid: _uid, idToken: _idToken };
}

// ── Common helpers ────────────────────────────────────────────────────────────

export async function signOut(): Promise<void> {
  _idToken = null;
  _uid = null;
  await firebaseSignOut(auth);
}

/**
 * Delete the Firebase account.
 * Caller is responsible for deleting the profile first.
 */
export async function deleteFirebaseAccount(): Promise<void> {
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  await user.delete();
  _idToken = null;
  _uid = null;
}

export function getIdToken(): string | null {
  return _idToken;
}

export function getUid(): string | null {
  return _uid;
}

// ── Dev-only helpers ──────────────────────────────────────────────────────────

async function fetchEmulatorCode(sessionInfo: string): Promise<string | undefined> {
  if (!config.emulatorHost) return undefined;
  try {
    const res = await fetch(
      `${config.emulatorHost}/emulator/v1/projects/${config.firebaseProjectId}/verificationCodes`,
    );
    if (!res.ok) return undefined;
    const data = await res.json();
    const match = data.verificationCodes?.find(
      (vc: any) => vc.sessionInfo === sessionInfo,
    );
    return match?.code;
  } catch {
    return undefined;
  }
}
