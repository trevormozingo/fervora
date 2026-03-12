// ──────────────────────────────────────────────────────────────────────────────
// AUTO-GENERATED — DO NOT EDIT
// Source: models/profile/*.schema.json
// Regenerate: npm run generate:models
// ──────────────────────────────────────────────────────────────────────────────

import { z } from 'zod';

export type FieldMeta = {
  name: string;
  label: string;
  placeholder: string;
  type: 'string' | 'number' | 'boolean';
  required: boolean;
  nullable: boolean;
  keyboard: 'default' | 'email-address' | 'numeric' | 'phone-pad';
  secure: boolean;
  multiline: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  description?: string;
};


export const INTEREST_OPTIONS = [
  "Weightlifting",
  "Powerlifting",
  "Bodybuilding",
  "Strongman",
  "Olympic Lifting",
  "Calisthenics",
  "CrossFit",
  "Running",
  "Cycling",
  "Swimming",
  "Rowing",
  "Jump Rope",
  "Stair Climbing",
  "Boxing",
  "MMA",
  "Wrestling",
  "Jiu-Jitsu",
  "Muay Thai",
  "Yoga",
  "Pilates",
  "Stretching",
  "Mobility Work",
  "Hiking",
  "Rock Climbing",
  "Trail Running",
  "Obstacle Course Racing",
  "Functional Fitness",
  "Basketball",
  "Soccer",
  "Tennis",
  "Volleyball",
  "Pickleball",
  "Flag Football"
] as const;

export const FITNESS_LEVEL_OPTIONS = [
  "novice",
  "intermediate",
  "experienced",
  "pro",
  "olympian"
] as const;

/** Base profile schema containing all profile fields */
export const BaseProfileSchema = z.object({
  id: z.string().optional(),
  username: z.string().min(3).max(30).regex(/^[a-zA-Z0-9_-]+$/).optional(),
  displayName: z.string().min(1).max(100).optional(),
  bio: z.string().max(500).nullable().default(null).optional(),
  birthday: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().default(null).optional(),
  profilePhoto: z.string().nullable().default(null).optional(),
  location: z.unknown().nullable().default(null).optional(),
  interests: z.array(z.enum(["Weightlifting", "Powerlifting", "Bodybuilding", "Strongman", "Olympic Lifting", "Calisthenics", "CrossFit", "Running", "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing", "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai", "Yoga", "Pilates", "Stretching", "Mobility Work", "Hiking", "Rock Climbing", "Trail Running", "Obstacle Course Racing", "Functional Fitness", "Basketball", "Soccer", "Tennis", "Volleyball", "Pickleball", "Flag Football"])).max(20).nullable().optional(),
  fitnessLevel: z.enum(["novice", "intermediate", "experienced", "pro", "olympian"]).nullable().optional(),
});
export type BaseProfile = z.infer<typeof BaseProfileSchema>;

/** Schema for creating a new profile. Server generates id, timestamps, and defaults. */
export const CreateProfileSchema = z.object({
  username: z.string().min(3).max(30).regex(/^[a-zA-Z0-9_-]+$/),
  displayName: z.string().min(1).max(100),
  profilePhoto: z.string().nullable().default(null),
  birthday: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().default(null),
  bio: z.string().max(500).nullable().default(null).optional(),
  location: z.unknown().nullable().default(null).optional(),
  interests: z.array(z.enum(["Weightlifting", "Powerlifting", "Bodybuilding", "Strongman", "Olympic Lifting", "Calisthenics", "CrossFit", "Running", "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing", "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai", "Yoga", "Pilates", "Stretching", "Mobility Work", "Hiking", "Rock Climbing", "Trail Running", "Obstacle Course Racing", "Functional Fitness", "Basketball", "Soccer", "Tennis", "Volleyball", "Pickleball", "Flag Football"])).max(20).nullable().optional(),
  fitnessLevel: z.enum(["novice", "intermediate", "experienced", "pro", "olympian"]).nullable().optional(),
});
export type CreateProfile = z.infer<typeof CreateProfileSchema>;

export const CreateProfileFields: FieldMeta[] = [
  {
    name: "username",
    label: "Username",
    placeholder: "Enter username",
    type: "string",
    required: true,
    nullable: false,
    keyboard: "default",
    secure: false,
    multiline: false,
    minLength: 3,
    maxLength: 30,
    pattern: "^[a-zA-Z0-9_-]+$",
    description: "Unique username (alphanumeric, underscores, hyphens)",
  },
  {
    name: "displayName",
    label: "Display Name",
    placeholder: "Enter display name",
    type: "string",
    required: true,
    nullable: false,
    keyboard: "default",
    secure: false,
    multiline: false,
    minLength: 1,
    maxLength: 100,
    description: "User's display name",
  },
  {
    name: "profilePhoto",
    label: "Profile Photo",
    placeholder: "Enter profile photo",
    type: "string",
    required: true,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "URL to the user's profile photo in Firebase Storage",
  },
  {
    name: "birthday",
    label: "Birthday",
    placeholder: "Enter birthday",
    type: "string",
    required: true,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "User's date of birth (YYYY-MM-DD)",
  },
  {
    name: "bio",
    label: "Bio",
    placeholder: "Enter bio",
    type: "string",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: true,
    maxLength: 500,
    description: "Short biography",
  },
  {
    name: "location",
    label: "Location",
    placeholder: "Enter location",
    type: "object",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "User's geolocation for nearby search",
  },
  {
    name: "interests",
    label: "Interests",
    placeholder: "Enter interests",
    type: "array",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "Activity interests",
  },
  {
    name: "fitnessLevel",
    label: "Fitness Level",
    placeholder: "Enter fitness level",
    type: "string",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "Gym fitness experience level",
  }
];

