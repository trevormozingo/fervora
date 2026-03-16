/**
 * Central config for API URLs and environment flags.
 *
 * Emulator:   FIREBASE_AUTH_URL = http://localhost:9099/identitytoolkit.googleapis.com/v1
 * Production: FIREBASE_AUTH_URL = https://identitytoolkit.googleapis.com/v1
 *
 * Auto-detects the dev server host so physical devices connect to the Mac's IP
 * instead of localhost (which only works on the simulator).
 */

import Constants from 'expo-constants';

const useEmulator = (process.env.EXPO_PUBLIC_USE_FIREBASE_EMULATOR ?? 'true') === 'true';

/**
 * Resolve the host to use for local services.
 * On a physical device, Expo's debuggerHost contains the Mac's LAN IP.
 * On simulator / web, falls back to localhost.
 */
function getDevHost(): string {
  try {
    const host =
      (Constants as any).debuggerHost ??          // runtime connection to Metro
      Constants.expoConfig?.hostUri ??            // baked in at build time
      '';
    const ip = host.split(':')[0];
    if (ip) return ip;
  } catch {
    // debuggerHost may be uninitialized before local network permission is granted
  }
  // Fallback to your Mac's LAN IP for physical device testing
  return '192.168.1.16';
}

const devHost = getDevHost();
console.log('[config] devHost resolved to:', devHost);

const emulatorHost =
  process.env.EXPO_PUBLIC_FIREBASE_AUTH_EMULATOR_URL ?? `http://${devHost}:9099`;

export const config = {
  /** API Gateway base URL (no trailing slash) */
  apiBaseUrl: process.env.EXPO_PUBLIC_API_URL ?? `http://${devHost}:8080`,

  /** Firebase project ID */
  firebaseProjectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID ?? 'fervora-local',

  /** Firebase API key — use your real key in production */
  firebaseApiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY ?? 'fake-api-key',

  /**
   * Firebase Auth REST API base URL (no trailing slash).
   * Same endpoints for emulator and production — only the host differs.
   */
  firebaseAuthUrl: useEmulator
    ? `${emulatorHost}/identitytoolkit.googleapis.com/v1`
    : 'https://identitytoolkit.googleapis.com/v1',

  /** Firebase Storage bucket */
  firebaseStorageBucket:
    process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET ?? 'fervora-local.appspot.com',

  /** Emulator host (used only for dev-only helpers like fetching verification codes) */
  emulatorHost: useEmulator ? emulatorHost : null,

  /** Whether we're using the emulator */
  useEmulator,

  /** Firestore emulator host (IP only, no protocol) */
  firestoreHost: devHost,

  /** Firestore emulator port */
  firestorePort: useEmulator ? 8181 : 0,
} as const;
