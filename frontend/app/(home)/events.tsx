import { useState, useCallback } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, fonts, fontSizes, spacing, radii } from '@/components/ui';
import { getMyEvents, getInvitedEvents } from '@/services/events';
import { getUid } from '@/services/auth';
import { apiFetch } from '@/services/api';
import type { EventItem } from '@/models/event';

type Tab = 'invited' | 'mine';

function formatEventTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const isToday =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow =
    d.getDate() === tomorrow.getDate() &&
    d.getMonth() === tomorrow.getMonth() &&
    d.getFullYear() === tomorrow.getFullYear();

  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (isToday) return `Today at ${time}`;
  if (isTomorrow) return `Tomorrow at ${time}`;
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} at ${time}`;
}

export default function EventsScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('invited');
  const uid = getUid();

  const { data: invitedData, isLoading: invitedLoading, isRefetching: invitedRefetching } = useQuery({
    queryKey: ['eventsInvited'],
    queryFn: async () => (await getInvitedEvents()).items,
  });

  const { data: myData, isLoading: myLoading, isRefetching: myRefetching } = useQuery({
    queryKey: ['eventsOwn'],
    queryFn: async () => (await getMyEvents()).items,
  });

  const events = tab === 'invited' ? (invitedData ?? []) : (myData ?? []);
  const isLoading = tab === 'invited' ? invitedLoading : myLoading;
  const isRefetching = tab === 'invited' ? invitedRefetching : myRefetching;

  const onRefresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: tab === 'invited' ? ['eventsInvited'] : ['eventsOwn'] });
  }, [queryClient, tab]);

  const getMyRsvp = (event: EventItem): string | null => {
    if (!uid) return null;
    const inv = event.invitees.find((i) => i.uid === uid);
    return inv?.status ?? null;
  };

  const rsvpColor = (status: string | null) => {
    if (status === 'accepted') return colors.success;
    if (status === 'declined') return colors.destructive;
    return colors.brandRed;
  };

  const rsvpLabel = (status: string | null) => {
    if (status === 'accepted') return 'Accepted';
    if (status === 'declined') return 'Declined';
    return 'Pending';
  };

  const renderEvent = useCallback(
    ({ item }: { item: EventItem }) => {
      const myStatus = getMyRsvp(item);
      const isOwner = item.authorUid === uid;
      const acceptedCount = item.invitees.filter((i) => i.status === 'accepted').length;

      return (
        <Pressable
          style={styles.card}
          onPress={() => router.push({ pathname: '/event/[id]', params: { id: item.id } } as any)}
        >
          <View style={styles.cardHeader}>
            <View style={styles.dateChip}>
              <Text style={styles.dateChipMonth}>
                {new Date(item.startTime).toLocaleDateString([], { month: 'short' }).toUpperCase()}
              </Text>
              <Text style={styles.dateChipDay}>
                {new Date(item.startTime).getDate()}
              </Text>
            </View>
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitle} numberOfLines={1}>{item.title}</Text>
              <Text style={styles.cardTime}>{formatEventTime(item.startTime)}</Text>
              {item.location && (
                <View style={styles.locationRow}>
                  <Ionicons name="location-outline" size={12} color={colors.mutedForeground} />
                  <Text style={styles.locationText} numberOfLines={1}>{item.location}</Text>
                </View>
              )}
            </View>
          </View>

          <View style={styles.cardFooter}>
            <View style={styles.attendeesRow}>
              <Ionicons name="people-outline" size={14} color={colors.mutedForeground} />
              <Text style={styles.attendeesText}>
                {acceptedCount} going · {item.invitees.length} invited
              </Text>
            </View>
            {!isOwner && myStatus && (
              <View style={[styles.statusBadge, { backgroundColor: rsvpColor(myStatus) + '18' }]}>
                <View style={[styles.statusDot, { backgroundColor: rsvpColor(myStatus) }]} />
                <Text style={[styles.statusText, { color: rsvpColor(myStatus) }]}>{rsvpLabel(myStatus)}</Text>
              </View>
            )}
            {isOwner && (
              <View style={[styles.statusBadge, { backgroundColor: colors.primary + '12' }]}>
                <Text style={[styles.statusText, { color: colors.primary }]}>Organizer</Text>
              </View>
            )}
          </View>
        </Pressable>
      );
    },
    [uid, router],
  );

  return (
    <GradientScreen transparent>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Events</Text>
        <Pressable
          style={styles.addButton}
          onPress={() => router.push('/create-event' as any)}
        >
          <Ionicons name="add" size={24} color={colors.primaryForeground} />
        </Pressable>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        <Pressable
          style={[styles.tab, tab === 'invited' && styles.activeTab]}
          onPress={() => setTab('invited')}
        >
          <Text style={[styles.tabText, tab === 'invited' && styles.activeTabText]}>Invited</Text>
        </Pressable>
        <Pressable
          style={[styles.tab, tab === 'mine' && styles.activeTab]}
          onPress={() => setTab('mine')}
        >
          <Text style={[styles.tabText, tab === 'mine' && styles.activeTabText]}>My Events</Text>
        </Pressable>
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={events}
          keyExtractor={(e) => e.id}
          renderItem={renderEvent}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={onRefresh} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Ionicons
                name={tab === 'invited' ? 'mail-open-outline' : 'calendar-outline'}
                size={48}
                color={colors.mutedForeground}
              />
              <Text muted style={styles.emptyTitle}>
                {tab === 'invited' ? 'No invites yet' : 'No events created'}
              </Text>
              <Text muted style={styles.emptySubtitle}>
                {tab === 'invited'
                  ? 'When someone invites you to a workout, it will show up here'
                  : 'Tap + to create your first workout event'}
              </Text>
            </View>
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
    paddingBottom: spacing.sm,
  },
  headerTitle: {
    fontSize: fontSizes.xl,
    ...fonts.bold,
    color: colors.foreground,
  },
  addButton: {
    width: 36,
    height: 36,
    borderRadius: radii.full,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  tabs: {
    flexDirection: 'row',
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    backgroundColor: 'rgba(255,255,255,0.5)',
    borderRadius: radii.full,
    padding: 3,
  },
  tab: {
    flex: 1,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    borderRadius: radii.full,
  },
  activeTab: {
    backgroundColor: '#fff',
  },
  tabText: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.mutedForeground,
  },
  activeTabText: {
    color: colors.foreground,
    ...fonts.semibold,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  list: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xl,
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  cardHeader: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  dateChip: {
    width: 48,
    height: 48,
    borderRadius: radii.md,
    backgroundColor: colors.brandRed + '14',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dateChipMonth: {
    fontSize: 10,
    ...fonts.bold,
    color: colors.brandRed,
    letterSpacing: 0.5,
  },
  dateChipDay: {
    fontSize: fontSizes.lg,
    ...fonts.bold,
    color: colors.brandRed,
    marginTop: -2,
  },
  cardInfo: {
    flex: 1,
    gap: 2,
  },
  cardTitle: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  cardTime: {
    fontSize: fontSizes.xs,
    ...fonts.medium,
    color: colors.mutedForeground,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  locationText: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  attendeesRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  attendeesText: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radii.full,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusText: {
    fontSize: fontSizes.xs,
    ...fonts.medium,
  },
  emptyState: {
    alignItems: 'center',
    paddingTop: spacing['2xl'],
    gap: spacing.sm,
  },
  emptyTitle: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
  },
  emptySubtitle: {
    fontSize: fontSizes.sm,
    textAlign: 'center',
    paddingHorizontal: spacing.xl,
  },
});
