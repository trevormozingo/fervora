import { useState, useEffect, useCallback, useRef } from 'react';
import { Alert, Animated, FlatList, Pressable, StyleSheet, View } from 'react-native';
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

      return (
        <Pressable
          style={styles.row}
          onPress={() =>
            router.push({
              pathname: '/conversation',
              params: { conversationId: item.id, otherUid: others.join(',') },
            })
          }
          onLongPress={() => handleDelete(item.id)}
        >
          <View style={styles.avatar}>
            <Ionicons
              name={isGroup ? 'people' : 'person'}
              size={22}
              color={colors.mutedForeground}
            />
          </View>
          <View style={styles.rowContent}>
            <View style={styles.rowHeader}>
              <Text style={styles.username} numberOfLines={1}>{displayName}</Text>
              <Text style={styles.time}>{formatTime(item.lastMessageAt)}</Text>
            </View>
            {item.lastMessage ? (
              <Text style={styles.preview} numberOfLines={1}>
                {item.lastMessage}
              </Text>
            ) : (
              <Text style={[styles.preview, { fontStyle: 'italic' }]}>
                No messages yet
              </Text>
            )}
          </View>
        </Pressable>
      );
    },
    [profiles, myUid, handleDelete],
  );

  return (
    <GradientScreen transparent>
      <View style={styles.header}>
        <Text style={styles.title}>Messages</Text>
        <Pressable
          style={styles.composeBtn}
          onPress={() => router.push('/new-chat')}
          hitSlop={12}
        >
          <Ionicons name="create-outline" size={24} color={colors.foreground} />
        </Pressable>
      </View>
      {loading ? (
        <View style={styles.center}>
          <Text muted>Loading…</Text>
        </View>
      ) : conversations.length === 0 ? (
        <View style={styles.center}>
          <Text muted>No conversations yet.</Text>
          <Pressable onPress={() => router.push('/new-chat')}>
            <Text style={styles.startChat}>Start a chat</Text>
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

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  title: {
    fontSize: fontSizes['2xl'],
    ...fonts.bold,
    color: colors.foreground,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.xs,
  },
  list: {
    paddingHorizontal: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  rowContent: {
    flex: 1,
    gap: 2,
  },
  rowHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  username: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  time: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
  preview: {
    fontSize: fontSizes.sm,
    color: colors.mutedForeground,
  },
  composeBtn: {
    padding: spacing.xs,
  },
  startChat: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.primary,
    marginTop: spacing.sm,
  },
});
