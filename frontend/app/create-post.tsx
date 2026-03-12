import { useState, useCallback } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { Button, GradientScreen, Input, Text, colors, spacing, radii, fontSizes, fonts } from '@/components/ui';
import {
  CreatePostSchema,
  ACTIVITY_TYPES,
  activityLabel,
  type ActivityType,
  type MediaItem,
} from '@/models/post';
import { isHealthAvailable, fetchRecentWorkouts, fetchBodyMetrics, type HealthWorkout } from '@/services/health';
import { getIdToken } from '@/services/auth';
import { uploadPostMedia } from '@/services/storage';
import { config } from '@/config';

export default function CreatePostScreen() {
  const router = useRouter();

  // ── media ──
  const [media, setMedia] = useState<(MediaItem & { localUri: string })[]>([]);
  const MAX_MEDIA = 10;

  const pickMedia = async (useCamera = false) => {
    if (media.length >= MAX_MEDIA) {
      Alert.alert('Limit Reached', `You can attach up to ${MAX_MEDIA} photos/videos.`);
      return;
    }

    // Check camera availability on simulator
    if (useCamera) {
      const available = await ImagePicker.getCameraPermissionsAsync();
      if (!available.canAskAgain && !available.granted) {
        Alert.alert('Camera Unavailable', 'Camera is not available on this device.');
        return;
      }
    }

    // Request permissions
    if (useCamera) {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Camera access is needed to take photos.');
        return;
      }
    } else {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Photo library access is needed to select media.');
        return;
      }
    }

    const opts: ImagePicker.ImagePickerOptions = {
      mediaTypes: ['images', 'videos'],
      allowsMultipleSelection: !useCamera,
      selectionLimit: MAX_MEDIA - media.length,
      quality: 0.8,
      videoMaxDuration: 60,
    };

    try {
      const result = useCamera
        ? await ImagePicker.launchCameraAsync(opts)
        : await ImagePicker.launchImageLibraryAsync(opts);

      if (result.canceled) return;

      const newItems = result.assets.map((asset) => ({
        url: asset.uri,
        mimeType: asset.mimeType ?? (asset.type === 'video' ? 'video/mp4' : 'image/jpeg'),
        localUri: asset.uri,
      }));

      setMedia((prev) => [...prev, ...newItems].slice(0, MAX_MEDIA));
    } catch {
      Alert.alert('Camera Unavailable', 'Camera is not available on this device (e.g. Simulator).');
    }
  };

  const removeMedia = (index: number) => {
    setMedia((prev) => prev.filter((_, i) => i !== index));
  };

  // ── text fields ──
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');

  // ── workout section ──
  const [showWorkout, setShowWorkout] = useState(false);
  const [activityType, setActivityType] = useState<ActivityType | null>(null);
  const [durationMin, setDurationMin] = useState('');
  const [calories, setCalories] = useState('');
  const [showActivityPicker, setShowActivityPicker] = useState(false);

  // ── apple health import ──
  const [healthWorkouts, setHealthWorkouts] = useState<HealthWorkout[]>([]);
  const [showHealthPicker, setShowHealthPicker] = useState(false);
  const [healthLoading, setHealthLoading] = useState(false);

  const handleImportHealth = async () => {
    setHealthLoading(true);
    try {
      const workouts = await fetchRecentWorkouts();
      if (workouts.length === 0) {
        Alert.alert('No Workouts', 'No recent workouts found in Apple Health.');
        return;
      }
      setHealthWorkouts(workouts);
      setShowHealthPicker(true);
    } catch (err: any) {
      Alert.alert('Health Error', err.message ?? 'Could not read workouts');
    } finally {
      setHealthLoading(false);
    }
  };

  const applyHealthWorkout = (w: HealthWorkout) => {
    setShowWorkout(true);
    setActivityType(w.activityType);
    setDurationMin(String(Math.round(w.durationSeconds / 60)));
    setCalories(w.caloriesBurned > 0 ? String(w.caloriesBurned) : '');
    setShowHealthPicker(false);
  };

  // ── body metrics section ──
  const [showMetrics, setShowMetrics] = useState(false);
  const [weightLbs, setWeightLbs] = useState('');
  const [bodyFat, setBodyFat] = useState('');
  const [metricsLoading, setMetricsLoading] = useState(false);

  const handleImportMetrics = async () => {
    setMetricsLoading(true);
    try {
      const metrics = await fetchBodyMetrics();
      if (!metrics) {
        Alert.alert('No Data', 'No body metrics found in Apple Health.');
        return;
      }
      setShowMetrics(true);
      if (metrics.weightLbs !== null) setWeightLbs(String(metrics.weightLbs));
      if (metrics.bodyFatPercentage !== null) setBodyFat(String(metrics.bodyFatPercentage));
    } catch (err: any) {
      Alert.alert('Health Error', err.message ?? 'Could not read body metrics');
    } finally {
      setMetricsLoading(false);
    }
  };

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const buildPayload = useCallback(() => {
    const data: Record<string, unknown> = {};
    if (title.trim()) data.title = title.trim();
    if (body.trim()) data.body = body.trim();
    if (media.length > 0) data.media = media.map(({ url, mimeType }) => ({ url, mimeType }));

    if (showWorkout && activityType) {
      const workout: Record<string, unknown> = { activityType };
      if (durationMin.trim()) workout.durationSeconds = Math.round(Number(durationMin) * 60);
      if (calories.trim()) workout.caloriesBurned = Number(calories);
      data.workout = workout;
    }

    if (showMetrics) {
      const metrics: Record<string, unknown> = {};
      if (weightLbs.trim()) metrics.weightLbs = Number(weightLbs);
      if (bodyFat.trim()) metrics.bodyFatPercentage = Number(bodyFat);
      if (Object.keys(metrics).length > 0) data.bodyMetrics = metrics;
    }

    return data;
  }, [title, body, media, showWorkout, activityType, durationMin, calories, showMetrics, weightLbs, bodyFat]);

  const handleSubmit = async () => {
    const data = buildPayload();

    // Upload media via backend API before validating
    // (replaces local file:// URIs with download URLs)
    let storagePostId: string | undefined;
    if (media.length > 0) {
      setLoading(true);
      try {
        const result = await uploadPostMedia(
          media.map((item) => ({ localUri: item.localUri, mimeType: item.mimeType })),
        );
        storagePostId = result.postId;
        data.media = result.media;
      } catch (err: any) {
        setLoading(false);
        Alert.alert('Upload Failed', err.message ?? 'Could not upload media');
        return;
      }
    }

    const result = CreatePostSchema.safeParse(data);

    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        const key = issue.path.join('.') || '_root';
        if (!fieldErrors[key]) fieldErrors[key] = issue.message;
      }
      setErrors(fieldErrors);
      setLoading(false);
      return;
    }

    setErrors({});
    setLoading(true);
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/posts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          ...result.data,
          ...(storagePostId ? { storagePostId } : {}),
        }),
      });

      if (!res.ok) {
        const resBody = await res.json().catch(() => ({}));
        throw new Error(resBody.detail ?? `Failed to create post (${res.status})`);
      }

      console.log('Post created');
      router.back();
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const hasContent =
    title.trim() ||
    body.trim() ||
    media.length > 0 ||
    (showWorkout && activityType) ||
    (showMetrics && (weightLbs.trim() || bodyFat.trim()));

  return (
    <GradientScreen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        {/* Header bar */}
        <View style={styles.headerBar}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerClose}>
            <Ionicons name="close" size={26} color={colors.foreground} />
          </Pressable>
          <Text variant="title" style={styles.headerTitle}>New Post</Text>
          <Pressable
            onPress={handleSubmit}
            disabled={!hasContent || loading}
            style={[styles.postBtn, (!hasContent || loading) && styles.postBtnDisabled]}
          >
            {loading ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.postBtnText}>Post</Text>
            )}
          </Pressable>
        </View>

        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {/* ── Composer area ── */}
          <View style={styles.composerCard}>
            <TextInput
              placeholder="Title (optional)"
              placeholderTextColor={colors.placeholder}
              value={title}
              onChangeText={setTitle}
              maxLength={200}
              style={styles.titleInput}
            />
            <TextInput
              placeholder="What's on your mind?"
              placeholderTextColor={colors.placeholder}
              value={body}
              onChangeText={setBody}
              multiline
              maxLength={5000}
              style={styles.bodyInput}
            />
            {errors._root && <Text style={styles.errorText}>{errors._root}</Text>}
          </View>

          {/* ── Media grid ── */}
          {media.length > 0 && (
            <View style={styles.mediaCard}>
              <View style={styles.mediaGrid}>
                {media.map((item, idx) => (
                  <View key={idx} style={styles.mediaThumbnailWrapper}>
                    <Image source={{ uri: item.localUri }} style={styles.mediaThumbnail} />
                    {item.mimeType.startsWith('video') && (
                      <View style={styles.videoOverlay}>
                        <Ionicons name="play-circle" size={32} color="#fff" />
                      </View>
                    )}
                    <Pressable style={styles.mediaRemove} onPress={() => removeMedia(idx)} hitSlop={8}>
                      <View style={styles.mediaRemoveBg}>
                        <Ionicons name="close" size={14} color="#fff" />
                      </View>
                    </Pressable>
                  </View>
                ))}
                {media.length < MAX_MEDIA && (
                  <Pressable style={styles.mediaAddBtn} onPress={() => pickMedia(false)}>
                    <Ionicons name="add" size={32} color={colors.mutedForeground} />
                  </Pressable>
                )}
              </View>
              <Text muted style={styles.mediaCount}>{media.length}/{MAX_MEDIA} items</Text>
            </View>
          )}

          {/* ── Workout section ── */}
          {showWorkout && (
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionIcon}>
                  <Ionicons name="barbell-outline" size={18} color={colors.primaryForeground} />
                </View>
                <Text style={styles.sectionTitle}>Workout</Text>
                {isHealthAvailable() && (
                  <Pressable
                    style={styles.healthButton}
                    onPress={handleImportHealth}
                    disabled={healthLoading}
                  >
                    {healthLoading ? (
                      <ActivityIndicator size="small" color={colors.primary} />
                    ) : (
                      <>
                        <Ionicons name="heart" size={14} color="#e74c3c" />
                        <Text style={styles.healthButtonText}>Health</Text>
                      </>
                    )}
                  </Pressable>
                )}
                <Pressable onPress={() => setShowWorkout(false)} hitSlop={8} style={styles.sectionClose}>
                  <Ionicons name="close-circle" size={22} color={colors.mutedForeground} />
                </Pressable>
              </View>

              {/* Activity type picker */}
              <Pressable
                style={styles.pickerButton}
                onPress={() => setShowActivityPicker((v) => !v)}
              >
                <View style={styles.pickerLeft}>
                  <Ionicons name="fitness-outline" size={16} color={activityType ? colors.foreground : colors.placeholder} />
                  <Text style={activityType ? styles.pickerText : styles.pickerPlaceholder}>
                    {activityType ? activityLabel(activityType) : 'Select activity type'}
                  </Text>
                </View>
                <Ionicons
                  name={showActivityPicker ? 'chevron-up' : 'chevron-down'}
                  size={18}
                  color={colors.mutedForeground}
                />
              </Pressable>
              {errors['workout.activityType'] && (
                <Text style={styles.errorText}>{errors['workout.activityType']}</Text>
              )}

              {showActivityPicker && (
                <View style={styles.pickerList}>
                  {ACTIVITY_TYPES.map((t) => (
                    <Pressable
                      key={t}
                      style={[
                        styles.pickerItem,
                        t === activityType && styles.pickerItemActive,
                      ]}
                      onPress={() => {
                        setActivityType(t);
                        setShowActivityPicker(false);
                      }}
                    >
                      <Text
                        style={[
                          styles.pickerItemText,
                          t === activityType && styles.pickerItemTextActive,
                        ]}
                      >
                        {activityLabel(t)}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              )}

              <View style={styles.row}>
                <View style={styles.halfField}>
                  <Input
                    label="Duration (min)"
                    placeholder="e.g. 45"
                    keyboardType="numeric"
                    value={durationMin}
                    onChangeText={setDurationMin}
                  />
                </View>
                <View style={styles.halfField}>
                  <Input
                    label="Calories"
                    placeholder="e.g. 350"
                    keyboardType="numeric"
                    value={calories}
                    onChangeText={setCalories}
                  />
                </View>
              </View>
            </View>
          )}

          {/* ── Body Metrics section ── */}
          {showMetrics && (
            <View style={styles.sectionCard}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionIcon}>
                  <Ionicons name="body-outline" size={18} color={colors.primaryForeground} />
                </View>
                <Text style={styles.sectionTitle}>Body Metrics</Text>
                {isHealthAvailable() && (
                  <Pressable
                    style={styles.healthButton}
                    onPress={handleImportMetrics}
                    disabled={metricsLoading}
                  >
                    {metricsLoading ? (
                      <ActivityIndicator size="small" color={colors.primary} />
                    ) : (
                      <>
                        <Ionicons name="heart" size={14} color="#e74c3c" />
                        <Text style={styles.healthButtonText}>Health</Text>
                      </>
                    )}
                  </Pressable>
                )}
                <Pressable onPress={() => setShowMetrics(false)} hitSlop={8} style={styles.sectionClose}>
                  <Ionicons name="close-circle" size={22} color={colors.mutedForeground} />
                </Pressable>
              </View>
              <View style={styles.row}>
                <View style={styles.halfField}>
                  <Input
                    label="Weight (lbs)"
                    placeholder="e.g. 185"
                    keyboardType="numeric"
                    value={weightLbs}
                    onChangeText={setWeightLbs}
                  />
                </View>
                <View style={styles.halfField}>
                  <Input
                    label="Body Fat %"
                    placeholder="e.g. 15"
                    keyboardType="numeric"
                    value={bodyFat}
                    onChangeText={setBodyFat}
                  />
                </View>
              </View>
            </View>
          )}
        </ScrollView>

        {/* ── Attachment bar ── */}
        <View style={styles.attachBar}>
          <AttachButton icon="images-outline" label="Gallery" onPress={() => pickMedia(false)} />
          <AttachButton icon="camera-outline" label="Camera" onPress={() => pickMedia(true)} />
          <AttachButton
            icon="barbell-outline"
            label="Workout"
            active={showWorkout}
            onPress={() => setShowWorkout((v) => !v)}
          />
          <AttachButton
            icon="body-outline"
            label="Metrics"
            active={showMetrics}
            onPress={() => setShowMetrics((v) => !v)}
          />
        </View>
      </KeyboardAvoidingView>

      {/* ── Health workout picker modal ── */}
      <Modal
        visible={showHealthPicker}
        animationType="slide"
        presentationStyle="fullScreen"
        onRequestClose={() => setShowHealthPicker(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={styles.headerBar}>
            <Pressable onPress={() => setShowHealthPicker(false)} hitSlop={12}>
              <Ionicons name="close" size={28} color={colors.foreground} />
            </Pressable>
            <Text variant="title" style={styles.headerTitle}>Select Workout</Text>
            <View style={{ width: 28 }} />
          </View>
          <ScrollView contentContainerStyle={styles.scrollContent}>
            {healthWorkouts.map((w, i) => (
              <Pressable
                key={i}
                style={styles.healthWorkoutItem}
                onPress={() => applyHealthWorkout(w)}
              >
                <Ionicons name="barbell-outline" size={20} color={colors.primary} />
                <View style={styles.healthWorkoutInfo}>
                  <Text style={styles.healthWorkoutLabel}>{w.label}</Text>
                  <Text muted style={styles.healthWorkoutDate}>
                    {w.startDate.toLocaleDateString(undefined, {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.mutedForeground} />
              </Pressable>
            ))}
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </GradientScreen>
  );
}

/* ── Attachment bar button ── */
function AttachButton({
  icon,
  label,
  active,
  onPress,
}: {
  icon: string;
  label: string;
  active?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable style={styles.attachBtn} onPress={onPress}>
      <View style={[styles.attachIconWrap, active && styles.attachIconActive]}>
        <Ionicons
          name={icon as any}
          size={20}
          color={active ? colors.primaryForeground : colors.mutedForeground}
        />
      </View>
      <Text style={[styles.attachLabel, active && styles.attachLabelActive]}>{label}</Text>
    </Pressable>
  );
}

const THUMB_SIZE = 100;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  flex: {
    flex: 1,
  },
  headerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerClose: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: fontSizes.lg,
  },
  postBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 20,
    minWidth: 70,
    alignItems: 'center',
  },
  postBtnDisabled: {
    opacity: 0.35,
  },
  postBtnText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
  scrollContent: {
    padding: spacing.lg,
    gap: spacing.md,
    paddingBottom: 100,
  },

  // Composer card
  composerCard: {
    backgroundColor: colors.muted,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  titleInput: {
    fontSize: fontSizes.lg,
    ...fonts.semibold,
    color: colors.foreground,
    paddingVertical: spacing.xs,
  },
  bodyInput: {
    fontSize: fontSizes.base,
    color: colors.foreground,
    minHeight: 100,
    textAlignVertical: 'top',
    paddingVertical: spacing.xs,
    lineHeight: 22,
  },
  errorText: {
    color: colors.destructive,
    fontSize: fontSizes.sm,
    marginTop: 2,
  },

  // Media
  mediaCard: {
    backgroundColor: colors.muted,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  mediaGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  mediaThumbnailWrapper: {
    position: 'relative',
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: radii.md,
    overflow: 'hidden',
  },
  mediaThumbnail: {
    width: '100%',
    height: '100%',
  },
  videoOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  mediaRemove: {
    position: 'absolute',
    top: 4,
    right: 4,
  },
  mediaRemoveBg: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  mediaAddBtn: {
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: radii.md,
    borderWidth: 2,
    borderColor: colors.border,
    borderStyle: 'dashed',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
  },
  mediaCount: {
    fontSize: fontSizes.xs,
    textAlign: 'right',
  },

  // Attachment bar
  attachBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.1)',
    backgroundColor: 'transparent',
  },
  attachBtn: {
    alignItems: 'center',
    gap: 2,
  },
  attachIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'transparent',
  },
  attachIconActive: {
    backgroundColor: colors.primary,
  },
  attachLabel: {
    fontSize: 11,
    color: colors.mutedForeground,
    ...fonts.medium,
  },
  attachLabelActive: {
    color: colors.primary,
    ...fonts.semibold,
  },

  // Section cards
  sectionCard: {
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.muted,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  sectionIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sectionTitle: {
    flex: 1,
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  sectionClose: {
    marginLeft: spacing.xs,
  },
  healthButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm + 2,
    borderRadius: 16,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
  },
  healthButtonText: {
    fontSize: fontSizes.xs,
    ...fonts.semibold,
    color: colors.foreground,
  },
  healthWorkoutItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.muted,
  },
  healthWorkoutInfo: {
    flex: 1,
    gap: 2,
  },
  healthWorkoutLabel: {
    fontSize: fontSizes.base,
    ...fonts.medium,
    color: colors.foreground,
  },
  healthWorkoutDate: {
    fontSize: fontSizes.sm,
  },
  row: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  halfField: {
    flex: 1,
  },
  pickerButton: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    height: 48,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.background,
  },
  pickerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  pickerText: {
    fontSize: fontSizes.base,
    color: colors.foreground,
  },
  pickerPlaceholder: {
    fontSize: fontSizes.base,
    color: colors.placeholder,
  },
  pickerList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  pickerItem: {
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.sm + 2,
    borderRadius: 16,
    backgroundColor: colors.background,
  },
  pickerItemActive: {
    backgroundColor: colors.primary,
  },
  pickerItemText: {
    fontSize: fontSizes.sm,
    color: colors.foreground,
  },
  pickerItemTextActive: {
    color: colors.primaryForeground,
    ...fonts.semibold,
  },
});
