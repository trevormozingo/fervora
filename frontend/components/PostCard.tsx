import { useState, useEffect, useRef, useCallback } from 'react';
import { ActivityIndicator, Alert, Animated, Dimensions, Image, Modal, PanResponder, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { Text, colors, spacing, radii, fontSizes, fonts } from '@/components/ui';
import { activityLabel, type ActivityType } from '@/models/post';
import { getIdToken, getUid } from '@/services/auth';
import { config } from '@/config';

// ── Shared types ────────────────────────────────────────────────────

export type Comment = {
  id: string;
  authorUid: string;
  authorUsername?: string;
  authorProfilePhoto?: string | null;
  body: string;
  createdAt: string;
};

export type Post = {
  id: string;
  authorUid: string;
  authorUsername?: string;
  authorProfilePhoto?: string | null;
  title?: string | null;
  body?: string | null;
  media?: { url: string; mimeType: string }[] | null;
  workout?: {
    activityType: ActivityType;
    durationSeconds?: number | null;
    caloriesBurned?: number | null;
    distanceMiles?: number | null;
    avgHeartRate?: number | null;
    maxHeartRate?: number | null;
    elevationFeet?: number | null;
  } | null;
  bodyMetrics?: {
    weightLbs?: number | null;
    bodyFatPercentage?: number | null;
    restingHeartRate?: number | null;
    leanBodyMassLbs?: number | null;
  } | null;
  reactionSummary?: Record<string, number>;
  recentComments?: Comment[];
  commentCount?: number;
  myReaction?: string | null;
  createdAt: string;
};

// ── Activity icon mapping ────────────────────────────────────────────

const ACTIVITY_ICON: Record<string, string> = {
  running: 'walk-outline',
  cycling: 'bicycle-outline',
  swimming: 'water-outline',
  weightlifting: 'barbell-outline',
  crossfit: 'flame-outline',
  yoga: 'leaf-outline',
  pilates: 'body-outline',
  hiking: 'trail-sign-outline',
  rowing: 'boat-outline',
  boxing: 'hand-left-outline',
  martial_arts: 'hand-left-outline',
  climbing: 'trending-up-outline',
  dance: 'musical-notes-outline',
  stretching: 'body-outline',
  cardio: 'heart-outline',
  hiit: 'flash-outline',
  walking: 'footsteps-outline',
  sports: 'football-outline',
  other: 'fitness-outline',
};

// ── Constants ───────────────────────────────────────────────────────

export const REACTION_EMOJI: Record<string, string> = {
  strong: '💪',
  fire: '🔥',
  heart: '❤️',
  smile: '😊',
  laugh: '😂',
  thumbsup: '👍',
  thumbsdown: '👎',
  angry: '😡',
};

const REACTION_TYPES = ['strong', 'fire', 'heart', 'smile', 'laugh', 'thumbsup', 'thumbsdown', 'angry'] as const;

// ── Animated bubble for staggered pop-in ────────────────────────────

function ReactionBubble({
  type,
  emoji,
  index,
  isSelected,
  onPress,
}: {
  type: string;
  emoji: string;
  index: number;
  isSelected: boolean;
  onPress: (type: string) => void;
}) {
  const scale = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(scale, {
      toValue: 1,
      delay: index * 40,
      friction: 5,
      tension: 160,
      useNativeDriver: true,
    }).start();
  }, []);

  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        onPress={() => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
          onPress(type);
        }}
        style={({ pressed }) => [
          styles.bubbleItem,
          isSelected && styles.bubbleItemSelected,
          pressed && { transform: [{ scale: 1.25 }] },
        ]}
      >
        <Text style={styles.bubbleEmoji}>{emoji}</Text>
      </Pressable>
    </Animated.View>
  );
}

// ── Lightbox with pinch-zoom, rotation & pan ───────────────────────

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

