import { useState, useCallback } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { ProfileView, type ProfileData } from '@/components/ProfileView';
import { type Post } from '@/components/PostCard';
import { consumeScrollToPostIntent } from '@/services/scrollToPost';
import { apiFetch } from '@/services/api';

type ProfileBundle = {
  profile: ProfileData;
  followersCount: number;
  followingCount: number;
};
type PostsPage = { items: Post[]; cursor: string | null; count: number };

export default function ProfileScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [extraPosts, setExtraPosts] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [scrollToPostId, setScrollToPostId] = useState<string | null>(null);
  const [scrollToPostSection, setScrollToPostSection] = useState<'comments' | 'reactions' | null>(null);
  const [scrollToReactionType, setScrollToReactionType] = useState<string | undefined>(undefined);

  // ── Profile + follow counts (cached) ──
  const { data: profileBundle, isLoading, isError, refetch } = useQuery({
    queryKey: ['myProfile'],
    queryFn: async () => {
      const [profile, followers, following] = await Promise.all([
        apiFetch<ProfileData>('/profile'),
        apiFetch<{ count: number }>('/follows/followers'),
        apiFetch<{ count: number }>('/follows/following'),
      ]);
      return { profile, followersCount: followers.count, followingCount: following.count };
    },
  });

  // ── Own posts (cached first page) ──
  const { data: postsData, isLoading: postsLoading, isRefetching: postsRefetching } = useQuery({
    queryKey: ['myPosts'],
    queryFn: () => apiFetch<PostsPage>('/posts?limit=20'),
    refetchOnMount: 'always',
  });

  // ── Aggregate post stats (server-side totals) ──
  const { data: postStats } = useQuery({
    queryKey: ['myPostStats'],
    queryFn: () => apiFetch<{ postCount: number; reactionCount: number; commentCount: number }>('/posts/stats'),
  });

  // Sync pagination state from cached query data
  const postsCursor = postsData?.cursor ?? null;
  const postsHasMore = postsData ? postsData.count === 20 : true;
  const postsItemIds = postsData?.items?.map((p) => p.id).join(',');
  const [lastPostIds, setLastPostIds] = useState<string | undefined>(undefined);
  if (postsItemIds !== undefined && postsItemIds !== lastPostIds) {
    setLastPostIds(postsItemIds);
    setCursor(postsCursor);
    setHasMore(postsHasMore);
    setExtraPosts([]);
  }

  const posts = [...(postsData?.items ?? []), ...extraPosts];

  // ── Check for scroll-to-post intent on focus ──
  useFocusEffect(
    useCallback(() => {
      const intent = consumeScrollToPostIntent();
      if (intent) {
        setScrollToPostId(intent.postId);
        setScrollToPostSection(intent.section);
        setScrollToReactionType(intent.reactionType);
      } else {
        setScrollToPostId(null);
        setScrollToPostSection(null);
        setScrollToReactionType(undefined);
      }
      // Only refetch if data is stale (respects staleTime)
      queryClient.refetchQueries({ queryKey: ['myPosts'], type: 'active', stale: true });
      queryClient.refetchQueries({ queryKey: ['myPostStats'], type: 'active', stale: true });
    }, [queryClient])
  );

  // ── Pagination ──
  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || !cursor) return;
    setLoadingMore(true);
    try {
      const data = await apiFetch<PostsPage>(`/posts?limit=20&cursor=${cursor}`);
      setExtraPosts((prev) => [...prev, ...data.items]);
      setCursor(data.cursor);
      setHasMore(data.count === 20);
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, cursor]);

  const onRefresh = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['myPosts'] }),
      queryClient.invalidateQueries({ queryKey: ['myProfile'] }),
      queryClient.invalidateQueries({ queryKey: ['myPostStats'] }),
    ]);
  }, [queryClient]);

  const handlePostChanged = (updated: Post) => {
    queryClient.setQueryData<PostsPage>(['myPosts'], (old) =>
      old ? { ...old, items: old.items.map((p) => (p.id === updated.id ? updated : p)) } : old
    );
    setExtraPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleDeletePost = async (postId: string) => {
    try {
      await apiFetch(`/posts/${postId}`, { method: 'DELETE' });
      queryClient.setQueryData<PostsPage>(['myPosts'], (old) =>
        old ? { ...old, items: old.items.filter((p) => p.id !== postId) } : old
      );
      setExtraPosts((prev) => prev.filter((p) => p.id !== postId));
      queryClient.invalidateQueries({ queryKey: ['myPostStats'] });
      if (profileBundle?.profile?.id) {
        queryClient.invalidateQueries({ queryKey: ['tracking', profileBundle.profile.id] });
      }
    } catch {
      // ignore
    }
  };

  if (isLoading) {
    return (
      <GradientScreen transparent>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </GradientScreen>
    );
  }

  if (isError) {
    return (
      <GradientScreen transparent>
        <View style={styles.center}>
          <Ionicons name="cloud-offline-outline" size={48} color={colors.mutedForeground} />
          <Text style={styles.errorTitle}>Can't Connect</Text>
          <Text muted style={styles.errorSubtitle}>
            Unable to reach the server. Check your connection and try again.
          </Text>
          <Pressable style={styles.retryButton} onPress={() => refetch()}>
            <Ionicons name="refresh" size={16} color={colors.primaryForeground} />
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      </GradientScreen>
    );
  }

  return (
    <GradientScreen transparent>
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }} />
        <View style={styles.headerActions}>
          <Pressable style={styles.headerIcon} onPress={() => router.push('/create-post')}>
            <Ionicons name="add-circle-outline" size={26} color={colors.foreground} />
          </Pressable>
          <Pressable style={styles.headerIcon} onPress={() => router.push('/edit-profile')}>
            <Ionicons name="pencil-outline" size={22} color={colors.foreground} />
          </Pressable>
          <Pressable style={styles.headerIcon} onPress={() => router.push('/settings')}>
            <Ionicons name="settings-outline" size={22} color={colors.foreground} />
          </Pressable>
        </View>
      </View>

      <ProfileView
        profile={profileBundle?.profile ?? null}
        followersCount={profileBundle?.followersCount ?? 0}
        followingCount={profileBundle?.followingCount ?? 0}
        isOwnProfile
        posts={posts}
        postsLoading={postsLoading || loadingMore}
        onLoadMore={loadMore}
        onPostChanged={handlePostChanged}
        onDeletePost={handleDeletePost}
        scrollToPostId={scrollToPostId}
        scrollToPostSection={scrollToPostSection}
        scrollToReactionType={scrollToReactionType}
        postStats={postStats ?? null}
        onRefresh={onRefresh}
        isRefreshing={postsRefetching}
      />
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
  },
  headerUsername: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.foreground,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  headerIcon: {
    padding: 6,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  errorTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.foreground,
    marginTop: spacing.md,
  },
  errorSubtitle: {
    fontSize: 14,
    color: colors.mutedForeground,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 20,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 999,
    marginTop: spacing.lg,
  },
  retryText: {
    color: colors.primaryForeground,
    fontWeight: '600',
    fontSize: 14,
  },
});
