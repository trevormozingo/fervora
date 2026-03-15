/**
 * Apple Health workout import service.
 *
 * Uses @kingstinct/react-native-healthkit to read recent workouts
 * and map them to the app's workout model.
 */

import { Platform } from 'react-native';
import type { ActivityType } from '@/models/post';

export interface HealthWorkout {
  /** HealthKit workout UUID — used for deduplication */
  healthKitId: string;
  /** Our app's activity type */
  activityType: ActivityType;
  /** Duration in seconds */
  durationSeconds: number;
  /** Calories burned (may be 0 if unavailable) */
  caloriesBurned: number;
  /** Distance in miles (may be null if unavailable) */
  distanceMiles: number | null;
  /** Average heart rate in BPM (may be null if unavailable) */
  avgHeartRate: number | null;
  /** Max heart rate in BPM (may be null if unavailable) */
  maxHeartRate: number | null;
  /** Elevation gain in feet (may be null if unavailable) */
  elevationFeet: number | null;
  /** When the workout started */
  startDate: Date;
  /** When the workout ended */
  endDate: Date;
  /** Display label, e.g. "Running · 45 min · 350 cal" */
  label: string;
}

// WorkoutActivityType enum values → our ActivityType
// Values from @kingstinct/react-native-healthkit WorkoutActivityType
const HK_ACTIVITY_MAP: Record<number, ActivityType> = {
  37: 'running',
  13: 'cycling',
  46: 'swimming',
  20: 'weightlifting',    // functionalStrengthTraining
  50: 'weightlifting',    // traditionalStrengthTraining
  11: 'crossfit',         // crossTraining
  14: 'dance',
  57: 'yoga',
  66: 'pilates',
  24: 'hiking',
  35: 'rowing',
  8:  'boxing',
  28: 'martial_arts',     // martialArts
  9:  'climbing',
  63: 'hiit',             // highIntensityIntervalTraining
  52: 'walking',
  62: 'stretching',       // flexibility
  73: 'cardio',           // mixedCardio
  64: 'cardio',           // jumpRope
  6:  'sports',           // basketball
  41: 'sports',           // soccer
  48: 'sports',           // tennis
};

function mapActivityType(hkType: number): ActivityType {
  return HK_ACTIVITY_MAP[hkType] ?? 'other';
}