/** Schema for updating an existing profile. All fields are optional — only provided fields are updated. */
export const UpdateProfileSchema = z.object({
  displayName: z.string().min(1).max(100).optional(),
  bio: z.string().max(500).nullable().default(null).optional(),
  birthday: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().default(null).optional(),
  profilePhoto: z.string().nullable().default(null).optional(),
  location: z.unknown().nullable().default(null).optional(),
  interests: z.array(z.enum(["Weightlifting", "Powerlifting", "Bodybuilding", "Strongman", "Olympic Lifting", "Calisthenics", "CrossFit", "Running", "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing", "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai", "Yoga", "Pilates", "Stretching", "Mobility Work", "Hiking", "Rock Climbing", "Trail Running", "Obstacle Course Racing", "Functional Fitness", "Basketball", "Soccer", "Tennis", "Volleyball", "Pickleball", "Flag Football"])).max(20).nullable().optional(),
  fitnessLevel: z.enum(["novice", "intermediate", "experienced", "pro", "olympian"]).nullable().optional(),
}).refine(
  (data) => Object.keys(data).filter((k) => data[k as keyof typeof data] !== undefined).length >= 1,
  { message: 'At least 1 field(s) must be provided' }
);
export type UpdateProfile = z.infer<typeof UpdateProfileSchema>;

export const UpdateProfileFields: FieldMeta[] = [
  {
    name: "displayName",
    label: "Display Name",
    placeholder: "Enter display name",
    type: "string",
    required: false,
    nullable: false,
    keyboard: "default",
    secure: false,
    multiline: false,
    minLength: 1,
    maxLength: 100,
    description: "User's display name",
  },
  {
    name: "bio",
    label: "Bio",
    placeholder: "Enter bio",
    type: "string",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: true,
    maxLength: 500,
    description: "Short biography",
  },
  {
    name: "birthday",
    label: "Birthday",
    placeholder: "Enter birthday",
    type: "string",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "User's date of birth (YYYY-MM-DD)",
  },
  {
    name: "profilePhoto",
    label: "Profile Photo",
    placeholder: "Enter profile photo",
    type: "string",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "URL to the user's profile photo in Firebase Storage",
  },
  {
    name: "location",
    label: "Location",
    placeholder: "Enter location",
    type: "object",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "User's geolocation for nearby search",
  },
  {
    name: "interests",
    label: "Interests",
    placeholder: "Enter interests",
    type: "array",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "Activity interests",
  },
  {
    name: "fitnessLevel",
    label: "Fitness Level",
    placeholder: "Enter fitness level",
    type: "string",
    required: false,
    nullable: true,
    keyboard: "default",
    secure: false,
    multiline: false,
    description: "Gym fitness experience level",
  }
];

/** Public-facing profile view. Excludes sensitive fields. */
export const PublicProfileSchema = z.object({
  id: z.string(),
  username: z.string().min(3).max(30).regex(/^[a-zA-Z0-9_-]+$/),
  displayName: z.string().min(1).max(100),
  bio: z.string().max(500).nullable().default(null).optional(),
  birthday: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().default(null).optional(),
  profilePhoto: z.string().nullable().default(null).optional(),
  location: z.unknown().nullable().default(null).optional(),
  interests: z.array(z.enum(["Weightlifting", "Powerlifting", "Bodybuilding", "Strongman", "Olympic Lifting", "Calisthenics", "CrossFit", "Running", "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing", "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai", "Yoga", "Pilates", "Stretching", "Mobility Work", "Hiking", "Rock Climbing", "Trail Running", "Obstacle Course Racing", "Functional Fitness", "Basketball", "Soccer", "Tennis", "Volleyball", "Pickleball", "Flag Football"])).max(20).nullable().optional(),
  fitnessLevel: z.enum(["novice", "intermediate", "experienced", "pro", "olympian"]).nullable().optional(),
});
export type PublicProfile = z.infer<typeof PublicProfileSchema>;

/** Full profile view for the authenticated owner. Includes all fields. */
export const PrivateProfileSchema = z.object({
  id: z.string(),
  username: z.string().min(3).max(30).regex(/^[a-zA-Z0-9_-]+$/),
  displayName: z.string().min(1).max(100),
  bio: z.string().max(500).nullable().default(null).optional(),
  birthday: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().default(null).optional(),
  profilePhoto: z.string().nullable().default(null).optional(),
  location: z.unknown().nullable().default(null).optional(),
  interests: z.array(z.enum(["Weightlifting", "Powerlifting", "Bodybuilding", "Strongman", "Olympic Lifting", "Calisthenics", "CrossFit", "Running", "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing", "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai", "Yoga", "Pilates", "Stretching", "Mobility Work", "Hiking", "Rock Climbing", "Trail Running", "Obstacle Course Racing", "Functional Fitness", "Basketball", "Soccer", "Tennis", "Volleyball", "Pickleball", "Flag Football"])).max(20).nullable().optional(),
  fitnessLevel: z.enum(["novice", "intermediate", "experienced", "pro", "olympian"]).nullable().optional(),
});
export type PrivateProfile = z.infer<typeof PrivateProfileSchema>;
