import { useState, useCallback } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing, fonts, fontSizes, radii } from '@/components/ui';
import { getUid, getIdToken } from '@/services/auth';
import { getOrCreateConversation, createGroupConversation } from '@/services/messaging';
import { config } from '@/config';

interface UserResult {
  id: string;
  username: string;
  displayName: string;
  profilePhoto?: string | null;
}

export default function NewChatScreen() {
  const router = useRouter();
  const myUid = getUid();

  const [searchText, setSearchText] = useState('');
  const [results, setResults] = useState<UserResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<UserResult[]>([]);
  const [creating, setCreating] = useState(false);

  // Debounced search
  const searchTimer = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleSearch = useCallback(
    (text: string) => {
      setSearchText(text);
      if (searchTimer[0]) clearTimeout(searchTimer[0]);
      if (!text.trim()) {
        setResults([]);
        return;
      }
      searchTimer[0] = setTimeout(async () => {
        setSearching(true);
        try {
          const token = getIdToken();
          const headers: Record<string, string> = token
            ? { Authorization: `Bearer ${token}` }
            : {};
          const res = await fetch(
            `${config.apiBaseUrl}/profile/search?q=${encodeURIComponent(text.trim())}`,
            { headers },
          );
          if (res.ok) {
            const data: UserResult[] = await res.json();
            // Filter out self and already-selected users
            setResults(
              data.filter(
                (u) => u.id !== myUid && !selected.some((s) => s.id === u.id),
              ),
            );
          } else {
            setResults([]);
          }
        } catch {
          setResults([]);
        } finally {
          setSearching(false);
        }
      }, 300);
    },
    [selected, myUid],
  );

  const toggleUser = (user: UserResult) => {
    setSelected((prev) => {
      const exists = prev.some((s) => s.id === user.id);
      if (exists) return prev.filter((s) => s.id !== user.id);
      return [...prev, user];
    });
    setSearchText('');
    setResults([]);
  };

  const removeSelected = (uid: string) => {
    setSelected((prev) => prev.filter((s) => s.id !== uid));
  };

  const startConversation = useCallback(async () => {
    if (!myUid || selected.length === 0 || creating) return;
    setCreating(true);
    try {
      let conversationId: string;
      const participantUids = selected.map((s) => s.id);

      if (participantUids.length === 1) {
        conversationId = await getOrCreateConversation(myUid, participantUids[0]);
      } else {
        conversationId = await createGroupConversation([myUid, ...participantUids]);
      }

      router.replace({
        pathname: '/conversation',
        params: {
          conversationId,
          otherUid: participantUids.join(','),
        },
      });
    } catch {
      // ignore
    } finally {
      setCreating(false);
    }
  }, [myUid, selected, creating, router]);

  return (
    <GradientScreen>
      {/* Header */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="close" size={26} color={colors.foreground} />
        </Pressable>
        <Text style={styles.title}>New Message</Text>
        <Pressable
          onPress={startConversation}
          disabled={selected.length === 0 || creating}
          hitSlop={12}
        >
          {creating ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Text
              style={[
                styles.nextBtn,
                selected.length === 0 && { opacity: 0.3 },
              ]}
            >
              Next
            </Text>
          )}
        </Pressable>
      </View>

      {/* Selected chips */}
      {selected.length > 0 && (
        <View style={styles.chipRow}>
          {selected.map((user) => (
            <Pressable
              key={user.id}
              style={styles.chip}
              onPress={() => removeSelected(user.id)}
            >
              <Text style={styles.chipText}>{user.username}</Text>
              <Ionicons name="close-circle" size={16} color={colors.mutedForeground} />
            </Pressable>
          ))}
        </View>
      )}

      {/* Search input */}
      <View style={styles.searchRow}>
        <Text style={styles.toLabel}>To:</Text>
        <TextInput
          style={styles.searchInput}
          placeholder="Search by username…"
          placeholderTextColor={colors.placeholder}
          value={searchText}
          onChangeText={handleSearch}
          autoCapitalize="none"
          autoCorrect={false}
          autoFocus
        />
        {searching && <ActivityIndicator size="small" color={colors.mutedForeground} />}
      </View>

      <View style={styles.divider} />

      {/* Results */}
      <FlatList
        data={results}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <Pressable style={styles.resultRow} onPress={() => toggleUser(item)}>
            {item.profilePhoto ? (
              <Image source={{ uri: item.profilePhoto }} style={styles.resultAvatarPhoto} />
            ) : (
              <View style={styles.resultAvatar}>
                <Ionicons name="person" size={20} color={colors.mutedForeground} />
              </View>
            )}
            <View style={styles.resultInfo}>
              <Text style={styles.resultName}>{item.displayName}</Text>
              <Text style={styles.resultUsername}>@{item.username}</Text>
            </View>
          </Pressable>
        )}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          searchText.trim().length > 0 && !searching ? (
            <View style={styles.emptyState}>
              <Text muted>No users found</Text>
            </View>
          ) : null
        }
      />
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  title: {
    fontSize: fontSizes.lg,
    ...fonts.semibold,
    color: colors.foreground,
  },
  nextBtn: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.primary,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.md,
    gap: spacing.xs,
    paddingBottom: spacing.sm,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.muted,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  chipText: {
    fontSize: fontSizes.sm,
    color: colors.foreground,
    ...fonts.medium,
  },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  toLabel: {
    fontSize: fontSizes.base,
    color: colors.mutedForeground,
    ...fonts.medium,
  },
  searchInput: {
    flex: 1,
    fontSize: fontSizes.base,
    color: colors.foreground,
    paddingVertical: 0,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
  },
  list: {
    paddingHorizontal: spacing.md,
  },
  resultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  resultAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  resultAvatarPhoto: {
    width: 44,
    height: 44,
    borderRadius: 22,
  },
  resultInfo: {
    flex: 1,
    gap: 2,
  },
  resultName: {
    fontSize: fontSizes.base,
    ...fonts.medium,
    color: colors.foreground,
  },
  resultUsername: {
    fontSize: fontSizes.sm,
    color: colors.mutedForeground,
  },
  emptyState: {
    paddingTop: spacing.xl,
    alignItems: 'center',
  },
});
