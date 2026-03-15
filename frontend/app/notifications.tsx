import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, Image, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, fonts, fontSizes, radii } from '@/components/ui';
import { setScrollToPostIntent } from '@/services/scrollToPost';
import { apiFetch } from '@/services/api';

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
  event_invite: 'calendar',
  event_rsvp: 'calendar',
};

export default function NotificationsScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: notifications = [], isLoading, isRefetching } = useQuery({
    queryKey: ['notifications'],
    queryFn: async () => {
      const data = await apiFetch<{ items: Notification[] }>('/profile/notifications?limit=50');
      return data.items;
    },
    refetchOnMount: 'always',
  });

  const onRefresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['notifications'] });
  }, [queryClient]);

  // Mark all as read on focus
  useFocusEffect(
    useCallback(() => {
      (async () => {
        try {
          await apiFetch('/profile/notifications/mark-read', { method: 'POST' });
          queryClient.setQueryData<Notification[]>(['notifications'], (old) =>
            old?.map((n) => ({ ...n, read: true }))
          );
          queryClient.setQueryData(['unreadNotifCount'], { count: 0 });
        } catch {}
      })();
    }, [queryClient])
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
    if (notif.type === 'event_invite' || notif.type === 'event_rsvp') {
      if (notif.data?.eventId) {
        router.push({ pathname: '/event/[id]', params: { id: notif.data.eventId } } as any);
      }
    } else if (notif.type === 'follow' && notif.data?.followerUsername) {
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
          <View style={styles.avatarContainer}>
            {photo ? (
              <Image source={{ uri: photo }} style={styles.avatarPhoto} />
            ) : (
              <View style={styles.avatarFallback}>
                <Ionicons name="person" size={18} color={colors.mutedForeground} />
              </View>
            )}
            <View style={[styles.typeBadge, !item.read && styles.typeBadgeUnread]}>
              <Ionicons name={iconName} size={10} color={!item.read ? '#fff' : colors.mutedForeground} />
            </View>
          </View>
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
      {isLoading ? (
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
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={onRefresh} tintColor={colors.primary} />
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
  avatarContainer: {
    position: 'relative',
    width: 40,
    height: 40,
    marginTop: 2,
  },
  avatarPhoto: {
    width: 40,
    height: 40,
    borderRadius: 20,
  },
  avatarFallback: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  typeBadge: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colors.background,
  },
  typeBadgeUnread: {
    backgroundColor: colors.brandRed,
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
