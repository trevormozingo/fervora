import { useState, useEffect, useCallback, useRef } from 'react';
import { ActivityIndicator, Alert, Animated, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, fonts, fontSizes, radii, floatingButton } from '@/components/ui';
import { getUid, getIdToken } from '@/services/auth';
import {
  subscribeToConversations,
  getOtherParticipants,
  hideConversation,
  type Conversation,
} from '@/services/messaging';
import { config } from '@/config';

/** Resolve UIDs → usernames + profile photos via the backend. */
async function resolveProfiles(
  uids: string[],
): Promise<Record<string, { username: string; profilePhoto?: string }>> {
  if (uids.length === 0) return {};
  const token = getIdToken();
  const headers: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};
  const map: Record<string, { username: string; profilePhoto?: string }> = {};
  await Promise.all(
    uids.map(async (uid) => {
      try {
        const res = await fetch(`${config.apiBaseUrl}/profile/uid/${uid}`, { headers });
        if (res.ok) {
          const data = await res.json();
          map[uid] = { username: data.username, profilePhoto: data.profilePhoto };
        }
      } catch {}
    }),
  );
  return map;
}

export default function MessagesScreen() {
  const router = useRouter();
  const myUid = getUid();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [profiles, setProfiles] = useState<
    Record<string, { username: string; profilePhoto?: string }>
  >({});
  const [loading, setLoading] = useState(true);

  // Subscribe to conversations
  useEffect(() => {
    if (!myUid) return;
    const unsub = subscribeToConversations(myUid, async (convos) => {
      setConversations(convos);
      setLoading(false);

      // Resolve any new participant UIDs
      const allOtherUids = convos.flatMap((c) => getOtherParticipants(c, myUid));
      const newUids = [...new Set(allOtherUids)].filter((uid) => uid && !profiles[uid]);
      if (newUids.length > 0) {
        const resolved = await resolveProfiles(newUids);
        setProfiles((prev) => ({ ...prev, ...resolved }));
      }
    });
    return unsub;
  }, [myUid]);

  const formatTime = (date: Date | null) => {
    if (!date) return '';
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / 86400000);
    if (days > 6) return date.toLocaleDateString();
    if (days > 0) return `${days}d`;
    return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  };

  const handleDelete = useCallback(
    (conversationId: string) => {
      Alert.alert('Delete Conversation', 'Remove this conversation from your list?', [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            if (myUid) await hideConversation(conversationId, myUid);
          },
        },
      ]);
    },
    [myUid],
  );

  const renderConversation = useCallback(
    ({ item }: { item: Conversation }) => {
      const others = getOtherParticipants(item, myUid ?? '');
      const isGroup = others.length > 1;
      const displayName = others
        .map((uid) => profiles[uid]?.username ?? uid.slice(0, 8))
        .join(', ');

      // Build avatar: single photo, stacked photos for group, or fallback icon
      const otherPhotos = others
        .map((uid) => profiles[uid]?.profilePhoto)
        .filter(Boolean) as string[];

      let avatarElement: React.ReactNode;
      if (!isGroup && otherPhotos.length > 0) {
        avatarElement = (
          <Image source={{ uri: otherPhotos[0] }} style={styles.avatarPhoto} />
        );
      } else if (isGroup && otherPhotos.length >= 2) {
        avatarElement = (
          <View style={styles.avatar}>
            <Image source={{ uri: otherPhotos[0] }} style={styles.stackedPhotoBack} />
            <Image source={{ uri: otherPhotos[1] }} style={styles.stackedPhotoFront} />
          </View>
        );
      } else if (isGroup && otherPhotos.length === 1) {
        avatarElement = (
          <View style={styles.avatar}>
            <Image source={{ uri: otherPhotos[0] }} style={styles.avatarPhoto} />
          </View>
        );
      } else {
        avatarElement = (
          <View style={styles.avatar}>
            <Ionicons
              name={isGroup ? 'people' : 'person'}
              size={22}
              color={colors.mutedForeground}
            />
          </View>
        );
      }

      return (
        <Pressable
          style={styles.conversationCard}
          onPress={() =>
            router.push({
              pathname: '/conversation',
              params: { conversationId: item.id, otherUid: others.join(',') },
            })
          }
          onLongPress={() => handleDelete(item.id)}
        >
          {avatarElement}
          <View style={styles.rowContent}>
            <View style={styles.rowHeader}>
              <Text style={[styles.username, item.unread && styles.unreadText]} numberOfLines={1}>{displayName}</Text>
              <Text muted style={styles.time}>{formatTime(item.lastMessageAt)}</Text>
            </View>
            {item.lastMessage ? (
              <Text style={[styles.preview, item.unread && styles.previewUnread]} numberOfLines={1}>
                {item.lastMessage}
              </Text>
            ) : (
              <Text muted style={[styles.preview, { fontStyle: 'italic' }]}>
                No messages yet
              </Text>
            )}
          </View>
          {item.unread && <View style={styles.unreadDot} />}
        </Pressable>
      );
    },
    [profiles, myUid, handleDelete],
  );

  return (
    <GradientScreen transparent>
      {/* ── Header ── */}
      <View style={styles.header}>
        <Text style={styles.title}>Messages</Text>
        <Pressable
          style={styles.composeBtn}
          onPress={() => router.push('/new-chat')}
          hitSlop={12}
        >
          <Ionicons name="create-outline" size={22} color={colors.foreground} />
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text muted style={styles.loadingText}>Loading conversations…</Text>
        </View>
      ) : conversations.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyIcon}>
            <Ionicons name="chatbubbles-outline" size={48} color={colors.mutedForeground} />
          </View>
          <Text style={styles.emptyTitle}>No Conversations</Text>
          <Text muted style={styles.emptySubtitle}>
            Start a chat with someone{"\n"}to see it here.
          </Text>
          <Pressable onPress={() => router.push('/new-chat')} style={styles.primaryPill}>
            <Ionicons name="chatbubble-ellipses" size={16} color={colors.primaryForeground} />
            <Text style={styles.pillText}>Start a Chat</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={conversations}
          keyExtractor={(c) => c.id}
          renderItem={renderConversation}
          contentContainerStyle={styles.list}
        />
      )}
    </GradientScreen>
  );
}

const AVATAR_SIZE = 50;

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
  title: {
    fontSize: fontSizes['2xl'],
    ...fonts.bold,
    color: colors.foreground,
  },
  composeBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },

  // ── List ──
  list: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },

  // ── Conversation card ──
  conversationCard: {
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
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarPhoto: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  stackedPhotoBack: {
    width: 34,
    height: 34,
    borderRadius: 17,
    position: 'absolute',
    top: 0,
    left: 0,
  },
  stackedPhotoFront: {
    width: 34,
    height: 34,
    borderRadius: 17,
    position: 'absolute',
    bottom: 0,
    right: 0,
    borderWidth: 2,
    borderColor: '#fff',
  },
  rowContent: {
    flex: 1,
    overflow: 'hidden',
    gap: 2,
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  username: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
    flexShrink: 1,
    marginRight: spacing.sm,
  },
  time: {
    fontSize: fontSizes.xs,
    flexShrink: 0,
    marginLeft: 'auto',
  },
  unreadDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.primary,
    marginLeft: spacing.xs,
  },
  unreadText: {
    ...fonts.bold,
  },
  preview: {
    fontSize: fontSizes.sm,
    color: colors.mutedForeground,
  },
  previewUnread: {
    color: colors.foreground,
    ...fonts.medium,
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

  // ── Pill buttons ──
  primaryPill: {
    marginTop: spacing.lg,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.full,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  pillText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
});
