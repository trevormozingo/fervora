// ──────────────────────────────────────────────────────────────────────────────
// Post models — based on models/post/*.schema.json
// ──────────────────────────────────────────────────────────────────────────────

import { z } from 'zod';

export const ACTIVITY_TYPES = [
  'running',
  'cycling',
  'swimming',
  'weightlifting',
  'crossfit',
  'yoga',
  'pilates',
  'hiking',
  'rowing',
  'boxing',
  'martial_arts',
  'climbing',
  'dance',
  'stretching',
  'cardio',
  'hiit',
  'walking',
  'sports',
  'other',
] as const;

export type ActivityType = (typeof ACTIVITY_TYPES)[number];

export const activityLabel = (t: ActivityType): string =>
  t
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

export const MediaItemSchema = z.object({
  url: z.string().url(),
  mimeType: z.string(),
});

export type MediaItem = z.infer<typeof MediaItemSchema>;

const WorkoutSchema = z.object({
  activityType: z.enum(ACTIVITY_TYPES),
  durationSeconds: z.number().int().min(0).nullable().optional(),
  caloriesBurned: z.number().min(0).nullable().optional(),
  distanceMiles: z.number().min(0).nullable().optional(),
  avgHeartRate: z.number().min(0).nullable().optional(),
  maxHeartRate: z.number().min(0).nullable().optional(),
  elevationFeet: z.number().min(0).nullable().optional(),
});

const BodyMetricsSchema = z
  .object({
    weightLbs: z.number().min(0).nullable().optional(),
    bodyFatPercentage: z.number().min(0).max(100).nullable().optional(),
    restingHeartRate: z.number().min(0).nullable().optional(),
    leanBodyMassLbs: z.number().min(0).nullable().optional(),
  })
  .refine(
    (d) => Object.values(d).some((v) => v !== undefined && v !== null),
    { message: 'Provide at least one metric' },
  );

/** Schema for creating a new post. At least one content field required. */
export const CreatePostSchema = z
  .object({
    title: z.string().min(1).max(200).nullable().optional(),
    body: z.string().min(1).max(5000).nullable().optional(),
    media: z.array(MediaItemSchema).max(10).nullable().optional(),
    workout: WorkoutSchema.nullable().optional(),
    bodyMetrics: BodyMetricsSchema.nullable().optional(),
    storagePostId: z.string().optional(),
  })
  .refine(
    (data) => {
      const { title, body, media, workout, bodyMetrics } = data;
      return [title, body, workout, bodyMetrics].some(
        (v) => v !== undefined && v !== null && v !== '',
      ) || (media && media.length > 0);
    },
    { message: 'A post must contain at least one content field' },
  );

export type CreatePost = z.infer<typeof CreatePostSchema>;
