import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import * as Calendar from 'expo-calendar';
import { GradientScreen, Text, Button, colors, fonts, fontSizes, spacing, radii } from '@/components/ui';
import { getEvent, rsvpEvent, deleteEvent } from '@/services/events';
import { sendPushToUsers } from '@/services/notifications';
import { getUid } from '@/services/auth';
import { apiFetch } from '@/services/api';
import type { EventItem, Invitee } from '@/models/event';

type ProfileSnippet = { id: string; username: string; displayName: string; profilePhoto?: string | null };

function formatFullDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export default function EventDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const uid = getUid();
  const [rsvpLoading, setRsvpLoading] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [calendarAdded, setCalendarAdded] = useState(false);

  const { data: event, isLoading, isRefetching } = useQuery({
    queryKey: ['event', id],
    queryFn: () => getEvent(id!),
    enabled: !!id,
  });

  // Fetch profiles for author + invitees
  const allUids = event ? [event.authorUid, ...event.invitees.map((i) => i.uid)] : [];
  const { data: profiles } = useQuery({
    queryKey: ['eventProfiles', id],
    queryFn: async () => {
      const unique = [...new Set(allUids)];
      const results: ProfileSnippet[] = [];
      for (const u of unique) {
        try {
          const p = await apiFetch<ProfileSnippet>(`/profile/uid/${u}`);
          results.push(p);
        } catch { /* skip */ }
      }
      return results;
    },
    enabled: allUids.length > 0,
  });

  const profileMap = new Map((profiles ?? []).map((p) => [p.id, p]));

  const onRefresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['event', id] });
    queryClient.invalidateQueries({ queryKey: ['eventProfiles', id] });
  }, [queryClient, id]);

  const handleRsvp = async (status: 'accepted' | 'declined') => {
    if (!id) return;
    setRsvpLoading(status);
    try {
      const updated = await rsvpEvent(id, status);
      queryClient.setQueryData(['event', id], updated);
      queryClient.invalidateQueries({ queryKey: ['eventsInvited'] });

      // notify the organizer
      if (event) {
        const myProfile = profileMap.get(uid ?? '');
        const name = myProfile?.displayName ?? 'Someone';
        sendPushToUsers(
          [event.authorUid],
          `RSVP: ${name} ${status}`,
          `${name} ${status} your event "${event.title}"`,
          { type: 'event_rsvp', eventId: id },
        );
      }
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not update RSVP');
    } finally {
      setRsvpLoading(null);
    }
  };

  const handleDelete = () => {
    Alert.alert('Delete Event', 'Are you sure? This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          setDeleteLoading(true);
          try {
            await deleteEvent(id!);
            queryClient.invalidateQueries({ queryKey: ['eventsOwn'] });
            queryClient.invalidateQueries({ queryKey: ['eventsInvited'] });
            router.back();
          } catch (err: any) {
            Alert.alert('Error', err.message ?? 'Could not delete event');
          } finally {
            setDeleteLoading(false);
          }
        },
      },
    ]);
  };

  const handleAddToCalendar = async () => {
    if (!event) return;
    try {
      const { status } = await Calendar.requestCalendarPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Calendar access is needed to add this event.');
        return;
      }
      const calendars = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
      const defaultCal = calendars.find(
        (c) => c.allowsModifications && c.source?.name === 'iCloud',
      ) ?? calendars.find((c) => c.allowsModifications);
      if (!defaultCal) {
        Alert.alert('No Calendar', 'No writable calendar found on this device.');
        return;
      }
      await Calendar.createEventAsync(defaultCal.id, {
        title: event.title,
        startDate: new Date(event.startTime),
        endDate: event.endTime ? new Date(event.endTime) : new Date(new Date(event.startTime).getTime() + 3600000),
        location: event.location ?? undefined,
        notes: event.description ?? undefined,
      });
      setCalendarAdded(true);
      Alert.alert('Added', 'Event added to your calendar.');
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not add to calendar');
    }
  };

  const isOwner = event?.authorUid === uid;
  const myInvite = event?.invitees.find((i) => i.uid === uid);

  if (isLoading) {
    return (
      <GradientScreen transparent>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </GradientScreen>
    );
  }

  if (!event) {
    return (
      <GradientScreen transparent>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12}>
            <Ionicons name="chevron-back" size={28} color={colors.foreground} />
          </Pressable>
          <Text style={styles.headerTitle}>Event</Text>
          <View style={{ width: 28 }} />
        </View>
        <View style={styles.center}>
          <Text muted>Event not found</Text>
        </View>
      </GradientScreen>
    );
  }

  const organizer = profileMap.get(event.authorUid);
  const acceptedInvitees = event.invitees.filter((i) => i.status === 'accepted');
  const pendingInvitees = event.invitees.filter((i) => i.status === 'pending');
  const declinedInvitees = event.invitees.filter((i) => i.status === 'declined');

  const renderInvitee = (inv: Invitee) => {
    const profile = profileMap.get(inv.uid);
    const statusColor =
      inv.status === 'accepted' ? colors.success :
      inv.status === 'declined' ? colors.destructive :
      colors.mutedForeground;
    return (
      <View key={inv.uid} style={styles.inviteeRow}>
        {profile?.profilePhoto ? (
          <Image source={{ uri: profile.profilePhoto }} style={styles.inviteeAvatar} />
        ) : (
          <View style={styles.inviteeAvatarFallback}>
            <Text style={styles.inviteeAvatarText}>
              {(profile?.displayName ?? '?').charAt(0).toUpperCase()}
            </Text>
          </View>
        )}
        <View style={styles.inviteeInfo}>
          <Text style={styles.inviteeName}>{profile?.displayName ?? inv.uid}</Text>
          {profile?.username && <Text style={styles.inviteeUsername}>@{profile.username}</Text>}
        </View>
        <View style={[styles.inviteeStatus, { backgroundColor: statusColor + '18' }]}>
          <Text style={[styles.inviteeStatusText, { color: statusColor }]}>
            {inv.status.charAt(0).toUpperCase() + inv.status.slice(1)}
          </Text>
        </View>
      </View>
    );
  };

  return (
    <GradientScreen transparent>
      {/* Header */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={28} color={colors.foreground} />
        </Pressable>
        <Text style={styles.headerTitle}>Event</Text>
        {isOwner ? (
          <Pressable onPress={handleDelete} hitSlop={12} disabled={deleteLoading}>
            {deleteLoading ? (
              <ActivityIndicator size="small" color={colors.destructive} />
            ) : (
              <Ionicons name="trash-outline" size={22} color={colors.destructive} />
            )}
          </Pressable>
        ) : (
          <View style={{ width: 28 }} />
        )}
      </View>

      <FlatList
        data={[]}
        renderItem={null}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={onRefresh} tintColor={colors.primary} />
        }
        ListHeaderComponent={
          <View style={styles.content}>
            {/* Title & Date */}
            <View style={styles.heroCard}>
              <Text style={styles.eventTitle}>{event.title}</Text>

              <View style={styles.detailRow}>
                <Ionicons name="calendar-outline" size={18} color={colors.brandRed} />
                <View>
                  <Text style={styles.detailPrimary}>{formatFullDate(event.startTime)}</Text>
                  <Text style={styles.detailSecondary}>
                    {formatTime(event.startTime)}
                    {event.endTime ? ` – ${formatTime(event.endTime)}` : ''}
                  </Text>
                </View>
              </View>

              {event.location && (
                <View style={styles.detailRow}>
                  <Ionicons name="location-outline" size={18} color={colors.brandRed} />
                  <Text style={styles.detailPrimary}>{event.location}</Text>
                </View>
              )}

              {event.description && (
                <View style={styles.descriptionSection}>
                  <Text style={styles.description}>{event.description}</Text>
                </View>
              )}

              {/* Organizer */}
              <View style={styles.organizerRow}>
                <Text style={styles.sectionLabel}>Organized by</Text>
                <Text style={styles.organizerName}>
                  {organizer?.displayName ?? 'Unknown'}
                </Text>
              </View>

              {/* Add to Calendar */}
              <Pressable
                style={styles.calendarButton}
                onPress={handleAddToCalendar}
                disabled={calendarAdded}
              >
                <Ionicons
                  name={calendarAdded ? 'checkmark-circle' : 'calendar'}
                  size={18}
                  color={calendarAdded ? colors.success : colors.brandRed}
                />
                <Text style={[styles.calendarButtonText, calendarAdded && { color: colors.success }]}>
                  {calendarAdded ? 'Added to Calendar' : 'Add to Calendar'}
                </Text>
              </Pressable>
            </View>

            {/* RSVP buttons */}
            {myInvite && !isOwner && (
              <View style={styles.rsvpSection}>
                <Text style={styles.sectionTitle}>Your RSVP</Text>
                <View style={styles.rsvpButtons}>
                  <Pressable
                    style={[
                      styles.rsvpButton,
                      myInvite.status === 'accepted' && styles.rsvpAccepted,
                    ]}
                    onPress={() => handleRsvp('accepted')}
                    disabled={rsvpLoading !== null}
                  >
                    {rsvpLoading === 'accepted' ? (
                      <ActivityIndicator size="small" color={colors.success} />
                    ) : (
                      <>
                        <Ionicons
                          name={myInvite.status === 'accepted' ? 'checkmark-circle' : 'checkmark-circle-outline'}
                          size={20}
                          color={colors.success}
                        />
                        <Text style={[styles.rsvpButtonText, { color: colors.success }]}>Accept</Text>
                      </>
                    )}
                  </Pressable>
                  <Pressable
                    style={[
                      styles.rsvpButton,
                      myInvite.status === 'declined' && styles.rsvpDeclined,
                    ]}
                    onPress={() => handleRsvp('declined')}
                    disabled={rsvpLoading !== null}
                  >
                    {rsvpLoading === 'declined' ? (
                      <ActivityIndicator size="small" color={colors.destructive} />
                    ) : (
                      <>
                        <Ionicons
                          name={myInvite.status === 'declined' ? 'close-circle' : 'close-circle-outline'}
                          size={20}
                          color={colors.destructive}
                        />
                        <Text style={[styles.rsvpButtonText, { color: colors.destructive }]}>Decline</Text>
                      </>
                    )}
                  </Pressable>
                </View>
              </View>
            )}

            {/* Invitees */}
            {event.invitees.length > 0 && (
              <View style={styles.inviteesSection}>
                <Text style={styles.sectionTitle}>
                  Invitees ({event.invitees.length})
                </Text>
                {acceptedInvitees.length > 0 && (
                  <View style={styles.inviteeGroup}>
                    <Text style={styles.groupLabel}>Going ({acceptedInvitees.length})</Text>
                    {acceptedInvitees.map(renderInvitee)}
                  </View>
                )}
                {pendingInvitees.length > 0 && (
                  <View style={styles.inviteeGroup}>
                    <Text style={styles.groupLabel}>Pending ({pendingInvitees.length})</Text>
                    {pendingInvitees.map(renderInvitee)}
                  </View>
                )}
                {declinedInvitees.length > 0 && (
                  <View style={styles.inviteeGroup}>
                    <Text style={styles.groupLabel}>Declined ({declinedInvitees.length})</Text>
                    {declinedInvitees.map(renderInvitee)}
                  </View>
                )}
              </View>
            )}
          </View>
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
    gap: spacing.md,
  },
  heroCard: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  eventTitle: {
    fontSize: fontSizes['2xl'],
    ...fonts.bold,
    color: colors.foreground,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  detailPrimary: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.foreground,
  },
  detailSecondary: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
  descriptionSection: {
    paddingTop: spacing.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  description: {
    fontSize: fontSizes.sm,
    color: colors.foreground,
    lineHeight: 20,
  },
  organizerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: spacing.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  sectionLabel: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
    ...fonts.medium,
  },
  organizerName: {
    fontSize: fontSizes.sm,
    ...fonts.semibold,
    color: colors.foreground,
  },
  calendarButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.full,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.xs,
  },
  calendarButtonText: {
    fontSize: fontSizes.sm,
    ...fonts.semibold,
    color: colors.brandRed,
  },
  rsvpSection: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
  },
  sectionTitle: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  rsvpButtons: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  rsvpButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.full,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: colors.border,
  },
  rsvpAccepted: {
    backgroundColor: colors.success + '14',
    borderColor: colors.success + '40',
  },
  rsvpDeclined: {
    backgroundColor: colors.destructive + '14',
    borderColor: colors.destructive + '40',
  },
  rsvpButtonText: {
    fontSize: fontSizes.sm,
    ...fonts.semibold,
  },
  inviteesSection: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  inviteeGroup: {
    gap: spacing.xs,
  },
  groupLabel: {
    fontSize: fontSizes.xs,
    ...fonts.semibold,
    color: colors.mutedForeground,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  inviteeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  inviteeAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
  },
  inviteeAvatarFallback: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  inviteeAvatarText: {
    fontSize: fontSizes.sm,
    ...fonts.bold,
    color: colors.mutedForeground,
  },
  inviteeInfo: {
    flex: 1,
  },
  inviteeName: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.foreground,
  },
  inviteeUsername: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
  inviteeStatus: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radii.full,
  },
  inviteeStatusText: {
    fontSize: fontSizes.xs,
    ...fonts.medium,
  },
});
