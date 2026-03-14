import { useState, useCallback } from 'react';
import { ActivityIndicator, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, radii, fonts, fontSizes } from '@/components/ui';
import { getUid } from '@/services/auth';
import { apiFetch } from '@/services/api';

type FollowUser = {
  id: string;
  username: string;
  displayName: string;
  profilePhoto?: string | null;
  location?: { coordinates?: [number, number]; label?: string | null } | null;
};

/** Haversine distance in miles between two [lng, lat] points. */
function distanceMiles(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const [lng1, lat1] = a;
  const [lng2, lat2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 3958.8 * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

function formatDistance(miles: number): string {
  if (miles < 1) return '< 1 mi';
  return `${Math.round(miles)} mi`;
}

type Tab = 'followers' | 'following';

export default function FollowListScreen() {
  const router = useRouter();
  const { tab: initialTab, uid } = useLocalSearchParams<{ tab?: string; uid?: string }>();
  const [tab, setTab] = useState<Tab>(
    initialTab === 'following' ? 'following' : 'followers',
  );
  const [myFollowingSet, setMyFollowingSet] = useState<Set<string>>(new Set());
  const [followLoadingIds, setFollowLoadingIds] = useState<Set<string>>(new Set());
  const [followSetInitialized, setFollowSetInitialized] = useState(false);

  /** Toggle follow / unfollow for a user */
  const toggleFollow = useCallback(async (targetUid: string) => {
    setFollowLoadingIds((prev) => new Set(prev).add(targetUid));
    try {
      const isFollowing = myFollowingSet.has(targetUid);
      const method = isFollowing ? 'DELETE' : 'POST';
      await apiFetch(`/follows/${targetUid}`, { method });
      setMyFollowingSet((prev) => {
        const next = new Set(prev);
        if (isFollowing) next.delete(targetUid);
        else next.add(targetUid);
        return next;
      });
    } catch {
      // ignore
    } finally {
      setFollowLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(targetUid);
        return next;
      });
    }
  }, [myFollowingSet]);

  const { data: queryData, isLoading } = useQuery({
    queryKey: ['followList', uid ?? 'me'],
    queryFn: async () => {
      const followersUrl = uid ? `/follows/${uid}/followers` : '/follows/followers';
      const followingUrl = uid ? `/follows/${uid}/following` : '/follows/following';
      const [followersData, followingData, myFollowingData, profileData] = await Promise.all([
        apiFetch<{ followers: FollowUser[] }>(followersUrl),
        apiFetch<{ following: FollowUser[] }>(followingUrl),
        apiFetch<{ following: { id: string }[] }>('/follows/following'),
        apiFetch<{ location?: { coordinates?: [number, number] } }>('/profile'),
      ]);
      setMyFollowingSet(new Set(myFollowingData.following.map((u) => u.id)));
      return {
        followers: followersData.followers,
        following: followingData.following,
        myFollowingIds: myFollowingData.following.map((u) => u.id),
        myLocation: profileData.location?.coordinates ?? null,
      };
    },
  });

  // Initialize follow set from cached query data on mount
  if (queryData?.myFollowingIds && !followSetInitialized) {
    setMyFollowingSet(new Set(queryData.myFollowingIds));
    setFollowSetInitialized(true);
  }

  const followers = queryData?.followers ?? [];
  const following = queryData?.following ?? [];
  const myLocation = queryData?.myLocation ?? null;
  const data = tab === 'followers' ? followers : following;

  const renderItem = ({ item }: { item: FollowUser }) => {
    const dist =
      myLocation && item.location?.coordinates
        ? distanceMiles(myLocation, item.location.coordinates)
        : null;
    const isFollowing = myFollowingSet.has(item.id);
    const isLoadingFollow = followLoadingIds.has(item.id);

    return (
      <Pressable
        style={styles.userCard}
        onPress={() => router.push(`/user/${item.username}` as any)}
      >
        {item.profilePhoto ? (
          <Image source={{ uri: item.profilePhoto }} style={styles.avatar} />
        ) : (
          <View style={styles.avatarFallback}>
            <Text style={styles.avatarText}>
              {item.displayName.charAt(0).toUpperCase()}
            </Text>
          </View>
        )}
        <View style={styles.userInfo}>
          <Text style={styles.displayName}>{item.displayName}</Text>
          <Text muted style={styles.username}>@{item.username}</Text>
          {(item.location?.label || dist != null) && (
            <View style={styles.locationRow}>
              {item.location?.label && (
                <>
                  <Ionicons name="location" size={11} color={colors.brandRed} />
                  <Text muted style={styles.locationText}>{item.location.label}</Text>
                </>
              )}
              {dist != null && (
                <Text muted style={styles.distText}>
                  {item.location?.label ? ' · ' : ''}{formatDistance(dist)}
                </Text>
              )}
            </View>
          )}
        </View>
        {item.id !== getUid() && (
          <Pressable
            style={[styles.followBtn, isFollowing && styles.followBtnActive]}
            onPress={() => toggleFollow(item.id)}
            disabled={isLoadingFollow}
          >
            {isLoadingFollow ? (
              <ActivityIndicator size="small" color={isFollowing ? colors.foreground : colors.primaryForeground} />
            ) : (
              <Text style={[styles.followBtnText, isFollowing && styles.followBtnTextActive]}>
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            )}
          </Pressable>
        )}
      </Pressable>
    );
  };

  return (
    <GradientScreen>
      {/* ── Header ── */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.foreground} />
        </Pressable>
        <Text style={styles.headerTitle}>
          {tab === 'followers' ? 'Followers' : 'Following'}
        </Text>
        <View style={styles.backButton} />
      </View>

      {/* ── Tab pills ── */}
      <View style={styles.tabRow}>
        <Pressable
          style={[styles.tabPill, tab === 'followers' && styles.tabPillActive]}
          onPress={() => setTab('followers')}
        >
          <Text style={[styles.tabText, tab === 'followers' && styles.tabTextActive]}>
            Followers{!isLoading ? ` (${followers.length})` : ''}
          </Text>
        </Pressable>
        <Pressable
          style={[styles.tabPill, tab === 'following' && styles.tabPillActive]}
          onPress={() => setTab('following')}
        >
          <Text style={[styles.tabText, tab === 'following' && styles.tabTextActive]}>
            Following{!isLoading ? ` (${following.length})` : ''}
          </Text>
        </Pressable>
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text muted style={styles.loadingText}>Loading…</Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <View style={styles.center}>
              <View style={styles.emptyIcon}>
                <Ionicons
                  name={tab === 'followers' ? 'people-outline' : 'person-add-outline'}
                  size={48}
                  color={colors.mutedForeground}
                />
              </View>
              <Text style={styles.emptyTitle}>
                {tab === 'followers' ? 'No Followers Yet' : 'Not Following Anyone'}
              </Text>
              <Text muted style={styles.emptySubtitle}>
                {tab === 'followers'
                  ? 'When people follow this account,\nthey\'ll show up here.'
                  : 'Follow people to see them here.'}
              </Text>
            </View>
          }
        />
      )}
    </GradientScreen>
  );
}

