import { useState, useCallback } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, colors, spacing, floatingButton } from '@/components/ui';
import { ProfileView, type ProfileData } from '@/components/ProfileView';
import { type Post } from '@/components/PostCard';
import { getIdToken } from '@/services/auth';
import { config } from '@/config';

export default function ProfileScreen() {
  const router = useRouter();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [followersCount, setFollowersCount] = useState(0);
  const [followingCount, setFollowingCount] = useState(0);
  const [posts, setPosts] = useState<Post[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);

  const fetchProfile = useCallback(async () => {
    try {
      const token = getIdToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const [profileRes, followersRes, followingRes] = await Promise.all([
        fetch(`${config.apiBaseUrl}/profile`, { headers }),
        fetch(`${config.apiBaseUrl}/follows/followers`, { headers }),
        fetch(`${config.apiBaseUrl}/follows/following`, { headers }),
      ]);
      if (profileRes.ok) {
        setProfile(await profileRes.json());
      }
      if (followersRes.ok) {
        const data = await followersRes.json();
        setFollowersCount(data.count);
      }
      if (followingRes.ok) {
        const data = await followingRes.json();
        setFollowingCount(data.count);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchProfile();
      fetchPosts();
    }, [])
  );

  const fetchPosts = useCallback(async (cursorVal?: string | null) => {
    if (postsLoading) return;
    setPostsLoading(true);
    try {
      const token = getIdToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const params = new URLSearchParams({ limit: '20' });
      if (cursorVal) params.set('cursor', cursorVal);
      const res = await fetch(`${config.apiBaseUrl}/posts?${params}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setPosts((prev) => (cursorVal ? [...prev, ...data.items] : data.items));
        setCursor(data.cursor);
        setHasMore(data.count === 20);
      }
    } catch {
      // ignore
    } finally {
      setPostsLoading(false);
    }
  }, [postsLoading]);

  const loadMore = () => {
    if (hasMore && !postsLoading && cursor) {
      fetchPosts(cursor);
    }
  };

  const handlePostChanged = (updated: Post) => {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleDeletePost = async (postId: string) => {
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/posts/${postId}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok || res.status === 204) {
        setPosts((prev) => prev.filter((p) => p.id !== postId));
      }
    } catch {
      // ignore
    }
  };

  if (loading) {
    return (
      <GradientScreen transparent>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </GradientScreen>
    );
  }

  return (
    <GradientScreen transparent>
      <Pressable
        style={styles.settingsButton}
        onPress={() => router.push('/settings')}
      >
        <Ionicons name="settings-outline" size={24} color={colors.foreground} />
      </Pressable>
      <Pressable
        style={styles.editButton}
        onPress={() => router.push('/edit-profile')}
      >
        <Ionicons name="pencil-outline" size={22} color={colors.foreground} />
      </Pressable>
      <Pressable
        style={styles.addPostButton}
        onPress={() => router.push('/create-post')}
      >
        <Ionicons name="add" size={26} color={colors.foreground} />
      </Pressable>

      <ProfileView
        profile={profile}
        followersCount={followersCount}
        followingCount={followingCount}
        isOwnProfile
        posts={posts}
        postsLoading={postsLoading}
        onLoadMore={loadMore}
        onPostChanged={handlePostChanged}
        onDeletePost={handleDeletePost}
      />
    </GradientScreen>
  );
}

const styles = StyleSheet.create({

  settingsButton: {
    ...floatingButton,
    top: 60,
    right: spacing.lg,
  },
  editButton: {
    ...floatingButton,
    top: 112,
    right: spacing.lg,
  },
  addPostButton: {
    ...floatingButton,
    top: 164,
    right: spacing.lg,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
