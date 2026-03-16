import { useState, useCallback } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import DateTimePicker from '@react-native-community/datetimepicker';
import { GradientScreen, Text, Button, colors, fonts, fontSizes, spacing, radii } from '@/components/ui';
import { createEvent } from '@/services/events';
import { getUid } from '@/services/auth';
import { apiFetch } from '@/services/api';

type FollowUser = {
  id: string;
  username: string;
  displayName: string;
  profilePhoto?: string | null;
};

export default function CreateEventScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Form state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [startDate, setStartDate] = useState(new Date());
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [showEndTime, setShowEndTime] = useState(false);

  // Date picker state
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [showEndDatePicker, setShowEndDatePicker] = useState(false);
  const [showEndTimePicker, setShowEndTimePicker] = useState(false);

  // Invitees
  const [selectedInvitees, setSelectedInvitees] = useState<FollowUser[]>([]);
  const [inviteModalVisible, setInviteModalVisible] = useState(false);
  const [followingList, setFollowingList] = useState<FollowUser[]>([]);
  const [followingLoading, setFollowingLoading] = useState(false);

  const [loading, setLoading] = useState(false);

  const openInvitePicker = async () => {
    setInviteModalVisible(true);
    if (followingList.length > 0) return;
    setFollowingLoading(true);
    try {
      const data = await apiFetch<{ following: FollowUser[] }>('/follows/following');
      setFollowingList(data.following ?? []);
    } catch {
      Alert.alert('Error', 'Could not load your following list');
    } finally {
      setFollowingLoading(false);
    }
  };

  const toggleInvitee = (user: FollowUser) => {
    setSelectedInvitees((prev) => {
      const exists = prev.find((u) => u.id === user.id);
      if (exists) return prev.filter((u) => u.id !== user.id);
      if (prev.length >= 50) {
        Alert.alert('Limit', 'Maximum 50 invitees');
        return prev;
      }
      return [...prev, user];
    });
  };

  const removeInvitee = (uid: string) => {
    setSelectedInvitees((prev) => prev.filter((u) => u.id !== uid));
  };

  const formatDate = (d: Date) =>
    d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });

  const formatTime = (d: Date) =>
    d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

  const handleSubmit = async () => {
    if (!title.trim()) {
      Alert.alert('Required', 'Please enter a title for your event');
      return;
    }

    setLoading(true);
    try {
      const payload: Record<string, unknown> = {
        title: title.trim(),
        startTime: startDate.toISOString(),
      };
      if (description.trim()) payload.description = description.trim();
      if (location.trim()) payload.location = location.trim();
      if (showEndTime && endDate) payload.endTime = endDate.toISOString();
      if (selectedInvitees.length > 0) {
        payload.inviteeUids = selectedInvitees.map((u) => u.id);
      }

      await createEvent(payload as any);

      queryClient.invalidateQueries({ queryKey: ['eventsOwn'] });
      queryClient.invalidateQueries({ queryKey: ['eventsInvited'] });

      router.back();
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not create event');
    } finally {
      setLoading(false);
    }
  };

  const hasContent = title.trim().length > 0;

  return (
    <GradientScreen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        {/* Header */}
        <View style={styles.headerBar}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerClose}>
            <Ionicons name="close" size={26} color={colors.foreground} />
          </Pressable>
          <Text variant="title" style={styles.headerTitle}>New Event</Text>
          <Pressable
            onPress={handleSubmit}
            disabled={!hasContent || loading}
            style={[styles.postButton, (!hasContent || loading) && styles.postButtonDisabled]}
          >
            {loading ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.postButtonText}>Create</Text>
            )}
          </Pressable>
        </View>

        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {/* Title */}
          <View style={styles.section}>
            <Text style={styles.label}>Title *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. Morning Chest & Tris"
              placeholderTextColor={colors.placeholder}
              value={title}
              onChangeText={setTitle}
              maxLength={200}
            />
          </View>

          {/* Description */}
          <View style={styles.section}>
            <Text style={styles.label}>Description</Text>
            <TextInput
              style={[styles.input, styles.inputMultiline]}
              placeholder="What's the plan?"
              placeholderTextColor={colors.placeholder}
              value={description}
              onChangeText={setDescription}
              multiline
              maxLength={2000}
            />
          </View>

          {/* Location */}
          <View style={styles.section}>
            <Text style={styles.label}>Location</Text>
            <TextInput
              style={styles.input}
              placeholder="Gym name, address, etc."
              placeholderTextColor={colors.placeholder}
              value={location}
              onChangeText={setLocation}
              maxLength={500}
            />
          </View>

          {/* Start Date & Time */}
          <View style={styles.section}>
            <Text style={styles.label}>Start</Text>
            <View style={styles.dateTimeRow}>
              <Pressable style={styles.datePicker} onPress={() => setShowDatePicker(true)}>
                <Ionicons name="calendar-outline" size={16} color={colors.brandRed} />
                <Text style={styles.datePickerText}>{formatDate(startDate)}</Text>
              </Pressable>
              <Pressable style={styles.datePicker} onPress={() => setShowTimePicker(true)}>
                <Ionicons name="time-outline" size={16} color={colors.brandRed} />
                <Text style={styles.datePickerText}>{formatTime(startDate)}</Text>
              </Pressable>
            </View>
          </View>

          {/* End Time (optional) */}
          {!showEndTime ? (
            <Pressable style={styles.addEndTime} onPress={() => {
              const end = new Date(startDate);
              end.setHours(end.getHours() + 1);
              setEndDate(end);
              setShowEndTime(true);
            }}>
              <Ionicons name="add-circle-outline" size={18} color={colors.brandRed} />
              <Text style={styles.addEndTimeText}>Add end time</Text>
            </Pressable>
          ) : (
            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <Text style={styles.label}>End</Text>
                <Pressable onPress={() => { setShowEndTime(false); setEndDate(null); }}>
                  <Text style={styles.removeText}>Remove</Text>
                </Pressable>
              </View>
              <View style={styles.dateTimeRow}>
                <Pressable style={styles.datePicker} onPress={() => setShowEndDatePicker(true)}>
                  <Ionicons name="calendar-outline" size={16} color={colors.brandRed} />
                  <Text style={styles.datePickerText}>{endDate ? formatDate(endDate) : 'Date'}</Text>
                </Pressable>
                <Pressable style={styles.datePicker} onPress={() => setShowEndTimePicker(true)}>
                  <Ionicons name="time-outline" size={16} color={colors.brandRed} />
                  <Text style={styles.datePickerText}>{endDate ? formatTime(endDate) : 'Time'}</Text>
                </Pressable>
              </View>
            </View>
          )}

          {/* Invitees */}
          <View style={styles.section}>
            <Text style={styles.label}>Invite People</Text>

            {selectedInvitees.length > 0 && (
              <View style={styles.chipRow}>
                {selectedInvitees.map((user) => (
                  <View key={user.id} style={styles.chip}>
                    {user.profilePhoto ? (
                      <Image source={{ uri: user.profilePhoto }} style={styles.chipAvatar} />
                    ) : null}
                    <Text style={styles.chipText}>{user.displayName}</Text>
                    <Pressable onPress={() => removeInvitee(user.id)} hitSlop={6}>
                      <Ionicons name="close-circle" size={16} color={colors.mutedForeground} />
                    </Pressable>
                  </View>
                ))}
              </View>
            )}

            <Pressable style={styles.addInviteeButton} onPress={openInvitePicker}>
              <Ionicons name="person-add-outline" size={18} color={colors.brandRed} />
              <Text style={styles.addInviteeText}>
                {selectedInvitees.length > 0 ? 'Add more people' : 'Choose from following'}
              </Text>
            </Pressable>
          </View>
        </ScrollView>

        {/* Invite picker modal */}
        <Modal visible={inviteModalVisible} animationType="slide" presentationStyle="pageSheet">
          <View style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Select Invitees</Text>
              <Pressable onPress={() => setInviteModalVisible(false)}>
                <Text style={styles.modalDone}>Done ({selectedInvitees.length})</Text>
              </Pressable>
            </View>

            {followingLoading ? (
              <View style={styles.center}>
                <ActivityIndicator color={colors.primary} />
              </View>
            ) : followingList.length === 0 ? (
              <View style={styles.center}>
                <Ionicons name="people-outline" size={48} color={colors.mutedForeground} />
                <Text muted style={{ marginTop: spacing.sm }}>
                  You're not following anyone yet
                </Text>
              </View>
            ) : (
              <FlatList
                data={followingList}
                keyExtractor={(u) => u.id}
                renderItem={({ item }) => {
                  const selected = selectedInvitees.some((u) => u.id === item.id);
                  return (
                    <Pressable
                      style={[styles.userRow, selected && styles.userRowSelected]}
                      onPress={() => toggleInvitee(item)}
                    >
                      {item.profilePhoto ? (
                        <Image source={{ uri: item.profilePhoto }} style={styles.userAvatar} />
                      ) : (
                        <View style={styles.userAvatarFallback}>
                          <Text style={styles.userAvatarText}>
                            {item.displayName.charAt(0).toUpperCase()}
                          </Text>
                        </View>
                      )}
                      <View style={styles.userInfo}>
                        <Text style={styles.userName}>{item.displayName}</Text>
                        <Text style={styles.userUsername}>@{item.username}</Text>
                      </View>
                      <Ionicons
                        name={selected ? 'checkmark-circle' : 'ellipse-outline'}
                        size={24}
                        color={selected ? colors.success : colors.border}
                      />
                    </Pressable>
                  );
                }}
                contentContainerStyle={styles.modalList}
              />
            )}
          </View>
        </Modal>
      </KeyboardAvoidingView>

      {/* Date/Time picker modals */}
      {showDatePicker && (
        <Modal transparent animationType="slide">
          <View style={styles.pickerOverlay}>
            <View style={styles.pickerSheet}>
              <View style={styles.pickerHeader}>
                <Pressable onPress={() => setShowDatePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerCancel}>Cancel</Text>
                </Pressable>
                <Text style={styles.pickerHeaderTitle}>Start Date</Text>
                <Pressable onPress={() => setShowDatePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerDone}>Done</Text>
                </Pressable>
              </View>
              <DateTimePicker
                value={startDate}
                mode="date"
                display="inline"
                minimumDate={new Date()}
                onChange={(_, date) => {
                  if (date) {
                    const next = new Date(startDate);
                    next.setFullYear(date.getFullYear(), date.getMonth(), date.getDate());
                    setStartDate(next);
                  }
                }}
              />
            </View>
          </View>
        </Modal>
      )}
      {showTimePicker && (
        <Modal transparent animationType="slide">
          <View style={styles.pickerOverlay}>
            <View style={styles.pickerSheet}>
              <View style={styles.pickerHeader}>
                <Pressable onPress={() => setShowTimePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerCancel}>Cancel</Text>
                </Pressable>
                <Text style={styles.pickerHeaderTitle}>Start Time</Text>
                <Pressable onPress={() => setShowTimePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerDone}>Done</Text>
                </Pressable>
              </View>
              <DateTimePicker
                value={startDate}
                mode="time"
                display="spinner"
                minuteInterval={5}
                onChange={(_, date) => {
                  if (date) {
                    const next = new Date(startDate);
                    next.setHours(date.getHours(), date.getMinutes());
                    setStartDate(next);
                  }
                }}
              />
            </View>
          </View>
        </Modal>
      )}
      {showEndDatePicker && endDate && (
        <Modal transparent animationType="slide">
          <View style={styles.pickerOverlay}>
            <View style={styles.pickerSheet}>
              <View style={styles.pickerHeader}>
                <Pressable onPress={() => setShowEndDatePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerCancel}>Cancel</Text>
                </Pressable>
                <Text style={styles.pickerHeaderTitle}>End Date</Text>
                <Pressable onPress={() => setShowEndDatePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerDone}>Done</Text>
                </Pressable>
              </View>
              <DateTimePicker
                value={endDate}
                mode="date"
                display="inline"
                minimumDate={startDate}
                onChange={(_, date) => {
                  if (date && endDate) {
                    const next = new Date(endDate);
                    next.setFullYear(date.getFullYear(), date.getMonth(), date.getDate());
                    setEndDate(next);
                  }
                }}
              />
            </View>
          </View>
        </Modal>
      )}
      {showEndTimePicker && endDate && (
        <Modal transparent animationType="slide">
          <View style={styles.pickerOverlay}>
            <View style={styles.pickerSheet}>
              <View style={styles.pickerHeader}>
                <Pressable onPress={() => setShowEndTimePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerCancel}>Cancel</Text>
                </Pressable>
                <Text style={styles.pickerHeaderTitle}>End Time</Text>
                <Pressable onPress={() => setShowEndTimePicker(false)} hitSlop={12}>
                  <Text style={styles.pickerDone}>Done</Text>
                </Pressable>
              </View>
              <DateTimePicker
                value={endDate}
                mode="time"
                display="spinner"
                minuteInterval={5}
                onChange={(_, date) => {
                  if (date && endDate) {
                    const next = new Date(endDate);
                    next.setHours(date.getHours(), date.getMinutes());
                    setEndDate(next);
                  }
                }}
              />
            </View>
          </View>
        </Modal>
      )}
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  headerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
  },
  headerClose: {
    padding: spacing.xs,
  },
  headerTitle: {
    fontSize: fontSizes.lg,
    ...fonts.bold,
    color: colors.foreground,
  },
  postButton: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
    minWidth: 72,
    alignItems: 'center',
  },
  postButtonDisabled: {
    opacity: 0.4,
  },
  postButtonText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
  scrollContent: {
    padding: spacing.md,
    paddingBottom: spacing['2xl'],
    gap: spacing.md,
  },
  section: {
    gap: spacing.xs,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  label: {
    fontSize: fontSizes.sm,
    ...fonts.semibold,
    color: colors.foreground,
  },
  input: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    fontSize: fontSizes.base,
    color: colors.foreground,
    borderWidth: 1,
    borderColor: colors.border,
  },
  inputMultiline: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  dateTimeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  datePicker: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderWidth: 1,
    borderColor: colors.border,
  },
  datePickerText: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.foreground,
  },
  addEndTime: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.xs,
  },
  addEndTimeText: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.brandRed,
  },
  removeText: {
    fontSize: fontSizes.xs,
    color: colors.destructive,
    ...fonts.medium,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(255,255,255,0.7)',
    paddingVertical: 4,
    paddingLeft: 4,
    paddingRight: spacing.sm,
    borderRadius: radii.full,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipAvatar: {
    width: 22,
    height: 22,
    borderRadius: 11,
  },
  chipText: {
    fontSize: fontSizes.xs,
    ...fonts.medium,
    color: colors.foreground,
  },
  addInviteeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: 'dashed',
  },
  addInviteeText: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.brandRed,
  },
  // Picker modal styles
  pickerOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  pickerSheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingBottom: 34,
    alignItems: 'center',
  },
  pickerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    alignSelf: 'stretch',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  pickerHeaderTitle: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  pickerCancel: {
    fontSize: fontSizes.base,
    color: colors.mutedForeground,
  },
  pickerDone: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.primary,
  },
  // Modal styles
  modalContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  modalTitle: {
    fontSize: fontSizes.lg,
    ...fonts.bold,
    color: colors.foreground,
  },
  modalDone: {
    fontSize: fontSizes.sm,
    ...fonts.semibold,
    color: colors.brandRed,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalList: {
    padding: spacing.md,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  userRowSelected: {
    backgroundColor: colors.success + '08',
    marginHorizontal: -spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
  },
  userAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
  },
  userAvatarFallback: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.muted,
    justifyContent: 'center',
    alignItems: 'center',
  },
  userAvatarText: {
    fontSize: fontSizes.base,
    ...fonts.bold,
    color: colors.mutedForeground,
  },
  userInfo: {
    flex: 1,
  },
  userName: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.foreground,
  },
  userUsername: {
    fontSize: fontSizes.xs,
    color: colors.mutedForeground,
  },
});
