import { useState, useCallback, useRef, useEffect } from 'react';
import { ActivityIndicator, Dimensions, FlatList, Image, Modal, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Text, colors, spacing, radii, fonts, fontSizes } from '@/components/ui';
import { PostCard, type Post } from '@/components/PostCard';
import { TrackingView } from '@/components/TrackingView';

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
  /** Called when the Message button is pressed */
  onMessage?: () => void;
  /** If set, auto-scroll to this post ID after posts load */
  scrollToPostId?: string | null;
  /** Which section to auto-open on the scrolled-to post */
  scrollToPostSection?: 'comments' | 'reactions' | null;
  /** Which specific reaction type to filter to */
  scrollToReactionType?: string;
  /** Server-side aggregate stats */
  postStats?: { postCount: number; reactionCount: number; commentCount: number } | null;
  /** Called on pull-to-refresh */
  onRefresh?: () => Promise<void>;
  /** Whether a refresh is in progress */
  isRefreshing?: boolean;
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
  onMessage,
  scrollToPostId,
  scrollToPostSection,
  scrollToReactionType,
  postStats,
  onRefresh,
  isRefreshing = false,
}: Props) {
  const router = useRouter();
  const [photoExpanded, setPhotoExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'posts' | 'tracking'>('posts');
  const flatListRef = useRef<FlatList>(null);
  const hasScrolled = useRef(false);

  const followBase = followListParams ?? '';

  // Auto-scroll to a specific post when scrollToPostId is set
  useEffect(() => {
    if (!scrollToPostId || posts.length === 0 || hasScrolled.current) return;
    const index = posts.findIndex((p) => p.id === scrollToPostId);
    if (index >= 0) {
      hasScrolled.current = true;
      setTimeout(() => {
        flatListRef.current?.scrollToIndex({ index, animated: true, viewOffset: 20 });
      }, 300);
    }
  }, [scrollToPostId, posts]);

  const profileHeaderContent = profile ? (
    <>
      {/* Profile Photo */}
      {profile.profilePhoto ? (
        <Pressable onPress={() => setPhotoExpanded(true)}>
          <Image source={{ uri: profile.profilePhoto }} style={styles.avatar} />
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
        <View style={styles.actionRow}>
          <Pressable
            style={[styles.followButton, isFollowing && styles.followButtonActive]}
            onPress={onFollowToggle}
            disabled={followLoading}
          >
            {followLoading ? (
              <ActivityIndicator size="small" color={colors.foreground} />
            ) : (
              <Text style={[styles.followButtonText, isFollowing && styles.followButtonTextActive]}>
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            )}
          </Pressable>
          {onMessage && (
            <Pressable style={styles.messageButton} onPress={onMessage}>
              <Ionicons name="chatbubble-outline" size={16} color={colors.foreground} />
              <Text style={styles.messageButtonText}>Message</Text>
            </Pressable>
          )}
        </View>
      )}
      <View style={styles.followRow}>
        <Pressable
          onPress={() => router.push(`/follow-list?tab=followers${followBase}` as any)}
          style={styles.followTap}
        >
          <Text style={styles.followCount}>{followersCount}</Text>
          <Text muted> followers</Text>
        </Pressable>
        <View style={{ width: spacing.lg }} />
        <Pressable
          onPress={() => router.push(`/follow-list?tab=following${followBase}` as any)}
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
  );

  // ── Post stats (prefer server-side, fall back to loaded posts) ──
  const totalPosts = postStats?.postCount ?? posts.length;
  const totalReactions = postStats?.reactionCount ?? posts.reduce(
    (sum, p) => sum + Object.values(p.reactionSummary ?? {}).reduce((a, b) => a + b, 0),
    0,
  );
  const totalComments = postStats?.commentCount ?? posts.reduce((sum, p) => sum + (p.commentCount ?? 0), 0);

  const renderHeader = () => (
    <View>
      <View style={styles.profileHeader}>{profileHeaderContent}</View>
      {/* ── Subtabs ── */}
      <View style={styles.tabBar}>
        <Pressable
          style={[styles.tab, activeTab === 'posts' && styles.tabActive]}
          onPress={() => setActiveTab('posts')}
        >
          <Ionicons
            name="grid-outline"
            size={18}
            color={activeTab === 'posts' ? colors.foreground : colors.mutedForeground}
          />
          <Text style={[styles.tabText, activeTab === 'posts' && styles.tabTextActive]}>
            Posts
          </Text>
        </Pressable>
        <Pressable
          style={[styles.tab, activeTab === 'tracking' && styles.tabActive]}
          onPress={() => setActiveTab('tracking')}
        >
          <Ionicons
            name="analytics-outline"
            size={18}
            color={activeTab === 'tracking' ? colors.foreground : colors.mutedForeground}
          />
          <Text style={[styles.tabText, activeTab === 'tracking' && styles.tabTextActive]}>
            Tracking
          </Text>
        </Pressable>
      </View>

      {/* ── Posts Summary Banner ── */}
      {activeTab === 'posts' && totalPosts > 0 && (
        <View style={styles.postsSummaryRow}>
          <View style={styles.postsSummaryItem}>
            <Text style={styles.postsSummaryValue}>{totalPosts}</Text>
            <Text style={styles.postsSummaryLabel}>Posts</Text>
          </View>
          <View style={styles.postsSummaryDivider} />
          <View style={styles.postsSummaryItem}>
            <Text style={styles.postsSummaryValue}>{totalReactions}</Text>
            <Text style={styles.postsSummaryLabel}>Reactions</Text>
          </View>
          <View style={styles.postsSummaryDivider} />
          <View style={styles.postsSummaryItem}>
            <Text style={styles.postsSummaryValue}>{totalComments}</Text>
            <Text style={styles.postsSummaryLabel}>Comments</Text>
          </View>
        </View>
      )}
    </View>
  );

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
    {activeTab === 'posts' ? (
      <FlatList
        ref={flatListRef}
        data={posts}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <PostCard
            post={item}
            showAuthor={false}
            onPostChanged={onPostChanged}
            onDeletePost={isOwnProfile ? onDeletePost : undefined}
            initialSection={item.id === scrollToPostId ? scrollToPostSection : null}
            initialReactionType={item.id === scrollToPostId ? scrollToReactionType : undefined}
          />
        )}
        onEndReached={onLoadMore}
        onEndReachedThreshold={0.5}
        extraData={`${scrollToPostId}-${scrollToPostSection}`}
        refreshControl={
          onRefresh ? (
            <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />
          ) : undefined
        }
        onScrollToIndexFailed={(info) => {
          setTimeout(() => {
            flatListRef.current?.scrollToIndex({ index: info.index, animated: true, viewOffset: 20 });
          }, 500);
        }}
        contentContainerStyle={styles.listContent}
        ListHeaderComponent={renderHeader}
        ListEmptyComponent={
          !postsLoading ? (
            <View style={styles.emptyState}>
              <Ionicons name="document-text-outline" size={48} color={colors.border} />
              <Text muted style={{ marginTop: spacing.md, textAlign: 'center' }}>
                {isOwnProfile
                  ? 'No posts yet.\nShare your first workout!'
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
    ) : (
      <FlatList
        data={[]}
        renderItem={null}
        ListHeaderComponent={
          <>
            {renderHeader()}
            {profile && <TrackingView uid={profile.id} />}
          </>
        }
        contentContainerStyle={styles.listContent}
      />
    )}
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
    ...fonts.bold,
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
    ...fonts.bold,
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
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followButtonActive: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  followButtonText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
  followButtonTextActive: {
    color: colors.foreground,
  },
  actionRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  messageButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
  },
  messageButtonText: {
    color: colors.foreground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
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
    borderRadius: radii.lg,
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
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.muted,
  },
  interestTagText: {
    fontSize: 12,
    color: colors.foreground,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    marginBottom: spacing.md,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: spacing.sm + 2,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    borderBottomColor: colors.foreground,
  },
  tabText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.mutedForeground,
  },
  tabTextActive: {
    color: colors.foreground,
  },
  // ── Posts Summary Banner ──
  postsSummaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingVertical: spacing.md,
    marginBottom: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    backgroundColor: 'rgba(255,255,255,0.6)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 4,
  },
  postsSummaryItem: {
    alignItems: 'center',
    flex: 1,
  },
  postsSummaryValue: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.foreground,
  },
  postsSummaryLabel: {
    fontSize: 11,
    fontWeight: '500',
    color: colors.mutedForeground,
    marginTop: 2,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  postsSummaryDivider: {
    width: 1,
    height: 28,
    backgroundColor: colors.border,
  },
});
