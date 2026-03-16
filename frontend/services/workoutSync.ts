/**
 * Auto-sync service for HealthKit workouts.
 *
 * When enabled, fetches recent workouts from Apple Health,
 * checks the backend for duplicates, and creates posts for new ones.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { fetchWorkoutsSince, isHealthAvailable, type HealthWorkout } from './health';
import { getIdToken, getUid } from './auth';
import { config } from '@/config';

const STORAGE_KEY_ENABLED = '@fervora/autoSyncWorkouts';
const STORAGE_KEY_LAST_SYNC = '@fervora/lastWorkoutSync';

/** Check if auto-sync is enabled. */
export async function isAutoSyncEnabled(): Promise<boolean> {
  const val = await AsyncStorage.getItem(STORAGE_KEY_ENABLED);
  return val === 'true';
}

/** Enable or disable auto-sync. */
export async function setAutoSyncEnabled(enabled: boolean): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY_ENABLED, enabled ? 'true' : 'false');
  if (!enabled) {
    await AsyncStorage.removeItem(STORAGE_KEY_LAST_SYNC);
  }
}

/**
 * Run a sync cycle: fetch new workouts from HealthKit, deduplicate
 * against the backend, and create posts for any unseen workouts.
 *
 * Returns the number of new workouts synced.
 */
export async function syncWorkouts(): Promise<number> {
  if (!isHealthAvailable()) return 0;

  const uid = getUid();
  const token = getIdToken();
  if (!uid || !token) return 0;

  // Determine how far back to look
  const lastSyncRaw = await AsyncStorage.getItem(STORAGE_KEY_LAST_SYNC);
  const since = lastSyncRaw ? new Date(lastSyncRaw) : new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);

  const workouts = await fetchWorkoutsSince(since);
  console.log(`[WorkoutSync] Found ${workouts.length} workouts since ${since.toISOString()}`);
  if (workouts.length === 0) {
    return 0;
  }

  // Check which are already synced
  const healthKitIds = workouts.map((w) => w.healthKitId);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };

  const checkResp = await fetch(`${config.apiBaseUrl}/posts/check-synced`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ healthKitIds }),
  });
  if (!checkResp.ok) {
    console.log(`[WorkoutSync] check-synced failed: ${checkResp.status} ${await checkResp.text()}`);
    return 0;
  }

  const { syncedIds } = (await checkResp.json()) as { syncedIds: string[] };
  const syncedSet = new Set(syncedIds);
  const newWorkouts = workouts.filter((w) => !syncedSet.has(w.healthKitId));
  console.log(`[WorkoutSync] ${syncedIds.length} already synced, ${newWorkouts.length} new`);

  // Create a post for each new workout
  let synced = 0;
  for (const w of newWorkouts) {
    const postBody: Record<string, any> = {
      workout: {
        activityType: w.activityType,
        durationSeconds: Math.round(w.durationSeconds),
        caloriesBurned: w.caloriesBurned,
        distanceMiles: w.distanceMiles,
        avgHeartRate: w.avgHeartRate,
        maxHeartRate: w.maxHeartRate,
        elevationFeet: w.elevationFeet,
        startDate: w.startDate.toISOString(),
        endDate: w.endDate.toISOString(),
      },
      healthKitId: w.healthKitId,
    };

    // Strip null/undefined/NaN values from workout
    for (const key of Object.keys(postBody.workout)) {
      const v = postBody.workout[key];
      if (v == null || (typeof v === 'number' && !Number.isFinite(v))) delete postBody.workout[key];
    }

    const resp = await fetch(`${config.apiBaseUrl}/posts`, {
      method: 'POST',
      headers,
      body: JSON.stringify(postBody),
    });
    if (!resp.ok) {
      console.log(`[WorkoutSync] create post failed: ${resp.status} ${await resp.text()}`);
    } else {
      synced++;
    }
  }

  if (synced > 0) {
    await AsyncStorage.setItem(STORAGE_KEY_LAST_SYNC, new Date().toISOString());
  }
  return synced;
}
