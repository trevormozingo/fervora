import { useEffect, useState, useCallback } from 'react';
import { ActivityIndicator, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, radii } from '@/components/ui';
import { getIdToken, getUid } from '@/services/auth';
import { config } from '@/config';

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
  const [followers, setFollowers] = useState<FollowUser[]>([]);
  const [following, setFollowing] = useState<FollowUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [myFollowingSet, setMyFollowingSet] = useState<Set<string>>(new Set());
  const [followLoadingIds, setFollowLoadingIds] = useState<Set<string>>(new Set());
  const [myLocation, setMyLocation] = useState<[number, number] | null>(null);

  /** Toggle follow / unfollow for a user */
  const toggleFollow = useCallback(async (targetUid: string) => {
    setFollowLoadingIds((prev) => new Set(prev).add(targetUid));
    try {
      const token = getIdToken();
      const isFollowing = myFollowingSet.has(targetUid);
      const method = isFollowing ? 'DELETE' : 'POST';
      const res = await fetch(`${config.apiBaseUrl}/follows/${targetUid}`, {
        method,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok || res.status === 201 || res.status === 204) {
        setMyFollowingSet((prev) => {
          const next = new Set(prev);
          if (isFollowing) next.delete(targetUid);
          else next.add(targetUid);
          return next;
        });
      }
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

  useEffect(() => {
    (async () => {
      try {
        const token = getIdToken();
        const headers: Record<string, string> = token
          ? { Authorization: `Bearer ${token}` }
          : {};
        const followersUrl = uid
          ? `${config.apiBaseUrl}/follows/${uid}/followers`
          : `${config.apiBaseUrl}/follows/followers`;
        const followingUrl = uid
          ? `${config.apiBaseUrl}/follows/${uid}/following`
          : `${config.apiBaseUrl}/follows/following`;
        const [followersRes, followingRes, myFollowingRes, profileRes] = await Promise.all([
          fetch(followersUrl, { headers }),
          fetch(followingUrl, { headers }),
          fetch(`${config.apiBaseUrl}/follows/following`, { headers }),
          fetch(`${config.apiBaseUrl}/profile`, { headers }),
        ]);
        if (followersRes.ok) {
          const data = await followersRes.json();
          setFollowers(data.followers);
        }
        if (followingRes.ok) {
          const data = await followingRes.json();
          setFollowing(data.following);
        }
        if (myFollowingRes.ok) {
          const data = await myFollowingRes.json();
          const ids = (data.following as { id: string }[]).map((u) => u.id);
          setMyFollowingSet(new Set(ids));
        }
        if (profileRes.ok) {
          const profile = await profileRes.json();
          if (profile.location?.coordinates) {
            setMyLocation(profile.location.coordinates);
          }
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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
        style={styles.userRow}
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
          <Text muted>@{item.username}</Text>
          {(item.location?.label || dist != null) && (
            <View style={styles.locationRow}>
              {item.location?.label && (
                <>
                  <Ionicons name="location-outline" size={12} color={colors.mutedForeground} />
                  <Text muted style={styles.locationText}>{item.location.label}</Text>
                </>
              )}
              {dist != null && (
                <Text muted style={styles.locationText}>
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
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.foreground} />
        </Pressable>
      </View>

      <View style={styles.tabRow}>
        <Pressable
          style={[styles.tab, tab === 'followers' && styles.tabActive]}
          onPress={() => setTab('followers')}
        >
          <Text
            style={[
              styles.tabText,
              tab === 'followers' && styles.tabTextActive,
            ]}
          >
            Followers
          </Text>
        </Pressable>
        <Pressable
          style={[styles.tab, tab === 'following' && styles.tabActive]}
          onPress={() => setTab('following')}
        >
          <Text
            style={[
              styles.tabText,
              tab === 'following' && styles.tabTextActive,
            ]}
          >
            Following
          </Text>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text muted>
                {tab === 'followers'
                  ? 'No followers yet.'
                  : "You're not following anyone yet."}
              </Text>
            </View>
          }
        />
      )}
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  backButton: {
    padding: spacing.xs,
  },
  tabRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  tabActive: {
    borderBottomWidth: 2,
    borderBottomColor: colors.foreground,
  },
  tabText: {
    color: colors.mutedForeground,
    fontWeight: '500',
  },
  tabTextActive: {
    color: colors.foreground,
    fontWeight: '700',
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: spacing['2xl'],
  },
  listContent: {
    paddingHorizontal: spacing.lg,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.muted,
    marginRight: spacing.md,
  },
  avatarFallback: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  avatarText: {
    fontWeight: '700',
    fontSize: 18,
    color: colors.foreground,
  },
  userInfo: {
    flex: 1,
    gap: 2,
  },
  displayName: {
    fontWeight: '600',
    color: colors.foreground,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginTop: 2,
  },
  locationText: {
    fontSize: 13,
  },
  followBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radii.sm,
    minWidth: 80,
    alignItems: 'center',
  },
  followBtnActive: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.border,
  },
  followBtnText: {
    color: colors.primaryForeground,
    fontWeight: '600',
    fontSize: 13,
  },
  followBtnTextActive: {
    color: colors.foreground,
  },
});
