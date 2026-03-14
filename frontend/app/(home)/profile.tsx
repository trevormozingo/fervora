import { useState, useCallback } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { ProfileView, type ProfileData } from '@/components/ProfileView';
import { type Post } from '@/components/PostCard';
import { getIdToken } from '@/services/auth';
import { consumeScrollToPostIntent } from '@/services/scrollToPost';
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
  const [scrollToPostId, setScrollToPostId] = useState<string | null>(null);
  const [scrollToPostSection, setScrollToPostSection] = useState<'comments' | 'reactions' | null>(null);
  const [scrollToReactionType, setScrollToReactionType] = useState<string | undefined>(undefined);

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
      // Check for scroll-to-post intent from notification tap
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
        profile={profile}
        followersCount={followersCount}
        followingCount={followingCount}
        isOwnProfile
        posts={posts}
        postsLoading={postsLoading}
        onLoadMore={loadMore}
        onPostChanged={handlePostChanged}
        onDeletePost={handleDeletePost}
        scrollToPostId={scrollToPostId}
        scrollToPostSection={scrollToPostSection}
        scrollToReactionType={scrollToReactionType}
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
  },
});
