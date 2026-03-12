import { useState, useCallback } from 'react';
import { ActivityIndicator, Dimensions, FlatList, Image, Modal, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Text, colors, spacing } from '@/components/ui';
import { PostCard, type Post } from '@/components/PostCard';
import { getIdToken } from '@/services/auth';
import { config } from '@/config';

export type ProfileData = {
  id: string;
  username: string;
  displayName: string;
  bio?: string | null;
  birthday?: string | null;
  profilePhoto?: string | null;
  location?: {
    type: string;
    coordinates: [number, number];
    label?: string | null;
  } | null;
  interests?: string[] | null;
  fitnessLevel?: string | null;
};

type Props = {
  /** Profile data to display */
  profile: ProfileData | null;
  /** Follower count */
  followersCount: number;
  /** Following count */
  followingCount: number;
  /** Is this the current user's own profile? */
  isOwnProfile?: boolean;
  /** Posts to render */
  posts: Post[];
  /** Are posts currently loading? */
  postsLoading: boolean;
  /** Called when infinite scroll hits the end */
  onLoadMore: () => void;
  /** Called when a post is mutated (reaction/comment) */
  onPostChanged: (post: Post) => void;
  /** Called to delete a post (own profile only) */
  onDeletePost?: (postId: string) => void;
  /** Base path for follow list navigation (defaults to own user) */
  followListParams?: string;
  /** Whether the viewer is following this profile */
  isFollowing?: boolean;
  /** Whether a follow/unfollow action is in progress */
  followLoading?: boolean;
  /** Called when the follow/unfollow button is pressed */
  onFollowToggle?: () => void;
};

export function ProfileView({
  profile,
  followersCount,
  followingCount,
  isOwnProfile = false,
  posts,
  postsLoading,
  onLoadMore,
  onPostChanged,
  onDeletePost,
  followListParams,
  isFollowing,
  followLoading,
  onFollowToggle,
}: Props) {
  const router = useRouter();
  const [photoExpanded, setPhotoExpanded] = useState(false);

  const followBase = followListParams ?? '';

  return (
    <>
    {/* Fullscreen profile photo lightbox */}
    {profile?.profilePhoto && (
      <Modal visible={photoExpanded} transparent animationType="fade" onRequestClose={() => setPhotoExpanded(false)}>
        <Pressable style={styles.lightboxOverlay} onPress={() => setPhotoExpanded(false)}>
          <Image
            source={{ uri: profile.profilePhoto }}
            style={styles.lightboxImage}
            resizeMode="contain"
          />
          <View style={styles.lightboxClose}>
            <Ionicons name="close" size={28} color="#fff" />
          </View>
        </Pressable>
      </Modal>
    )}
    <FlatList
      data={posts}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <PostCard
          post={item}
          showAuthor={false}
          onPostChanged={onPostChanged}
          onDeletePost={isOwnProfile ? onDeletePost : undefined}
        />
      )}
      onEndReached={onLoadMore}
      onEndReachedThreshold={0.5}
      contentContainerStyle={styles.listContent}
      ListHeaderComponent={
        <View style={styles.profileHeader}>
          {profile ? (
            <>
              {/* Profile Photo */}
              {profile.profilePhoto ? (
                <Pressable onPress={() => setPhotoExpanded(true)}>
                  <Image
                    source={{ uri: profile.profilePhoto }}
                    style={styles.avatar}
                  />
                </Pressable>
              ) : (
                <View style={styles.avatarPlaceholder}>
                  <Text style={styles.avatarInitial}>
                    {profile.displayName.charAt(0).toUpperCase()}
                  </Text>
                </View>
              )}
              <Text variant="title">{profile.displayName}</Text>
              <Text muted>@{profile.username}</Text>
              {!isOwnProfile && onFollowToggle && (
                <Pressable
                  style={[
                    styles.followButton,
                    isFollowing && styles.followButtonActive,
                  ]}
                  onPress={onFollowToggle}
                  disabled={followLoading}
                >
                  {followLoading ? (
                    <ActivityIndicator size="small" color={colors.foreground} />
                  ) : (
                    <Text
                      style={[
                        styles.followButtonText,
                        isFollowing && styles.followButtonTextActive,
                      ]}
                    >
                      {isFollowing ? 'Following' : 'Follow'}
                    </Text>
                  )}
                </Pressable>
              )}
              <View style={styles.followRow}>
                <Pressable
                  onPress={() =>
                    router.push(
                      `/follow-list?tab=followers${followBase}` as any,
                    )
                  }
                  style={styles.followTap}
                >
                  <Text style={styles.followCount}>{followersCount}</Text>
                  <Text muted> followers</Text>
                </Pressable>
                <View style={{ width: spacing.lg }} />
                <Pressable
                  onPress={() =>
                    router.push(
                      `/follow-list?tab=following${followBase}` as any,
                    )
                  }
                  style={styles.followTap}
                >
                  <Text style={styles.followCount}>{followingCount}</Text>
                  <Text muted> following</Text>
                </Pressable>
              </View>
              {profile.bio && <Text style={styles.bio}>{profile.bio}</Text>}
              {profile.fitnessLevel && (
                <View style={styles.levelBadge}>
                  <Ionicons name="barbell-outline" size={14} color={colors.primaryForeground} />
                  <Text style={styles.levelBadgeText}>
                    {profile.fitnessLevel.charAt(0).toUpperCase() + profile.fitnessLevel.slice(1)}
                  </Text>
                </View>
              )}
              {profile.location?.label && (
                <View style={styles.locationRow}>
                  <Ionicons name="location-outline" size={14} color={colors.mutedForeground} />
                  <Text muted style={styles.locationText}>{profile.location.label}</Text>
                </View>
              )}
              {profile.interests && profile.interests.length > 0 && (
                <View style={styles.interestsRow}>
                  {profile.interests.map((interest) => (
                    <View key={interest} style={styles.interestTag}>
                      <Text style={styles.interestTagText}>{interest}</Text>
                    </View>
                  ))}
                </View>
              )}
            </>
          ) : (
            <Text muted>Could not load profile.</Text>
          )}
        </View>
      }
      ListEmptyComponent={
        !postsLoading ? (
          <View style={styles.emptyState}>
            <Text muted>
              {isOwnProfile
                ? 'No posts yet. Share your first workout!'
                : 'No posts yet.'}
            </Text>
          </View>
        ) : null
      }
      ListFooterComponent={
        postsLoading ? (
          <ActivityIndicator style={styles.footerLoader} color={colors.primary} />
        ) : null
      }
    />
    </>
  );
}