function LightboxViewer({ images, initialIndex, onClose }: { images: { url: string }[]; initialIndex: number; onClose: () => void }) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const uri = images[currentIndex].url;

  const scale = useRef(new Animated.Value(1)).current;
  const rotation = useRef(new Animated.Value(0)).current;
  const translateX = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(0)).current;

  const baseScale = useRef(1);
  const baseRotation = useRef(0);
  const baseTranslateX = useRef(0);
  const baseTranslateY = useRef(0);
  const lastDistance = useRef(0);
  const lastAngle = useRef(0);

  const resetTransform = useCallback(() => {
    scale.setValue(1);
    rotation.setValue(0);
    translateX.setValue(0);
    translateY.setValue(0);
    baseScale.current = 1;
    baseRotation.current = 0;
    baseTranslateX.current = 0;
    baseTranslateY.current = 0;
  }, []);

  const goNext = useCallback(() => {
    if (currentIndex < images.length - 1) {
      resetTransform();
      setCurrentIndex(currentIndex + 1);
    }
  }, [currentIndex, images.length]);

  const goPrev = useCallback(() => {
    if (currentIndex > 0) {
      resetTransform();
      setCurrentIndex(currentIndex - 1);
    }
  }, [currentIndex]);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,

      onPanResponderGrant: () => {
        baseScale.current = (scale as any).__getValue();
        baseRotation.current = (rotation as any).__getValue();
        baseTranslateX.current = (translateX as any).__getValue();
        baseTranslateY.current = (translateY as any).__getValue();
        lastDistance.current = 0;
        lastAngle.current = 0;
      },

      onPanResponderMove: (_, gestureState) => {
        const { numberActiveTouches } = gestureState;

        if (numberActiveTouches === 2) {
          // Handled by onTouchMove below
        } else if (numberActiveTouches === 1) {
          const isZoomed = (scale as any).__getValue() > 1.05;
          if (isZoomed) {
            translateX.setValue(baseTranslateX.current + gestureState.dx);
            translateY.setValue(baseTranslateY.current + gestureState.dy);
          }
        }
      },

      onPanResponderRelease: (_, gestureState) => {
        const currentScale = (scale as any).__getValue();

        if (currentScale < 1) {
          Animated.parallel([
            Animated.spring(scale, { toValue: 1, useNativeDriver: true }),
            Animated.spring(rotation, { toValue: 0, useNativeDriver: true }),
            Animated.spring(translateX, { toValue: 0, useNativeDriver: true }),
            Animated.spring(translateY, { toValue: 0, useNativeDriver: true }),
          ]).start();
          baseScale.current = 1;
          baseRotation.current = 0;
        }
      },
    }),
  ).current;

  // Use onTouchMove for multi-touch pinch/rotate (PanResponder gestureState
  // doesn't expose individual touch coordinates reliably)
  const handleTouchMove = useCallback(
    (e: any) => {
      const touches = e.nativeEvent.touches;
      if (touches.length === 2) {
        const [t1, t2] = touches;
        const dx = t1.pageX - t2.pageX;
        const dy = t1.pageY - t2.pageY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const angle = Math.atan2(dy, dx);

        if (lastDistance.current > 0) {
          const dScale = distance / lastDistance.current;
          const newScale = Math.max(0.5, Math.min(baseScale.current * dScale, 5));
          scale.setValue(newScale);

          const dAngle = angle - lastAngle.current;
          rotation.setValue(baseRotation.current + dAngle);
        } else {
          lastDistance.current = distance;
          lastAngle.current = angle;
          baseScale.current = (scale as any).__getValue();
          baseRotation.current = (rotation as any).__getValue();
        }
        lastDistance.current = distance;
        lastAngle.current = angle;
      }
    },
    [],
  );

  const handleTouchEnd = useCallback(() => {
    lastDistance.current = 0;
    lastAngle.current = 0;
  }, []);

  const handleDoubleTap = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handlePress = useCallback(() => {
    if (handleDoubleTap.current) {
      clearTimeout(handleDoubleTap.current);
      handleDoubleTap.current = null;
      // Double tap → reset
      Animated.parallel([
        Animated.spring(scale, { toValue: 1, useNativeDriver: true }),
        Animated.spring(rotation, { toValue: 0, useNativeDriver: true }),
        Animated.spring(translateX, { toValue: 0, useNativeDriver: true }),
        Animated.spring(translateY, { toValue: 0, useNativeDriver: true }),
      ]).start();
    } else {
      handleDoubleTap.current = setTimeout(() => {
        handleDoubleTap.current = null;
      }, 300);
    }
  }, []);

  const rotationStr = rotation.interpolate({
    inputRange: [-Math.PI, Math.PI],
    outputRange: ['-180deg', '180deg'],
  });

  return (
    <View
      style={styles.lightboxBackdrop}
      {...panResponder.panHandlers}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      <Animated.Image
        source={{ uri }}
        style={[
          styles.lightboxImage,
          {
            transform: [
              { translateX },
              { translateY },
              { scale },
              { rotate: rotationStr },
            ],
          },
        ]}
        resizeMode="contain"
      />
      <Pressable style={styles.lightboxClose} onPress={onClose} hitSlop={16}>
        <Ionicons name="close" size={28} color="#fff" />
      </Pressable>
      {/* Navigation arrows */}
      {images.length > 1 && (
        <>
          {currentIndex > 0 && (
            <Pressable style={styles.lightboxArrowLeft} onPress={goPrev} hitSlop={20}>
              <Ionicons name="chevron-back" size={32} color="#fff" />
            </Pressable>
          )}
          {currentIndex < images.length - 1 && (
            <Pressable style={styles.lightboxArrowRight} onPress={goNext} hitSlop={20}>
              <Ionicons name="chevron-forward" size={32} color="#fff" />
            </Pressable>
          )}
          <View style={styles.lightboxDots}>
            {images.map((_, i) => (
              <View
                key={i}
                style={[
                  styles.lightboxDot,
                  i === currentIndex && styles.lightboxDotActive,
                ]}
              />
            ))}
          </View>
        </>
      )}
    </View>
  );
}

