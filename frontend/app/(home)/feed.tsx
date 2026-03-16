import { useState, useCallback } from 'react';
import { ActivityIndicator, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, fonts, fontSizes, spacing, radii } from '@/components/ui';
import { PostCard, type Post } from '@/components/PostCard';
import { apiFetch } from '@/services/api';

type FeedPage = { items: Post[]; cursor: string | null; count: number };

export default function FeedScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [extraPosts, setExtraPosts] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // ── Initial feed load (cached, stale-while-revalidate) ──
  const { data: feedData, isLoading, isRefetching, isError, refetch } = useQuery({
    queryKey: ['feed'],
    queryFn: async () => {
      const data = await apiFetch<FeedPage>('/feed?limit=20');
      return data;
    },
  });

  // Sync pagination state from cached query data
  const feedCursor = feedData?.cursor ?? null;
  const feedHasMore = feedData ? feedData.count === 20 : true;

  // Reset pagination extras when feed query refreshes
  const feedItemIds = feedData?.items?.map((p) => p.id).join(',');
  const [lastFeedIds, setLastFeedIds] = useState<string | undefined>(undefined);
  if (feedItemIds !== undefined && feedItemIds !== lastFeedIds) {
    setLastFeedIds(feedItemIds);
    setCursor(feedCursor);
    setHasMore(feedHasMore);
    setExtraPosts([]);
  }

  const posts = [...(feedData?.items ?? []), ...extraPosts];

  // ── Unread notification count (cached) ──
  const { data: unreadData } = useQuery({
    queryKey: ['unreadNotifCount'],
    queryFn: () => apiFetch<{ count: number }>('/profile/notifications/unread-count'),
  });
  const unreadNotifs = unreadData?.count ?? 0;

  // ── Pagination (append beyond first page) ──
  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || !cursor) return;
    setLoadingMore(true);
    try {
      const data = await apiFetch<FeedPage>(`/feed?limit=20&cursor=${cursor}`);
      setExtraPosts((prev) => [...prev, ...data.items]);
      setCursor(data.cursor);
      setHasMore(data.count === 20);
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, cursor]);

  // ── Pull-to-refresh ──
  const onRefresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['feed'] });
    queryClient.invalidateQueries({ queryKey: ['unreadNotifCount'] });
  }, [queryClient]);

  const handlePostChanged = (updated: Post) => {
    // Update in query cache
    queryClient.setQueryData<FeedPage>(['feed'], (old) =>
      old ? { ...old, items: old.items.map((p) => (p.id === updated.id ? updated : p)) } : old
    );
    // Update in extra pages
    setExtraPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  return (
    <GradientScreen transparent>
      {/* ── Header ── */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Image
            source={require('@/assets/images/logo.png')}
            style={styles.logo}
            resizeMode="contain"
          />
          <Text style={styles.headerTitle}>Feed</Text>
        </View>
        <View style={styles.headerActions}>
          <Pressable
            style={styles.iconButton}
            onPress={() => router.push('/notifications')}
          >
            <Ionicons name="notifications-outline" size={22} color={colors.foreground} />
            {unreadNotifs > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>
                  {unreadNotifs > 99 ? '99+' : unreadNotifs}
                </Text>
              </View>
            )}
          </Pressable>
          <Pressable
            style={styles.iconButton}
            onPress={() => router.push('/friends')}
          >
            <Ionicons name="people-outline" size={22} color={colors.foreground} />
          </Pressable>
        </View>
      </View>

      <FlatList
        data={posts}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <PostCard
            post={item}
            showAuthor
            onPostChanged={handlePostChanged}
          />
        )}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        refreshing={isRefetching}
        onRefresh={onRefresh}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          isError ? (
            <View style={styles.emptyState}>
              <View style={styles.emptyIcon}>
                <Ionicons name="cloud-offline-outline" size={48} color={colors.mutedForeground} />
              </View>
              <Text style={styles.emptyTitle}>Can't Connect</Text>
              <Text muted style={styles.emptySubtitle}>
                Unable to reach the server. Check your connection and try again.
              </Text>
              <Pressable style={styles.emptyButton} onPress={() => refetch()}>
                <Ionicons name="refresh" size={16} color={colors.primaryForeground} />
                <Text style={styles.emptyButtonText}>Retry</Text>
              </Pressable>
            </View>
          ) : !isLoading ? (
            <View style={styles.emptyState}>
              <View style={styles.emptyIcon}>
                <Ionicons name="newspaper-outline" size={48} color={colors.mutedForeground} />
              </View>
              <Text style={styles.emptyTitle}>Your feed is empty</Text>
              <Text muted style={styles.emptySubtitle}>
                Follow people to see their posts here
              </Text>
              <Pressable
                style={styles.emptyButton}
                onPress={() => router.push('/friends')}
              >
                <Ionicons name="people" size={16} color={colors.primaryForeground} />
                <Text style={styles.emptyButtonText}>Find People</Text>
              </Pressable>
            </View>
          ) : null
        }
        ListFooterComponent={
          isLoading || loadingMore ? <ActivityIndicator style={styles.footerLoader} color={colors.primary} /> : null
        }
      />
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  // ── Header ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.sm,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  logo: {
    width: 28,
    height: 28,
  },
  headerTitle: {
    fontSize: fontSizes.xl,
    ...fonts.bold,
    color: colors.foreground,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  badge: {
    position: 'absolute',
    top: 2,
    right: 2,
    backgroundColor: colors.brandRed,
    borderRadius: radii.full,
    minWidth: 18,
    height: 18,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
    borderWidth: 2,
    borderColor: '#fff',
  },
  badgeText: {
    color: '#fff',
    fontSize: 9,
    ...fonts.bold,
  },

  // ── List ──
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: 16,
  },
  footerLoader: {
    paddingVertical: spacing.lg,
  },

  // ── Empty state ──
  emptyState: {
    alignItems: 'center',
    paddingTop: spacing['2xl'] + spacing.lg,
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  emptyIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  emptyTitle: {
    fontSize: fontSizes.lg,
    ...fonts.semibold,
    color: colors.foreground,
  },
  emptySubtitle: {
    fontSize: fontSizes.sm,
    textAlign: 'center',
  },
  emptyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.full,
    marginTop: spacing.md,
  },
  emptyButtonText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
});
