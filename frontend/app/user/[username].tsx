import { useState, useCallback } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, colors, spacing } from '@/components/ui';
import { ProfileView, type ProfileData } from '@/components/ProfileView';
import { type Post } from '@/components/PostCard';
import { getIdToken, getUid } from '@/services/auth';
import { config } from '@/config';
import { getOrCreateConversation } from '@/services/messaging';

export default function UserProfileScreen() {
  const router = useRouter();
  const { username } = useLocalSearchParams<{ username: string }>();

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [followersCount, setFollowersCount] = useState(0);
  const [followingCount, setFollowingCount] = useState(0);
  const [posts, setPosts] = useState<Post[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [isFollowing, setIsFollowing] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);

  const fetchProfile = useCallback(async () => {
    if (!username) return;
    try {
      const token = getIdToken();
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      const res = await fetch(`${config.apiBaseUrl}/profile/${username}`, {
        headers,
      });
      if (res.ok) {
        const data: ProfileData = await res.json();
        setProfile(data);
        return data;
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
    return null;
  }, [username]);

  const fetchFollowData = useCallback(
    async (uid: string) => {
      const token = getIdToken();
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      const [followersRes, followingRes, myFollowingRes] = await Promise.all([
        fetch(`${config.apiBaseUrl}/follows/${uid}/followers`, { headers }),
        fetch(`${config.apiBaseUrl}/follows/${uid}/following`, { headers }),
        fetch(`${config.apiBaseUrl}/follows/following`, { headers }),
      ]);
      if (followersRes.ok) {
        const data = await followersRes.json();
        setFollowersCount(data.count);
      }
      if (followingRes.ok) {
        const data = await followingRes.json();
        setFollowingCount(data.count);
      }
      if (myFollowingRes.ok) {
        const data = await myFollowingRes.json();
        const following = data.following as { id: string }[];
        setIsFollowing(following.some((u) => u.id === uid));
      }
    },
    [],
  );

  const fetchPosts = useCallback(
    async (uid: string, cursorVal?: string | null) => {
      if (postsLoading) return;
      setPostsLoading(true);
      try {
        const token = getIdToken();
        const headers: Record<string, string> = token
          ? { Authorization: `Bearer ${token}` }
          : {};
        const params = new URLSearchParams({ limit: '20' });
        if (cursorVal) params.set('cursor', cursorVal);
        const res = await fetch(
          `${config.apiBaseUrl}/posts/user/${uid}?${params}`,
          { headers },
        );
        if (res.ok) {
          const data = await res.json();
          setPosts((prev) =>
            cursorVal ? [...prev, ...data.items] : data.items,
          );
          setCursor(data.cursor);
          setHasMore(data.count === 20);
        }
      } catch {
        // ignore
      } finally {
        setPostsLoading(false);
      }
    },
    [postsLoading],
  );

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const p = await fetchProfile();
        if (p) {
          fetchFollowData(p.id);
          fetchPosts(p.id);
        }
      })();
    }, [username]),
  );

  const handleFollow = async () => {
    if (!profile || followLoading) return;
    setFollowLoading(true);
    try {
      const token = getIdToken();
      const headers: Record<string, string> = {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };
      const method = isFollowing ? 'DELETE' : 'POST';
      const res = await fetch(
        `${config.apiBaseUrl}/follows/${profile.id}`,
        { method, headers },
      );
      if (res.ok || res.status === 201 || res.status === 204) {
        setIsFollowing(!isFollowing);
        setFollowersCount((c) => c + (isFollowing ? -1 : 1));
      }
    } catch {
      // ignore
    } finally {
      setFollowLoading(false);
    }
  };

  const handlePostChanged = (updated: Post) => {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleMessage = useCallback(async () => {
    const myUid = getUid();
    if (!myUid || !profile) return;
    const conversationId = await getOrCreateConversation(myUid, profile.id);
    router.push({
      pathname: '/conversation',
      params: { conversationId, otherUid: profile.id },
    });
  }, [profile, router]);

  const loadMore = () => {
    if (hasMore && !postsLoading && cursor && profile) {
      fetchPosts(profile.id, cursor);
    }
  };

  if (loading) {
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
      </View>

      <ProfileView
        profile={profile}
        followersCount={followersCount}
        followingCount={followingCount}
        isOwnProfile={profile?.id === getUid()}
        posts={posts}
        postsLoading={postsLoading}
        onLoadMore={loadMore}
        onPostChanged={handlePostChanged}
        followListParams={profile ? `&uid=${profile.id}` : ''}
        isFollowing={isFollowing}
        followLoading={followLoading}
        onFollowToggle={profile?.id !== getUid() ? handleFollow : undefined}
        onMessage={profile?.id !== getUid() ? handleMessage : undefined}
      />
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
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
