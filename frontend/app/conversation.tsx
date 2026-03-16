import { useState, useEffect, useRef, useCallback } from 'react';
import {
  FlatList,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, fonts, fontSizes, radii } from '@/components/ui';
import { getUid, getIdToken } from '@/services/auth';
import { sendMessage, subscribeToMessages, markConversationRead, type Message } from '@/services/messaging';
import { sendPushToUsers } from '@/services/notifications';
import { config } from '@/config';

export default function ConversationScreen() {
  const router = useRouter();
  const { conversationId, otherUid } = useLocalSearchParams<{
    conversationId: string;
    otherUid: string;
  }>();
  const myUid = getUid();

  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [headerLabel, setHeaderLabel] = useState<string>('');
  const [participantProfiles, setParticipantProfiles] = useState<
    Record<string, { name: string; photo?: string }>
  >({});
  const flatListRef = useRef<FlatList>(null);

  const otherUids = (otherUid ?? '').split(',').filter(Boolean);
  const isGroup = otherUids.length > 1;

  // Resolve participant usernames (including self, for push notification title)
  useEffect(() => {
    if (otherUids.length === 0) return;
    const allUids = myUid ? [...otherUids, myUid] : otherUids;
    (async () => {
      const token = getIdToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const resolved: Record<string, { name: string; photo?: string }> = {};
      try {
        const res = await fetch(`${config.apiBaseUrl}/profile/batch`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ uids: allUids }),
        });
        if (res.ok) {
          const profiles: { id: string; username: string; profilePhoto?: string }[] = await res.json();
          for (const p of profiles) {
            resolved[p.id] = { name: p.username ?? p.id.slice(0, 8), photo: p.profilePhoto };
          }
        }
      } catch {}
      setParticipantProfiles(resolved);
      setHeaderLabel(
        otherUids.map((uid) => resolved[uid]?.name ?? uid.slice(0, 8)).join(', '),
      );
    })();
  }, [otherUid]);

  // Subscribe to messages
  useEffect(() => {
    if (!conversationId) return;
    // Mark conversation as read
    if (myUid) markConversationRead(conversationId, myUid).catch(() => {});
    const unsub = subscribeToMessages(conversationId, (msgs) => {
      setMessages(msgs);
      // Scroll to bottom on new messages
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
      // Mark as read when new messages arrive
      if (myUid) markConversationRead(conversationId, myUid).catch(() => {});
    });
    return unsub;
  }, [conversationId]);

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || !conversationId || !myUid || sending) return;
    setSending(true);
    setText('');
    try {
      await sendMessage(conversationId, myUid, trimmed);
      // Send push notification to other participants (fire-and-forget)
      const myName = participantProfiles[myUid]?.name || 'Someone';
      sendPushToUsers(
        otherUids,
        myName,
        trimmed,
        { conversationId, otherUid: myUid },
      );
    } catch {
      setText(trimmed); // Restore on failure
    } finally {
      setSending(false);
    }
  }, [text, conversationId, myUid, sending, otherUids, participantProfiles]);

  const renderMessage = useCallback(
    ({ item }: { item: Message }) => {
      const isMe = item.senderUid === myUid;
      const senderProfile = participantProfiles[item.senderUid];
      const senderPhoto = senderProfile?.photo;

      return (
        <View style={[styles.messageRow, isMe && styles.messageRowMe]}>
          {!isMe && (
            senderPhoto ? (
              <Image source={{ uri: senderPhoto }} style={styles.msgAvatar} />
            ) : (
              <View style={styles.msgAvatarFallback}>
                <Ionicons name="person" size={14} color={colors.mutedForeground} />
              </View>
            )
          )}
          <View
            style={[
              styles.bubble,
              isMe ? styles.bubbleMe : styles.bubbleThem,
            ]}
          >
            {isGroup && !isMe && (
              <Text style={styles.senderName}>
                {senderProfile?.name ?? item.senderUid.slice(0, 8)}
              </Text>
            )}
            <Text
              style={[
                styles.bubbleText,
                isMe ? styles.bubbleTextMe : styles.bubbleTextThem,
              ]}
            >
              {item.text}
            </Text>
            {item.createdAt && (
              <Text style={[styles.bubbleTime, isMe && styles.bubbleTimeMe]}>
                {item.createdAt.toLocaleTimeString([], {
                  hour: 'numeric',
                  minute: '2-digit',
                })}
              </Text>
            )}
          </View>
        </View>
      );
    },
    [myUid, isGroup, participantProfiles],
  );

  return (
    <GradientScreen>
      {/* Header */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={28} color={colors.foreground} />
        </Pressable>
        <Pressable
          style={styles.headerCenter}
          onPress={() => {
            if (!isGroup && otherUids[0] && participantProfiles[otherUids[0]]) {
              router.push({
                pathname: '/user/[username]',
                params: { username: participantProfiles[otherUids[0]].name },
              });
            }
          }}
        >
          {isGroup ? (
            (() => {
              const photos = otherUids
                .map((uid) => participantProfiles[uid]?.photo)
                .filter(Boolean) as string[];
              if (photos.length >= 2) {
                return (
                  <View style={styles.headerStackedContainer}>
                    <Image source={{ uri: photos[0] }} style={styles.headerStackedBack} />
                    <Image source={{ uri: photos[1] }} style={styles.headerStackedFront} />
                  </View>
                );
              }
              if (photos.length === 1) {
                return <Image source={{ uri: photos[0] }} style={styles.headerAvatar} />;
              }
              return (
                <View style={styles.headerAvatarFallback}>
                  <Ionicons name="people" size={18} color={colors.mutedForeground} />
                </View>
              );
            })()
          ) : (
            (() => {
              const photo = otherUids[0] && participantProfiles[otherUids[0]]?.photo;
              if (photo) {
                return <Image source={{ uri: photo }} style={styles.headerAvatar} />;
              }
              return (
                <View style={styles.headerAvatarFallback}>
                  <Ionicons name="person" size={18} color={colors.mutedForeground} />
                </View>
              );
            })()
          )}
          <Text style={styles.headerName} numberOfLines={1}>
            {headerLabel || 'Chat'}
          </Text>
        </Pressable>
        <View style={{ width: 28 }} />
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        {/* Messages */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(m) => m.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          onContentSizeChange={() =>
            flatListRef.current?.scrollToEnd({ animated: false })
          }
        />

        {/* Composer */}
        <View style={styles.composer}>
          <TextInput
            style={styles.input}
            placeholder="Message…"
            placeholderTextColor={colors.placeholder}
            value={text}
            onChangeText={setText}
            multiline
            maxLength={2000}
            returnKeyType="default"
          />
          <Pressable
            style={[
              styles.sendBtn,
              (!text.trim() || sending) && styles.sendBtnDisabled,
            ]}
            onPress={handleSend}
            disabled={!text.trim() || sending}
          >
            <Ionicons
              name="arrow-up"
              size={20}
              color={colors.primaryForeground}
            />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  headerCenter: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  headerAvatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
  },
  headerAvatarFallback: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerStackedContainer: {
    width: 38,
    height: 32,
  },
  headerStackedBack: {
    width: 24,
    height: 24,
    borderRadius: 12,
    position: 'absolute',
    top: 0,
    left: 0,
  },
  headerStackedFront: {
    width: 24,
    height: 24,
    borderRadius: 12,
    position: 'absolute',
    bottom: 0,
    right: 0,
    borderWidth: 2,
    borderColor: colors.background,
  },
  headerName: {
    fontSize: fontSizes.lg,
    ...fonts.semibold,
    color: colors.foreground,
  },
  messageList: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    flexGrow: 1,
    justifyContent: 'flex-end',
  },
  messageRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginVertical: 3,
    gap: 6,
  },
  messageRowMe: {
    justifyContent: 'flex-end',
  },
  msgAvatar: {
    width: 26,
    height: 26,
    borderRadius: 13,
    marginBottom: 2,
  },
  msgAvatarFallback: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 2,
  },
  bubble: {
    maxWidth: '78%',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 18,
  },
  bubbleMe: {
    alignSelf: 'flex-end',
    backgroundColor: colors.primary,
  },
  bubbleThem: {
    alignSelf: 'flex-start',
    backgroundColor: colors.muted,
  },
  senderName: {
    fontSize: fontSizes.xs,
    ...fonts.semibold,
    color: colors.mutedForeground,
    marginBottom: 2,
  },
  bubbleText: {
    fontSize: fontSizes.base,
    lineHeight: 21,
  },
  bubbleTextMe: {
    color: colors.primaryForeground,
  },
  bubbleTextThem: {
    color: colors.foreground,
  },
  bubbleTime: {
    fontSize: 10,
    color: colors.mutedForeground,
    marginTop: 2,
  },
  bubbleTimeMe: {
    color: 'rgba(255,255,255,0.6)',
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  input: {
    flex: 1,
    minHeight: 38,
    maxHeight: 120,
    borderRadius: radii.xl,
    backgroundColor: colors.muted,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: fontSizes.base,
    color: colors.foreground,
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: radii.full,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    opacity: 0.4,
  },
});
