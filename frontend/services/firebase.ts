/**
 * Firebase app initialization.
 *
 * Uses initializeAuth with React Native persistence so that
 * auth.currentUser survives app restarts — required for
 * obtaining ID tokens used by the backend API.
 *
 * Connects to the Auth Emulator when config.useEmulator is true.
 * Storage is handled entirely by the backend (Admin SDK), so
 * the client no longer initialises the Storage SDK.
 */

import { initializeApp, getApps, getApp } from 'firebase/app';
import {
  initializeAuth,
  getAuth,
  getReactNativePersistence,
  connectAuthEmulator,
} from 'firebase/auth';
import { getFirestore, connectFirestoreEmulator } from 'firebase/firestore';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { config } from '@/config';

const firebaseConfig = {
  apiKey: config.firebaseApiKey,
  projectId: config.firebaseProjectId,
};

// Initialize app once
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();

// Initialize Auth with React Native persistence.
// initializeAuth throws if called twice (e.g. hot reload), so fall back to getAuth.
let authInstance;
try {
  authInstance = initializeAuth(app, {
    persistence: getReactNativePersistence(AsyncStorage),
  });
} catch {
  authInstance = getAuth(app);
}

export const auth = authInstance;

// Firestore
export const db = getFirestore(app);

// Connect to emulators in local dev
if (config.emulatorHost) {
  try {
    connectAuthEmulator(auth, config.emulatorHost, {
      disableWarnings: true,
    });
  } catch {
    // Already connected — ignore
  }
  try {
    connectFirestoreEmulator(db, config.firestoreHost, config.firestorePort);
  } catch {
    // Already connected — ignore
  }
}
