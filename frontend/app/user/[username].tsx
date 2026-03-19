import { useState, useCallback } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { ProfileView, type ProfileData } from '@/components/ProfileView';
import { type Post } from '@/components/PostCard';
import { getUid } from '@/services/auth';
import { apiFetch } from '@/services/api';
import { getOrCreateConversation } from '@/services/messaging';

type PostsPage = { items: Post[]; cursor: string | null; count: number };

export default function UserProfileScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { username } = useLocalSearchParams<{ username: string }>();

  const [extraPosts, setExtraPosts] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);
  const [blockLoading, setBlockLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  // ── Profile data (cached by username) — includes followersCount, followingCount, isFollowing ──
  const { data: profile, isLoading } = useQuery({
    queryKey: ['userProfile', username],
    queryFn: () => apiFetch<ProfileData & { followersCount: number; followingCount: number; postCount: number; isFollowing?: boolean; isBlocked?: boolean; isBlockedByThem?: boolean }>(`/profile/${username}`),
    enabled: !!username,
  });

  const isFollowing = profile?.isFollowing ?? false;
  const isBlocked = profile?.isBlocked ?? false;
  const isBlockedByThem = profile?.isBlockedByThem ?? false;
  const anyBlock = isBlocked || isBlockedByThem;

  // ── User's posts (cached first page by uid) ──
  const { data: postsData, isLoading: postsLoading, isRefetching: postsRefetching } = useQuery({
    queryKey: ['userPosts', profile?.id],
    queryFn: () => apiFetch<PostsPage>(`/posts/user/${profile!.id}?limit=20`),
    enabled: !!profile?.id,
    refetchOnMount: 'always',
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

  // ── Pagination ──
  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || !cursor || !profile) return;
    setLoadingMore(true);
    try {
      const data = await apiFetch<PostsPage>(`/posts/user/${profile.id}?limit=20&cursor=${cursor}`);
      setExtraPosts((prev) => [...prev, ...data.items]);
      setCursor(data.cursor);
      setHasMore(data.count === 20);
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, cursor, profile]);

  // Refetch posts when the screen gains focus (only if stale)
  useFocusEffect(
    useCallback(() => {
      if (!profile?.id) return;
      queryClient.refetchQueries({ queryKey: ['userPosts', profile.id], type: 'active', stale: true });
    }, [queryClient, profile?.id])
  );

  const onRefresh = useCallback(async () => {
    if (!profile?.id) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['userPosts', profile.id] }),
      queryClient.invalidateQueries({ queryKey: ['userProfile', username] }),
    ]);
  }, [queryClient, profile?.id, username]);

  const handleFollow = async () => {
    if (!profile || followLoading) return;
    setFollowLoading(true);
    try {
      const method = isFollowing ? 'DELETE' : 'POST';
      await apiFetch(`/follows/${profile.id}`, { method });
      // Optimistically update the profile cache
      queryClient.setQueryData(
        ['userProfile', username],
        (old: any) => old ? {
          ...old,
          followersCount: (old.followersCount ?? 0) + (isFollowing ? -1 : 1),
          isFollowing: !isFollowing,
        } : old
      );
    } catch {
      Alert.alert('Error', 'Could not update follow status');
    } finally {
      setFollowLoading(false);
    }
  };

  const handlePostChanged = (updated: Post) => {
    queryClient.setQueryData<PostsPage>(['userPosts', profile?.id], (old) =>
      old ? { ...old, items: old.items.map((p) => (p.id === updated.id ? updated : p)) } : old
    );
    setExtraPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleMessage = useCallback(async () => {
    const myUid = getUid();
    if (!myUid || !profile) return;
    try {
      const conversationId = await getOrCreateConversation(myUid, profile.id);
      router.push({
        pathname: '/conversation',
        params: { conversationId, otherUid: profile.id },
      });
    } catch {
      Alert.alert('Error', 'Could not start conversation');
    }
  }, [profile, router]);

  const handleBlock = async () => {
    if (!profile || blockLoading) return;
    setBlockLoading(true);
    try {
      const method = isBlocked ? 'DELETE' : 'POST';
      await apiFetch(`/blocks/${profile.id}`, { method });
      queryClient.setQueryData(
        ['userProfile', username],
        (old: any) => old ? {
          ...old,
          isBlocked: !isBlocked,
          // If blocking, also unfollow
          ...(!isBlocked ? { isFollowing: false } : {}),
        } : old
      );
      // Invalidate feeds/search that may now be stale
      queryClient.invalidateQueries({ queryKey: ['feed'] });
      queryClient.invalidateQueries({ queryKey: ['nearbyProfiles'] });
    } catch {
      Alert.alert('Error', 'Could not update block status');
    } finally {
      setBlockLoading(false);
    }
  };

  if (isLoading) {
    return (
      <GradientScreen>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} style={styles.backButton}>
            <Ionicons name="chevron-back" size={24} color={colors.foreground} />
          </Pressable>
        </View>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </GradientScreen>
    );
  }

  return (
    <GradientScreen>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.foreground} />
        </Pressable>
        {profile?.id !== getUid() && (
          <View style={{ position: 'relative' }}>
            <Pressable onPress={() => setMenuOpen((o) => !o)} style={styles.menuButton}>
              <Ionicons name="ellipsis-horizontal" size={20} color={colors.foreground} />
            </Pressable>
            {menuOpen && (
              <View style={styles.dropdown}>
                <Pressable
                  style={styles.dropdownItem}
                  disabled={blockLoading}
                  onPress={() => {
                    setMenuOpen(false);
                    Alert.alert(
                      isBlocked ? 'Unblock User' : 'Block User',
                      isBlocked
                        ? `Unblock @${profile?.username}?`
                        : `Block @${profile?.username}? They won't be able to see your profile, posts, or message you.`,
                      [
                        { text: 'Cancel', style: 'cancel' },
                        {
                          text: isBlocked ? 'Unblock' : 'Block',
                          style: isBlocked ? 'default' : 'destructive',
                          onPress: handleBlock,
                        },
                      ],
                    );
                  }}
                >
                  <Ionicons
                    name="ban-outline"
                    size={16}
                    color={isBlocked ? '#ef4444' : colors.foreground}
                  />
                  <Text style={[styles.dropdownText, isBlocked && { color: '#ef4444' }]}>
                    {isBlocked ? 'Unblock' : 'Block'}
                  </Text>
                </Pressable>
              </View>
            )}
          </View>
        )}
      </View>

      <ProfileView
        profile={profile ?? null}
        followersCount={profile?.followersCount ?? 0}
        followingCount={profile?.followingCount ?? 0}
        isOwnProfile={profile?.id === getUid()}
        posts={anyBlock ? [] : posts}
        postsLoading={anyBlock ? false : (postsLoading || loadingMore)}
        onLoadMore={loadMore}
        onPostChanged={handlePostChanged}
        followListParams={profile ? `&uid=${profile.id}` : ''}
        isFollowing={isFollowing}
        followLoading={followLoading}
        onFollowToggle={profile?.id !== getUid() && !anyBlock ? handleFollow : undefined}
        onMessage={profile?.id !== getUid() && !anyBlock ? handleMessage : undefined}
        postCount={anyBlock ? 0 : (profile?.postCount ?? 0)}
        onRefresh={onRefresh}
        isRefreshing={postsRefetching}
      />
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  backButton: {
    padding: spacing.xs,
  },
  menuButton: {
    padding: spacing.xs,
  },
  dropdown: {
    position: 'absolute',
    top: 36,
    right: 0,
    backgroundColor: colors.card,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 4,
    minWidth: 140,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
    zIndex: 100,
  },
  dropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  dropdownText: {
    fontSize: 15,
    color: colors.foreground,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
