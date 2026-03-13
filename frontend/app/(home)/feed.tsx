import { useState, useCallback } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { PostCard, type Post } from '@/components/PostCard';
import { getIdToken } from '@/services/auth';
import { config } from '@/config';

export default function FeedScreen() {
  const router = useRouter();
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [unreadNotifs, setUnreadNotifs] = useState(0);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/profile/notifications/unread-count`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setUnreadNotifs(data.count);
      }
    } catch {}
  }, []);

  const fetchPosts = useCallback(async (cursorVal?: string | null) => {
    if (loading) return;
    setLoading(true);
    try {
      const token = getIdToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const params = new URLSearchParams({ limit: '20' });
      if (cursorVal) params.set('cursor', cursorVal);
      const res = await fetch(`${config.apiBaseUrl}/feed?${params}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setPosts((prev) => (cursorVal ? [...prev, ...data.items] : data.items));
        setCursor(data.cursor);
        setHasMore(data.count === 20);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [loading]);

  useFocusEffect(
    useCallback(() => {
      fetchPosts();
      fetchUnreadCount();
    }, [])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    setCursor(null);
    setHasMore(true);
    try {
      const token = getIdToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`${config.apiBaseUrl}/feed?limit=20`, { headers });
      if (res.ok) {
        const data = await res.json();
        setPosts(data.items);
        setCursor(data.cursor);
        setHasMore(data.count === 20);
      }
    } catch {
      // ignore
    } finally {
      setRefreshing(false);
    }
  }, []);

  const loadMore = () => {
    if (hasMore && !loading && cursor) {
      fetchPosts(cursor);
    }
  };

  const handlePostChanged = (updated: Post) => {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  return (
    <GradientScreen transparent>
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }} />
        <Pressable
          style={styles.bellButton}
          onPress={() => router.push('/notifications')}
        >
          <Ionicons name="notifications-outline" size={24} color={colors.foreground} />
          {unreadNotifs > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>
                {unreadNotifs > 99 ? '99+' : unreadNotifs}
              </Text>
            </View>
          )}
        </Pressable>
        <Pressable
          style={styles.personButton}
          onPress={() => router.push('/friends')}
        >
          <Ionicons name="people-outline" size={24} color={colors.foreground} />
        </Pressable>
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
        refreshing={refreshing}
        onRefresh={onRefresh}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          !loading ? (
            <View style={styles.emptyState}>
              <Text muted>No posts in your feed yet. Follow some people!</Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          loading ? <ActivityIndicator style={styles.footerLoader} color={colors.primary} /> : null
        }
      />
    </GradientScreen>
  );
}

const styles = StyleSheet.create({

  personButton: {
    padding: 8,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: spacing.sm,
  },
  bellButton: {
    padding: 8,
  },
  badge: {
    position: 'absolute',
    top: 2,
    right: 2,
    backgroundColor: colors.primary,
    borderRadius: 9,
    minWidth: 18,
    height: 18,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  badgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
  },

  feedHeader: {
    paddingTop: spacing['2xl'],
    paddingBottom: spacing.lg,
    alignItems: 'center',
  },
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: 16,
  },
  emptyState: {
    alignItems: 'center',
    paddingTop: spacing['2xl'],
  },
  footerLoader: {
    paddingVertical: spacing.lg,
  },
});