const AVATAR_SIZE = 80;

const styles = StyleSheet.create({
  profileHeader: {
    alignItems: 'center',
    paddingTop: spacing['2xl'],
    gap: spacing.sm,
    paddingBottom: spacing.xl,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    marginBottom: spacing.md,
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
    marginBottom: spacing.sm,
  },
  avatarPlaceholder: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  avatarInitial: {
    fontSize: 32,
    fontWeight: '700',
    color: '#fff',
  },
  bio: {
    paddingHorizontal: spacing.lg,
    textAlign: 'center',
    marginTop: spacing.md,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: spacing.xs,
  },
  locationText: {
    fontSize: 13,
  },
  followRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  followCount: {
    fontWeight: '700',
    color: colors.foreground,
  },
  followTap: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: 100,
  },
  emptyState: {
    alignItems: 'center',
    paddingTop: spacing['2xl'],
  },
  footerLoader: {
    paddingVertical: spacing.lg,
  },
  followButton: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xs,
    borderRadius: 20,
    backgroundColor: colors.primary,
    minWidth: 100,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  followButtonActive: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.border,
  },
  followButtonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 14,
  },
  followButtonTextActive: {
    color: colors.foreground,
  },
  lightboxOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.92)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  lightboxImage: {
    width: Dimensions.get('window').width,
    height: Dimensions.get('window').width,
  },
  lightboxClose: {
    position: 'absolute',
    top: 54,
    right: 20,
  },
  levelBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: 16,
    marginTop: spacing.xs,
  },
  levelBadgeText: {
    color: colors.primaryForeground,
    fontWeight: '600',
    fontSize: 13,
  },
  interestsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: spacing.xs,
    marginTop: spacing.md,
    paddingHorizontal: spacing.md,
  },
  interestTag: {
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.muted,
  },
  interestTagText: {
    fontSize: 12,
    color: colors.foreground,
  },
});