/** Return the number if it's finite, otherwise null. */
function safeNum(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function formatDuration(seconds: number): string {
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

function buildLabel(activityType: ActivityType, durationSeconds: number, calories: number): string {
  const name = activityType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  const parts = [name, formatDuration(durationSeconds)];
  if (calories > 0) parts.push(`${Math.round(calories)} cal`);
  return parts.join(' · ');
}

/**
 * Check whether HealthKit is available (iOS only).
 */
export function isHealthAvailable(): boolean {
  return Platform.OS === 'ios';
}

export interface HealthBodyMetrics {
  weightLbs: number | null;
  bodyFatPercentage: number | null;
  restingHeartRate: number | null;
  leanBodyMassLbs: number | null;
  /** Display label, e.g. "185 lbs · 15% BF" */
  label: string;
}

/**
 * Fetch the most recent body weight and body fat % from Apple Health.
 */
export async function fetchBodyMetrics(): Promise<HealthBodyMetrics | null> {
  if (!isHealthAvailable()) return null;

  const HealthKit = await import('@kingstinct/react-native-healthkit');

  await HealthKit.requestAuthorization({
    toRead: [
      'HKQuantityTypeIdentifierBodyMass' as any,
      'HKQuantityTypeIdentifierBodyFatPercentage' as any,
      'HKQuantityTypeIdentifierRestingHeartRate' as any,
      'HKQuantityTypeIdentifierLeanBodyMass' as any,
    ],
  });

  const [weightSample, bfSample, rhrSample, lbmSample] = await Promise.all([
    HealthKit.getMostRecentQuantitySample(
      'HKQuantityTypeIdentifierBodyMass' as any,
      'lb',
    ),
    HealthKit.getMostRecentQuantitySample(
      'HKQuantityTypeIdentifierBodyFatPercentage' as any,
      '%',
    ),
    HealthKit.getMostRecentQuantitySample(
      'HKQuantityTypeIdentifierRestingHeartRate' as any,
      'count/min' as any,
    ),
    HealthKit.getMostRecentQuantitySample(
      'HKQuantityTypeIdentifierLeanBodyMass' as any,
      'lb',
    ),
  ]);

  const weightLbs = weightSample ? Math.round(weightSample.quantity * 10) / 10 : null;
  const bodyFatPercentage = bfSample ? Math.round(bfSample.quantity * 10) / 10 : null;
  const restingHeartRate = rhrSample ? Math.round(rhrSample.quantity) : null;
  const leanBodyMassLbs = lbmSample ? Math.round(lbmSample.quantity * 10) / 10 : null;

  if (weightLbs === null && bodyFatPercentage === null && restingHeartRate === null && leanBodyMassLbs === null) return null;

  const parts: string[] = [];
  if (weightLbs !== null) parts.push(`${weightLbs} lbs`);
  if (bodyFatPercentage !== null) parts.push(`${bodyFatPercentage}% BF`);
  if (restingHeartRate !== null) parts.push(`${restingHeartRate} rhr`);
  if (leanBodyMassLbs !== null) parts.push(`${leanBodyMassLbs} lbs lean`);

  return { weightLbs, bodyFatPercentage, restingHeartRate, leanBodyMassLbs, label: parts.join(' · ') };
}

/**
 * Request HealthKit authorization and fetch recent workouts.
 * Returns the last `limit` workouts, sorted newest first.
 */
export async function fetchRecentWorkouts(
  limit = 20,
): Promise<HealthWorkout[]> {
  if (!isHealthAvailable()) return [];

  // Dynamic import so Android doesn't crash
  const HealthKit = await import('@kingstinct/react-native-healthkit');

  // Request read access for workouts
  await HealthKit.requestAuthorization({
    toRead: ['HKWorkoutTypeIdentifier' as any],
  });

  const samples = await HealthKit.queryWorkoutSamples({
    limit,
    ascending: false,
  });

  return samples.map((s) => {
    const start = new Date(s.startDate);
    const end = new Date(s.endDate);
    const durationSeconds = Math.round(safeNum(s.duration.quantity) ?? 0);
    const caloriesBurned = Math.round(safeNum(s.totalEnergyBurned?.quantity) ?? 0);
    const activityType = mapActivityType(s.workoutActivityType);
    const healthKitId = (s as any).uuid as string;

    // Distance: HealthKit provides in meters, convert to miles
    const distRaw = safeNum((s as any).totalDistance?.quantity);
    const distanceMiles = distRaw != null ? Math.round((distRaw / 1609.344) * 100) / 100 : null;

    // Elevation gain (metadata, may not be present)
    const elevRaw = safeNum((s as any).totalFlightsClimbed?.quantity) ?? safeNum((s as any).metadata?.HKElevationAscended);
    const elevationFeet = elevRaw != null ? Math.round(elevRaw * 3.28084) : null;

    // Heart rate stats from workout events/metadata (may not be present)
    const avgHR = safeNum((s as any).metadata?.HKAverageHeartRate);
    const avgHeartRate = avgHR != null ? Math.round(avgHR) : null;
    const maxHR = safeNum((s as any).metadata?.HKMaximumHeartRate);
    const maxHeartRate = maxHR != null ? Math.round(maxHR) : null;

    return {
      healthKitId,
      activityType,
      durationSeconds,
      caloriesBurned,
      distanceMiles,
      avgHeartRate,
      maxHeartRate,
      elevationFeet,
      startDate: start,
      endDate: end,
      label: buildLabel(activityType, durationSeconds, caloriesBurned),
    };
  });
}

/**
 * Fetch workouts from HealthKit since a given date (for auto-sync).
 * Returns up to 50 workouts, newest first.
 */
export async function fetchWorkoutsSince(since: Date): Promise<HealthWorkout[]> {
  if (!isHealthAvailable()) return [];

  const HealthKit = await import('@kingstinct/react-native-healthkit');

  await HealthKit.requestAuthorization({
    toRead: ['HKWorkoutTypeIdentifier' as any],
  });

  const samples = await HealthKit.queryWorkoutSamples({
    filter: { date: { startDate: since } },
    limit: 50,
    ascending: false,
  });

  return samples.map((s) => {
    const start = new Date(s.startDate);
    const end = new Date(s.endDate);
    const durationSeconds = Math.round(safeNum(s.duration.quantity) ?? 0);
    const caloriesBurned = Math.round(safeNum(s.totalEnergyBurned?.quantity) ?? 0);
    const activityType = mapActivityType(s.workoutActivityType);
    const healthKitId = (s as any).uuid as string;

    const distRaw = safeNum((s as any).totalDistance?.quantity);
    const distanceMiles = distRaw != null ? Math.round((distRaw / 1609.344) * 100) / 100 : null;

    const elevRaw = safeNum((s as any).totalFlightsClimbed?.quantity) ?? safeNum((s as any).metadata?.HKElevationAscended);
    const elevationFeet = elevRaw != null ? Math.round(elevRaw * 3.28084) : null;

    const avgHR = safeNum((s as any).metadata?.HKAverageHeartRate);
    const avgHeartRate = avgHR != null ? Math.round(avgHR) : null;
    const maxHR = safeNum((s as any).metadata?.HKMaximumHeartRate);
    const maxHeartRate = maxHR != null ? Math.round(maxHR) : null;

    return {
      healthKitId,
      activityType,
      durationSeconds,
      caloriesBurned,
      distanceMiles,
      avgHeartRate,
      maxHeartRate,
      elevationFeet,
      startDate: start,
      endDate: end,
      label: buildLabel(activityType, durationSeconds, caloriesBurned),
    };
  });
}