// ── Props ───────────────────────────────────────────────────────────

type PostCardProps = {
  post: Post;
  /** Show author name above the card (for feed). Hidden on own-profile view. */
  showAuthor?: boolean;
  /** Called after the post is mutated (reaction/comment add/delete) so the parent can update state. */
  onPostChanged: (updated: Post) => void;
  /** Called when the user confirms post deletion. */
  onDeletePost?: (postId: string) => void;
  /** Auto-open this section when the card mounts */
  initialSection?: 'comments' | 'reactions' | null;
  /** Which specific reaction type to filter to */
  initialReactionType?: string;
};

// ── Component ───────────────────────────────────────────────────────

type ReactionUser = { authorUid: string; username: string; type: string; profilePhoto?: string | null };

export function PostCard({ post, showAuthor, onPostChanged, onDeletePost, initialSection, initialReactionType }: PostCardProps) {
  const router = useRouter();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [reactionUsersOpen, setReactionUsersOpen] = useState(false);
  const [reactionUsers, setReactionUsers] = useState<ReactionUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [selectedReactionType, setSelectedReactionType] = useState<string | null>(null);
  const [allCommentsLoaded, setAllCommentsLoaded] = useState(false);
  const [loadingComments, setLoadingComments] = useState(false);
  const [commentCursor, setCommentCursor] = useState<string | null>(null);
  const [lightboxUri, setLightboxUri] = useState<string | null>(null);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const prevInitialSection = useRef(initialSection);

  const isOwner = post.authorUid === getUid();

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };

  // ── Reactions ─────────────────────────────────────────────────────

  const handleReact = async (type: string) => {
    setPickerOpen(false);
    const oldReaction = post.myReaction;
    const isToggleOff = oldReaction === type;

    // Optimistic update
    const summary = { ...(post.reactionSummary ?? {}) };
    if (oldReaction && summary[oldReaction]) {
      summary[oldReaction] -= 1;
      if (summary[oldReaction] <= 0) delete summary[oldReaction];
    }
    if (!isToggleOff) {
      summary[type] = (summary[type] ?? 0) + 1;
    }
    onPostChanged({ ...post, reactionSummary: summary, myReaction: isToggleOff ? null : type });

    try {
      const token = getIdToken();
      if (isToggleOff) {
        await fetch(`${config.apiBaseUrl}/posts/${post.id}/reactions`, {
          method: 'DELETE',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
      } else {
        await fetch(`${config.apiBaseUrl}/posts/${post.id}/reactions`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ type }),
        });
      }
    } catch {
      // Revert
      const reverted = { ...(post.reactionSummary ?? {}) };
      onPostChanged({ ...post, reactionSummary: reverted, myReaction: oldReaction ?? null });
      Alert.alert('Error', 'Failed to react');
    }
  };

  // ── Reaction users ────────────────────────────────────────────────

  const fetchReactionUsers = async (type?: string) => {
    // If tapping the same type again, close it
    if (reactionUsersOpen && selectedReactionType === (type ?? null)) {
      setReactionUsersOpen(false);
      setSelectedReactionType(null);
      return;
    }
    setSelectedReactionType(type ?? null);
    setReactionUsersOpen(true);
    setLoadingUsers(true);
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/posts/${post.id}/reactions`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        const all: ReactionUser[] = data.reactions;
        setReactionUsers(type ? all.filter((r) => r.type === type) : all);
      }
    } catch {
      // ignore
    } finally {
      setLoadingUsers(false);
    }
  };

  // Auto-open comments or reactions when navigated from a notification
  useEffect(() => {
    if (!initialSection || initialSection === prevInitialSection.current) return;
    prevInitialSection.current = initialSection;
    if (initialSection === 'comments') {
      setCommentOpen(true);
      fetchMoreComments();
    } else if (initialSection === 'reactions') {
      setPickerOpen(true);
      fetchReactionUsers(initialReactionType);
    }
  }, [initialSection]);

  // Also handle initial mount
  useEffect(() => {
    if (initialSection === 'comments') {
      setCommentOpen(true);
      fetchMoreComments();
    } else if (initialSection === 'reactions') {
      setPickerOpen(true);
      fetchReactionUsers(initialReactionType);
    }
  }, []);

  // ── Comments ──────────────────────────────────────────────────────

  const handleComment = async () => {
    const text = commentText.trim();
    if (!text) return;
    setCommentText('');
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/posts/${post.id}/comments`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ body: text }),
      });
      if (res.ok) {
        const newComment = await res.json();
        onPostChanged({
          ...post,
          recentComments: [...(post.recentComments ?? []), newComment],
          commentCount: (post.commentCount ?? 0) + 1,
        });
      }
    } catch {
      Alert.alert('Error', 'Failed to comment');
    }
  };

  const handleDeleteComment = (commentId: string) => {
    Alert.alert('Delete Comment', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            const token = getIdToken();
            const res = await fetch(
              `${config.apiBaseUrl}/posts/${post.id}/comments/${commentId}`,
              { method: 'DELETE', headers: token ? { Authorization: `Bearer ${token}` } : {} },
            );
            if (res.ok || res.status === 204) {
              onPostChanged({
                ...post,
                recentComments: (post.recentComments ?? []).filter((c) => c.id !== commentId),
                commentCount: Math.max((post.commentCount ?? 1) - 1, 0),
              });
            } else {
              Alert.alert('Error', 'Failed to delete comment');
            }
          } catch {
            Alert.alert('Error', 'Something went wrong');
          }
        },
      },
    ]);
  };

  const handleDeletePost = () => {
    if (!onDeletePost) return;
    Alert.alert('Delete Post', 'Are you sure you want to delete this post?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => onDeletePost(post.id),
      },
    ]);
  };

  const fetchMoreComments = async () => {
    if (loadingComments) return;
    setLoadingComments(true);
    try {
      const token = getIdToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const params = new URLSearchParams({ limit: '10' });
      if (commentCursor) params.set('cursor', commentCursor);
      const res = await fetch(`${config.apiBaseUrl}/posts/${post.id}/comments?${params}`, { headers });
      if (res.ok) {
        const data = await res.json();
        const existing = post.recentComments ?? [];
        // On first load replace the preview; on subsequent loads append
        const merged = commentCursor ? [...existing, ...data.items] : data.items;
        onPostChanged({ ...post, recentComments: merged });
        if (data.count < 10) {
          setAllCommentsLoaded(true);
          setCommentCursor(null);
        } else {
          setCommentCursor(data.cursor);
        }
      }
    } catch {
      // ignore
    } finally {
      setLoadingComments(false);
    }
  };

  // ── Derived counts ─────────────────────────────────────────────────

  const totalReactions = Object.values(post.reactionSummary ?? {}).reduce((a, b) => a + b, 0);
  const commentCount = post.commentCount ?? 0;
  const reactionsExpanded = pickerOpen;
  const commentsExpanded = commentOpen;

  // ── Render ────────────────────────────────────────────────────────

  return (
    <View style={styles.card}>
      {/* Header: author (feed) + 3-dot menu (own posts) */}
      <View style={styles.header}>
        {showAuthor ? (
          <Pressable style={styles.authorRow} onPress={() => router.push(`/user/${post.authorUsername}` as any)}>
            {post.authorProfilePhoto ? (
              <Image source={{ uri: post.authorProfilePhoto }} style={styles.authorAvatar} />
            ) : (
              <View style={styles.authorAvatarFallback}>
                <Text style={styles.authorAvatarText}>
                  {(post.authorUsername ?? '?').charAt(0).toUpperCase()}
                </Text>
              </View>
            )}
            <Text style={styles.authorName}>{post.authorUsername ?? post.authorUid}</Text>
          </Pressable>
        ) : (
          <View style={{ flex: 1 }} />
        )}
        {isOwner && onDeletePost && (
          <Pressable
            onPress={handleDeletePost}
            hitSlop={12}
          >
            <Ionicons name="ellipsis-horizontal" size={20} color={colors.mutedForeground} />
          </Pressable>
        )}
      </View>

      {/* ── Workout hero ── */}
      {post.workout && (
        <LinearGradient
          colors={[colors.brandPurple, colors.brandPink, colors.brandRed]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.workoutHero}
        >
          <View style={styles.workoutHeaderRow}>
            <View style={styles.workoutIconCircle}>
              <Ionicons name={(ACTIVITY_ICON[post.workout.activityType] ?? 'fitness-outline') as any} size={20} color={colors.primaryForeground} />
            </View>
            <Text style={styles.workoutActivity}>{activityLabel(post.workout.activityType)}</Text>
          </View>
          {(post.workout.durationSeconds || post.workout.caloriesBurned || post.workout.distanceMiles || post.workout.avgHeartRate || post.workout.elevationFeet) && (
            <View style={styles.workoutStats}>
              {post.workout.durationSeconds != null && (
                <View style={styles.workoutStat}>
                  <Text style={styles.workoutStatValue}>{Math.round(post.workout.durationSeconds / 60)}</Text>
                  <Text style={styles.workoutStatLabel}>min</Text>
                </View>
              )}
              {post.workout.durationSeconds != null && post.workout.caloriesBurned != null && (
                <View style={styles.workoutStatDivider} />
              )}
              {post.workout.caloriesBurned != null && (
                <View style={styles.workoutStat}>
                  <Text style={styles.workoutStatValue}>{post.workout.caloriesBurned}</Text>
                  <Text style={styles.workoutStatLabel}>cal</Text>
                </View>
              )}
              {post.workout.distanceMiles != null && (
                <>
                  <View style={styles.workoutStatDivider} />
                  <View style={styles.workoutStat}>
                    <Text style={styles.workoutStatValue}>{post.workout.distanceMiles}</Text>
                    <Text style={styles.workoutStatLabel}>mi</Text>
                  </View>
                </>
              )}
              {post.workout.avgHeartRate != null && (
                <>
                  <View style={styles.workoutStatDivider} />
                  <View style={styles.workoutStat}>
                    <Text style={styles.workoutStatValue}>{post.workout.avgHeartRate}</Text>
                    <Text style={styles.workoutStatLabel}>avg bpm</Text>
                  </View>
                </>
              )}
              {post.workout.elevationFeet != null && (
                <>
                  <View style={styles.workoutStatDivider} />
                  <View style={styles.workoutStat}>
                    <Text style={styles.workoutStatValue}>{post.workout.elevationFeet}</Text>
                    <Text style={styles.workoutStatLabel}>ft elev</Text>
                  </View>
                </>
              )}
            </View>
          )}
        </LinearGradient>
      )}

      {/* ── Body Metrics ── */}
      {post.bodyMetrics && (
        <LinearGradient
          colors={['#1B2838', '#2C3E50', '#34495E']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.metricsHero}
        >
          <View style={styles.metricsHeaderRow}>
            <View style={styles.metricsIconCircle}>
              <Ionicons name="body-outline" size={20} color={colors.primaryForeground} />
            </View>
            <Text style={styles.metricsTitle}>Body Stats</Text>
          </View>
          <View style={styles.metricsStats}>
            {post.bodyMetrics.weightLbs != null && (
              <View style={styles.workoutStat}>
                <Text style={styles.workoutStatValue}>{post.bodyMetrics.weightLbs}</Text>
                <Text style={styles.workoutStatLabel}>lbs</Text>
              </View>
            )}
            {post.bodyMetrics.weightLbs != null && post.bodyMetrics.bodyFatPercentage != null && (
              <View style={styles.workoutStatDivider} />
            )}
            {post.bodyMetrics.bodyFatPercentage != null && (
              <View style={styles.workoutStat}>
                <Text style={styles.workoutStatValue}>{post.bodyMetrics.bodyFatPercentage}%</Text>
                <Text style={styles.workoutStatLabel}>body fat</Text>
              </View>
            )}
            {post.bodyMetrics.restingHeartRate != null && (
              <>
                <View style={styles.workoutStatDivider} />
                <View style={styles.workoutStat}>
                  <Text style={styles.workoutStatValue}>{post.bodyMetrics.restingHeartRate}</Text>
                  <Text style={styles.workoutStatLabel}>rhr</Text>
                </View>
              </>
            )}
            {post.bodyMetrics.leanBodyMassLbs != null && (
              <>
                <View style={styles.workoutStatDivider} />
                <View style={styles.workoutStat}>
                  <Text style={styles.workoutStatValue}>{post.bodyMetrics.leanBodyMassLbs}</Text>
                  <Text style={styles.workoutStatLabel}>lbs lean</Text>
                </View>
              </>
            )}
          </View>
        </LinearGradient>
      )}

      {/* Title */}
      {post.title && <Text style={styles.title}>{post.title}</Text>}

      {/* Body */}
      {post.body && <Text style={styles.body} numberOfLines={4}>{post.body}</Text>}

      {/* Media — compact thumbnails */}
      {post.media && post.media.length > 0 && (
        <View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.mediaStrip}
          >
            {post.media.map((m, i) => (
              <Pressable key={i} onPress={() => { setLightboxIndex(i); setLightboxUri(m.url); }}>
                <Image
                  source={{ uri: m.url }}
                  style={[
                    styles.mediaThumb,
                    post.media!.length === 1 && styles.mediaThumbSingle,
                  ]}
                  resizeMode="cover"
                />
              </Pressable>
            ))}
          </ScrollView>
        </View>
      )}

      {/* Lightbox modal with pinch-zoom, rotation & swipe between photos */}
      <Modal visible={!!lightboxUri} transparent animationType="fade" onRequestClose={() => setLightboxUri(null)}>
        {lightboxUri && post.media && (
          <LightboxViewer images={post.media} initialIndex={lightboxIndex} onClose={() => setLightboxUri(null)} />
        )}
      </Modal>

      {/* Date */}
      <Text muted style={styles.date}>{formatDate(post.createdAt)}</Text>

      {/* ── Action bar (collapsed icons with counts) ─────────────── */}
      <View style={styles.actionBar}>
        {/* React button */}
        <Pressable
          style={styles.actionButton}
          onPress={() => { setPickerOpen(!pickerOpen); setCommentOpen(false); }}
        >
          {post.myReaction ? (
            <Text style={{ fontSize: 18 }}>{REACTION_EMOJI[post.myReaction]}</Text>
          ) : (
            <Ionicons name="happy-outline" size={18} color={colors.mutedForeground} />
          )}
          {totalReactions > 0 && (
            <Text style={[styles.actionCount, post.myReaction && { color: colors.primary }]}>
              {totalReactions}
            </Text>
          )}
        </Pressable>

        {/* Comment button */}
        <Pressable
          style={styles.actionButton}
          onPress={() => { setCommentOpen(!commentOpen); setPickerOpen(false); setCommentText(''); }}
        >
          <Ionicons
            name={commentsExpanded ? 'chatbubble' : 'chatbubble-outline'}
            size={16}
            color={commentsExpanded ? colors.primary : colors.mutedForeground}
          />
          {commentCount > 0 && (
            <Text style={[styles.actionCount, commentsExpanded && { color: colors.primary }]}>
              {commentCount}
            </Text>
          )}
        </Pressable>
      </View>

      {/* ── Expanded: Reactions ──────────────────────────────────── */}
      {reactionsExpanded && (
        <View style={styles.reactionsExpanded}>
          {/* Summary badges — tap one to see who reacted with that emoji */}
          {post.reactionSummary && Object.keys(post.reactionSummary).length > 0 && (
            <View style={styles.reactionsRow}>
              {Object.entries(post.reactionSummary).map(([type, count]) => (
                <Pressable key={type} onPress={() => fetchReactionUsers(type)}>
                  <View style={[styles.reactionBadge, selectedReactionType === type && reactionUsersOpen && styles.reactionBadgeSelected]}>
                    <Text style={styles.reactionEmoji}>{REACTION_EMOJI[type] ?? type}</Text>
                    <Text style={styles.reactionCount}>{count}</Text>
                  </View>
                </Pressable>
              ))}
            </View>
          )}
          {/* Who reacted */}
          {reactionUsersOpen && (
            <View style={styles.reactionUsersList}>
              {loadingUsers ? (
                <ActivityIndicator size="small" color={colors.primary} />
              ) : (
                reactionUsers.map((r, i) => (
                  <Pressable key={`${r.authorUid}-${i}`} style={styles.reactionUserRow} onPress={() => router.push(`/user/${r.username}` as any)}>
                    <Text style={styles.reactionUserEmoji}>{REACTION_EMOJI[r.type] ?? r.type}</Text>
                    {r.profilePhoto ? (
                      <Image source={{ uri: r.profilePhoto }} style={styles.reactionUserAvatar} />
                    ) : (
                      <View style={styles.reactionUserAvatarFallback}>
                        <Text style={styles.reactionUserAvatarText}>
                          {r.username.charAt(0).toUpperCase()}
                        </Text>
                      </View>
                    )}
                    <Text style={styles.reactionUserName}>{r.username}</Text>
                  </Pressable>
                ))
              )}
            </View>
          )}
          {/* Bubble picker */}
          <View style={styles.bubblePicker}>
            {REACTION_TYPES.map((type, i) => (
              <ReactionBubble
                key={type}
                type={type}
                emoji={REACTION_EMOJI[type]}
                index={i}
                isSelected={post.myReaction === type}
                onPress={handleReact}
              />
            ))}
          </View>
        </View>
      )}

      {/* ── Expanded: Comments ───────────────────────────────────── */}
      {commentsExpanded && (
        <View style={styles.commentsExpanded}>
          {/* Comment list */}
          {post.recentComments && post.recentComments.length > 0 && (
            <View style={styles.commentsSection}>
              {post.recentComments.map((c) => (
                <Pressable
                  key={c.id}
                  onLongPress={() => {
                    if (c.authorUid === getUid()) {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                      Alert.alert('Delete Comment', 'Are you sure you want to delete this comment?', [
                        { text: 'Cancel', style: 'cancel' },
                        { text: 'Delete', style: 'destructive', onPress: () => handleDeleteComment(c.id) },
                      ]);
                    }
                  }}
                  style={({ pressed }) => [styles.commentRow, pressed && { opacity: 0.6 }]}
                >
                  <View style={styles.commentContent}>
                    <View style={styles.commentHeader}>
                      <Pressable style={styles.commentAuthorRow} onPress={() => router.push(`/user/${c.authorUsername}` as any)}>
                        {c.authorProfilePhoto ? (
                          <Image source={{ uri: c.authorProfilePhoto }} style={styles.commentAvatar} />
                        ) : (
                          <View style={styles.commentAvatarFallback}>
                            <Text style={styles.commentAvatarText}>
                              {(c.authorUsername ?? '?').charAt(0).toUpperCase()}
                            </Text>
                          </View>
                        )}
                        <Text style={styles.commentAuthor}>{c.authorUsername ?? c.authorUid}</Text>
                      </Pressable>
                    </View>
                    <Text style={styles.commentBody}>{c.body}</Text>
                  </View>
                </Pressable>
              ))}
              {!allCommentsLoaded && commentCount > (post.recentComments?.length ?? 0) && (
                <Pressable onPress={fetchMoreComments}>
                  {loadingComments ? (
                    <ActivityIndicator size="small" color={colors.primary} style={{ paddingVertical: spacing.xs }} />
                  ) : (
                    <Text muted style={styles.moreComments}>
                      {commentCursor ? 'Load more comments' : `View all ${commentCount} comments`}
                    </Text>
                  )}
                </Pressable>
              )}
            </View>
          )}
          {/* Comment input */}
          <View style={styles.commentInputRow}>
            <TextInput
              style={styles.commentInput}
              placeholder="Write a comment..."
              placeholderTextColor={colors.placeholder}
              value={commentText}
              onChangeText={setCommentText}
              onSubmitEditing={handleComment}
              returnKeyType="send"
              maxLength={2000}
            />
            <Pressable onPress={handleComment} disabled={!commentText.trim()}>
              <Ionicons
                name="send"
                size={20}
                color={commentText.trim() ? colors.primary : colors.mutedForeground}
              />
            </Pressable>
          </View>
        </View>
      )}
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    backgroundColor: 'rgba(255, 255, 255, 0.6)',
    marginBottom: spacing.md,
    // Shadow / float
    shadowColor: '#000',
    shadowOffset: { width: 1, height: 1},
    shadowOpacity: 0.1,
    shadowRadius: 10,
    elevation: 10,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  authorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: spacing.sm,
  },
  authorAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.border,
  },
  authorAvatarFallback: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  authorAvatarText: {
    fontSize: 12,
    ...fonts.bold,
    color: colors.foreground,
  },
  authorName: {
    flex: 1,
    fontSize: fontSizes.sm,
    ...fonts.semibold,
    color: colors.foreground,
  },
  deleteButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    alignSelf: 'flex-end',
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.sm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.destructive,
  },
  deleteButtonText: {
    fontSize: fontSizes.sm,
    color: colors.destructive,
    ...fonts.medium,
  },
  mediaStrip: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  mediaThumb: {
    width: 140,
    height: 140,
    borderRadius: radii.md,
    backgroundColor: colors.border,
  },
  mediaThumbSingle: {
    width: 240,
    height: 180,
  },
  lightboxBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.92)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  lightboxImage: {
    width: Dimensions.get('window').width,
    height: Dimensions.get('window').height * 0.8,
  },
  lightboxClose: {
    position: 'absolute',
    top: 54,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: radii.xl,
    padding: 6,
    zIndex: 10,
  },
  lightboxArrowLeft: {
    position: 'absolute',
    left: 12,
    top: '50%',
    marginTop: -24,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderRadius: radii.xl,
    padding: 8,
    zIndex: 10,
  },
  lightboxArrowRight: {
    position: 'absolute',
    right: 12,
    top: '50%',
    marginTop: -24,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderRadius: radii.xl,
    padding: 8,
    zIndex: 10,
  },
  lightboxDots: {
    position: 'absolute',
    bottom: 50,
    flexDirection: 'row',
    alignSelf: 'center',
    gap: 6,
    zIndex: 10,
  },
  lightboxDot: {
    width: 7,
    height: 7,
    borderRadius: radii.xs,
    backgroundColor: 'rgba(255,255,255,0.4)',
  },
  lightboxDotActive: {
    backgroundColor: '#fff',
    width: 18,
  },
  title: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  body: {
    fontSize: fontSizes.sm,
    color: colors.foreground,
    lineHeight: 20,
  },
  // Workout hero
  workoutHero: {
    borderRadius: radii.md,
    overflow: 'hidden' as const,
    padding: spacing.md,
    gap: spacing.sm,
  },
  workoutHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  workoutIconCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  workoutActivity: {
    fontSize: fontSizes.lg,
    ...fonts.bold,
    color: colors.primaryForeground,
  },
  workoutStats: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.lg,
    paddingTop: spacing.xs,
  },
  workoutStat: {
    alignItems: 'center',
    minWidth: 40,
  },
  workoutStatValue: {
    fontSize: 22,
    ...fonts.bold,
    color: colors.primaryForeground,
  },
  workoutStatLabel: {
    fontSize: fontSizes.xs,
    color: 'rgba(255,255,255,0.7)',
    ...fonts.medium,
  },
  workoutStatDivider: {
    width: 1,
    height: 28,
    backgroundColor: 'rgba(255,255,255,0.25)',
  },
  // Body metrics hero
  metricsHero: {
    borderRadius: radii.md,
    overflow: 'hidden' as const,
    padding: spacing.md,
    gap: spacing.sm,
  },
  metricsHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  metricsIconCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  metricsTitle: {
    fontSize: fontSizes.lg,
    ...fonts.bold,
    color: colors.primaryForeground,
  },
  metricsStats: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.lg,
    paddingTop: spacing.xs,
  },
  date: {
    fontSize: fontSizes.xs,
  },
  reactionsRow: {
    flexDirection: 'row',
    gap: spacing.xs,
    flexWrap: 'wrap',
  },
  reactionBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.full,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
  },
  reactionBadgeSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.muted,
  },
  reactionEmoji: {
    fontSize: fontSizes.sm,
  },
  reactionCount: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
    ...fonts.medium,
  },
  actionBar: {
    flexDirection: 'row',
    gap: spacing.lg,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: spacing.xs,
  },
  actionCount: {
    fontSize: fontSizes.sm,
    color: colors.mutedForeground,
    ...fonts.medium,
  },
  reactionsExpanded: {
    gap: spacing.sm,
  },
  reactionUsersList: {
    gap: spacing.xs,
    padding: spacing.sm,
    borderRadius: radii.md,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
  },
  reactionUserRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 2,
  },
  reactionUserEmoji: {
    fontSize: fontSizes.sm,
  },
  reactionUserAvatar: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.border,
  },
  reactionUserAvatarFallback: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  reactionUserAvatarText: {
    fontSize: 10,
    ...fonts.bold,
    color: colors.foreground,
  },
  reactionUserName: {
    fontSize: fontSizes.sm,
    color: colors.foreground,
    ...fonts.medium,
  },
  reactionPicker: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    padding: spacing.sm,
    borderRadius: radii.md,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
  },
  reactionPickerItem: {
    padding: spacing.xs,
  },
  reactionPickerSelected: {
    backgroundColor: colors.border,
    borderRadius: radii.sm,
  },
  reactionPickerEmoji: {
    fontSize: 22,
  },
  bubblePicker: {
    flexDirection: 'row',
    justifyContent: 'space-evenly',
    paddingVertical: spacing.xs,
  },
  bubbleItem: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  bubbleItemSelected: {
    backgroundColor: colors.border,
    borderRadius: radii.lg,
  },
  bubbleEmoji: {
    fontSize: 28,
  },
  commentsExpanded: {
    gap: spacing.sm,
  },
  commentInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  commentInput: {
    flex: 1,
    height: 36,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.sm,
    fontSize: fontSizes.sm,
    color: colors.foreground,
    backgroundColor: colors.background,
  },
  commentsSection: {
    gap: spacing.xs,
  },
  commentRow: {
    paddingVertical: spacing.xs,
  },
  commentContent: {
    gap: 2,
  },
  commentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  commentAuthorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  commentAvatar: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.border,
  },
  commentAvatarFallback: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  commentAvatarText: {
    fontSize: 10,
    ...fonts.bold,
    color: colors.foreground,
  },
  commentAuthor: {
    fontSize: fontSizes.xs,
    ...fonts.bold,
    color: colors.foreground,
  },
  commentBody: {
    fontSize: fontSizes.sm,
    color: colors.foreground,
  },
  moreComments: {
    fontSize: fontSizes.sm,
    paddingTop: spacing.xs,
  },
});
