import { useState, useCallback } from 'react';
import { ActivityIndicator, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, fonts, fontSizes, radii } from '@/components/ui';
import { getIdToken } from '@/services/auth';
import { setScrollToPostIntent } from '@/services/scrollToPost';
import { config } from '@/config';

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, string>;
  read: boolean;
  createdAt: string;
}

const TYPE_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  comment: 'chatbubble',
  reaction: 'heart',
  message: 'mail',
  follow: 'person-add',
};

export default function NotificationsScreen() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchNotifications = useCallback(async () => {
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/profile/notifications?limit=50`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.items);
      }
    } catch {}
    setLoading(false);
  }, []);

  const markAllRead = useCallback(async () => {
    try {
      const token = getIdToken();
      await fetch(`${config.apiBaseUrl}/profile/notifications/mark-read`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchNotifications();
      // Mark all as read when viewing
      markAllRead();
    }, [])
  );

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d`;
    return d.toLocaleDateString();
  };

  const handlePress = (notif: Notification) => {
    if (notif.type === 'follow' && notif.data?.followerUsername) {
      // Navigate to the follower's profile
      router.push(`/user/${notif.data.followerUsername}` as any);
    } else if (notif.type === 'comment' || notif.type === 'reaction') {
      if (notif.data?.postId) {
        setScrollToPostIntent(
          notif.data.postId,
          notif.type === 'comment' ? 'comments' : 'reactions',
          notif.data.reactionType,
        );
      }
      router.navigate('/(home)/profile' as any);
    } else if (notif.data?.conversationId) {
      router.push({
        pathname: '/conversation',
        params: {
          conversationId: notif.data.conversationId,
          otherUid: notif.data.otherUid ?? '',
        },
      });
    }
  };

  const renderNotification = useCallback(
    ({ item }: { item: Notification }) => {
      const iconName = TYPE_ICONS[item.type] ?? 'notifications';
      const photo = item.data?.profilePhoto;
      return (
        <Pressable
          style={[styles.row, !item.read && styles.unreadRow]}
          onPress={() => handlePress(item)}
        >
          {photo ? (
            <Image source={{ uri: photo }} style={styles.avatarPhoto} />
          ) : (
            <View style={[styles.iconCircle, !item.read && styles.unreadIcon]}>
              <Ionicons name={iconName} size={18} color={!item.read ? '#fff' : colors.mutedForeground} />
            </View>
          )}
          <View style={styles.content}>
            <Text style={[styles.title, !item.read && styles.unreadTitle]} numberOfLines={2}>
              {item.title}
            </Text>
            {item.body ? (
              <Text style={styles.body} numberOfLines={1}>
                {item.body}
              </Text>
            ) : null}
            <Text style={styles.time}>{formatTime(item.createdAt)}</Text>
          </View>
        </Pressable>
      );
    },
    [],
  );

  return (
    <GradientScreen transparent>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={28} color={colors.foreground} />
        </Pressable>
        <Text style={styles.headerTitle}>Notifications</Text>
        <View style={{ width: 28 }} />
      </View>
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : notifications.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="notifications-off-outline" size={48} color={colors.mutedForeground} />
          <Text muted style={{ marginTop: spacing.sm }}>No notifications yet</Text>
        </View>
      ) : (
        <FlatList
          data={notifications}
          keyExtractor={(n) => n.id}
          renderItem={renderNotification}
          contentContainerStyle={styles.list}
        />
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
  list: {
    paddingHorizontal: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: spacing.md,
    gap: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  unreadRow: {
    backgroundColor: 'rgba(245, 81, 95, 0.06)',
    marginHorizontal: -spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
  },
  iconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 2,
  },
  avatarPhoto: {
    width: 36,
    height: 36,
    borderRadius: 18,
    marginTop: 2,
  },
  unreadIcon: {
    backgroundColor: colors.primary,
  },
  content: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.foreground,
  },
  unreadTitle: {
    ...fonts.bold,
  },
  body: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
  time: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
    marginTop: 2,
  },
});
