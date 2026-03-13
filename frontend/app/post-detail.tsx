import { useState, useEffect } from 'react';
import { ActivityIndicator, ScrollView, Pressable, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, fonts, fontSizes } from '@/components/ui';
import { PostCard, type Post } from '@/components/PostCard';
import { getIdToken } from '@/services/auth';
import { config } from '@/config';

export default function PostDetailScreen() {
  const router = useRouter();
  const { postId } = useLocalSearchParams<{ postId: string }>();
  const [post, setPost] = useState<Post | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!postId) return;
    (async () => {
      try {
        const token = getIdToken();
        const res = await fetch(`${config.apiBaseUrl}/posts/${postId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          setPost(await res.json());
        } else {
          setError(true);
        }
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [postId]);

  return (
    <GradientScreen>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={28} color={colors.foreground} />
        </Pressable>
        <Text style={styles.headerTitle}>Post</Text>
        <View style={{ width: 28 }} />
      </View>
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : error || !post ? (
        <View style={styles.center}>
          <Text muted>Post not found</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <PostCard
            post={post}
            showAuthor
            onPostChanged={setPost}
          />
        </ScrollView>
      )}
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  headerTitle: {
    fontSize: fontSizes.xl,
    ...fonts.bold,
    color: colors.foreground,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xl,
  },
});