const AVATAR_SIZE = 48;

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
  headerTitle: {
    fontSize: fontSizes.xl,
    ...fonts.bold,
    color: colors.foreground,
  },
  backButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
  },

  // ── Tab pills ──
  tabRow: {
    flexDirection: 'row',
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    backgroundColor: 'rgba(255,255,255,0.4)',
    borderRadius: radii.full,
    padding: 3,
  },
  tabPill: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
  },
  tabPillActive: {
    backgroundColor: 'rgba(255,255,255,0.8)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 2,
  },
  tabText: {
    color: colors.mutedForeground,
    ...fonts.medium,
    fontSize: fontSizes.sm,
  },
  tabTextActive: {
    color: colors.foreground,
    ...fonts.semibold,
  },

  // ── List ──
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },

  // ── User card ──
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.md,
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarFallback: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    color: '#fff',
    ...fonts.bold,
    fontSize: fontSizes.base,
  },
  userInfo: {
    flex: 1,
    gap: 1,
  },
  displayName: {
    ...fonts.semibold,
    fontSize: fontSizes.base,
    color: colors.foreground,
  },
  username: {
    fontSize: fontSizes.sm,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginTop: 2,
  },
  locationText: {
    fontSize: fontSizes.xs,
  },
  distText: {
    fontSize: fontSizes.xs,
  },

  // ── Follow button ──
  followBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
    minWidth: 84,
    alignItems: 'center',
  },
  followBtnActive: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  followBtnText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
  followBtnTextActive: {
    color: colors.foreground,
  },

  // ── Center / empty states ──
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
  },
  loadingText: {
    marginTop: spacing.md,
    fontSize: fontSizes.sm,
  },
  emptyIcon: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  emptyTitle: {
    fontSize: fontSizes.lg,
    ...fonts.semibold,
    color: colors.foreground,
    marginBottom: spacing.xs,
  },
  emptySubtitle: {
    fontSize: fontSizes.sm,
    textAlign: 'center',
    lineHeight: 20,
  },
});
