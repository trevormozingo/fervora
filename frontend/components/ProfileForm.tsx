import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import DateTimePicker from '@react-native-community/datetimepicker';
import { Text as RNText } from 'react-native';
import { Button, Input, Text, colors, fonts, fontSizes, spacing, radii } from '@/components/ui';
import { LocationPicker } from '@/components/LocationPicker';
import { INTEREST_OPTIONS, FITNESS_LEVEL_OPTIONS } from '@/models/profile';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ProfileFormData = {
  username?: string;
  displayName: string;
  bio: string;
  birthday: string;
  photoUri: string | null;
  locationCoords: [number, number] | null;
  locationLabel: string | null;
  interests: string[];
  fitnessLevel: string | null;
};

type Props = {
  /** Initial form values (for edit mode) */
  initial?: Partial<ProfileFormData>;
  /** URL of existing photo (edit mode) */
  existingPhotoUrl?: string | null;
  /** Show username field (create mode only) */
  showUsername?: boolean;
  /** Require photo, birthday (create mode) */
  requirePhoto?: boolean;
  requireBirthday?: boolean;
  /** Submit button label */
  submitLabel: string;
  /** Loading state from parent */
  submitting?: boolean;
  /** Called with form data on submit */
  onSubmit: (data: ProfileFormData) => Promise<void> | void;
};

// ── Component ─────────────────────────────────────────────────────────────────

const PHOTO_SIZE = 110;

export function ProfileForm({
  initial,
  existingPhotoUrl,
  showUsername = false,
  requirePhoto = false,
  requireBirthday = false,
  submitLabel,
  submitting = false,
  onSubmit,
}: Props) {
  const [username, setUsername] = useState(initial?.username ?? '');
  const [displayName, setDisplayName] = useState(initial?.displayName ?? '');
  const [bio, setBio] = useState(initial?.bio ?? '');
  const [birthday, setBirthday] = useState(initial?.birthday ?? '');
  const [photoUri, setPhotoUri] = useState<string | null>(initial?.photoUri ?? null);
  const [locationCoords, setLocationCoords] = useState<[number, number] | null>(initial?.locationCoords ?? null);
  const [locationLabel, setLocationLabel] = useState<string | null>(initial?.locationLabel ?? null);
  const [interests, setInterests] = useState<string[]>(initial?.interests ?? []);
  const [fitnessLevel, setFitnessLevel] = useState<string | null>(initial?.fitnessLevel ?? null);

  const [locatingUser, setLocatingUser] = useState(false);
  const [mapPickerVisible, setMapPickerVisible] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [tempDate, setTempDate] = useState<Date | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const displayPhoto = photoUri ?? existingPhotoUrl ?? null;

  // ── Validation ────────────────────────────────────────────────────────────

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (showUsername && username.trim().length < 3) errs.username = 'Username must be at least 3 characters';
    if (showUsername && !/^[a-zA-Z0-9_-]+$/.test(username)) errs.username = 'Letters, numbers, underscores, hyphens only';
    if (!displayName.trim()) errs.displayName = 'Display name is required';
    if (requirePhoto && !displayPhoto) errs.photo = 'Profile photo is required';
    if (requireBirthday && !birthday) errs.birthday = 'Birthday is required';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  // ── Handlers ──────────────────────────────────────────────────────────────

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });
    if (!result.canceled && result.assets[0]) {
      setPhotoUri(result.assets[0].uri);
      setErrors((prev) => { const n = { ...prev }; delete n.photo; return n; });
    }
  };

  const setMyLocation = async () => {
    try {
      setLocatingUser(true);
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Enable location permissions in Settings to use this feature.');
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const coords: [number, number] = [pos.coords.longitude, pos.coords.latitude];
      setLocationCoords(coords);
      const [geo] = await Location.reverseGeocodeAsync({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
      setLocationLabel(geo ? [geo.city, geo.region].filter(Boolean).join(', ') : null);
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not get location');
    } finally {
      setLocatingUser(false);
    }
  };

  const toggleInterest = (interest: string) => {
    setInterests((prev) =>
      prev.includes(interest) ? prev.filter((i) => i !== interest) : [...prev, interest]
    );
  };

  const openDatePicker = () => {
    const dateValue = birthday
      ? (() => { const [y, m, d] = birthday.split('-').map(Number); return new Date(y, m - 1, d); })()
      : new Date(2000, 0, 1);
    setTempDate(dateValue);
    setShowDatePicker(true);
  };

  const handleDateChange = (_event: any, selected?: Date) => {
    if (Platform.OS === 'android') {
      setShowDatePicker(false);
      if (selected) {
        const iso = `${selected.getFullYear()}-${String(selected.getMonth() + 1).padStart(2, '0')}-${String(selected.getDate()).padStart(2, '0')}`;
        setBirthday(iso);
        setErrors((prev) => { const n = { ...prev }; delete n.birthday; return n; });
      }
    } else if (selected) {
      setTempDate(selected);
    }
  };

  const handleDateDone = () => {
    if (tempDate) {
      const iso = `${tempDate.getFullYear()}-${String(tempDate.getMonth() + 1).padStart(2, '0')}-${String(tempDate.getDate()).padStart(2, '0')}`;
      setBirthday(iso);
      setErrors((prev) => { const n = { ...prev }; delete n.birthday; return n; });
    }
    setShowDatePicker(false);
  };

  const formatBirthday = (iso: string) => {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    await onSubmit({
      username: showUsername ? username : undefined,
      displayName,
      bio,
      birthday,
      photoUri,
      locationCoords,
      locationLabel,
      interests,
      fitnessLevel,
    });
  };

  const dateValue = birthday
    ? (() => { const [y, m, d] = birthday.split('-').map(Number); return new Date(y, m - 1, d); })()
    : new Date(2000, 0, 1);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <ScrollView
        contentContainerStyle={s.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* ── Photo ── */}
        <View style={s.photoSection}>
          <Pressable onPress={pickImage} style={s.photoPressable}>
            <View style={s.photoWrapper}>
              {displayPhoto ? (
                <Image source={{ uri: displayPhoto }} style={s.photoImage} />
              ) : (
                <View style={s.photoPlaceholder}>
                  <Ionicons name="person" size={44} color={colors.mutedForeground} />
                </View>
              )}
            </View>
            <View style={s.cameraOverlay}>
              <Ionicons name="camera" size={14} color="#fff" />
            </View>
          </Pressable>
          <Text muted style={s.photoHint}>Tap to {displayPhoto ? 'change' : 'add'} photo</Text>
          {errors.photo && <RNText style={s.errorText}>{errors.photo}</RNText>}
        </View>

        {/* ── Basic Info Card ── */}
        <View style={s.sectionCard}>
          <View style={s.sectionHeaderRow}>
            <Ionicons name="person-outline" size={18} color={colors.foreground} />
            <RNText style={s.sectionTitle}>Basic Info</RNText>
          </View>

          {showUsername && (
            <Input
              label="Username"
              placeholder="Enter username"
              value={username}
              onChangeText={(t) => { setUsername(t); setErrors((p) => { const n = { ...p }; delete n.username; return n; }); }}
              error={errors.username}
              autoCapitalize="none"
              autoCorrect={false}
              maxLength={30}
            />
          )}

          <Input
            label="Display Name"
            placeholder="Enter your name"
            value={displayName}
            onChangeText={(t) => { setDisplayName(t); setErrors((p) => { const n = { ...p }; delete n.displayName; return n; }); }}
            error={errors.displayName}
            maxLength={100}
          />

          <Input
            label="Bio"
            placeholder="Tell us about yourself"
            value={bio}
            onChangeText={setBio}
            multiline
            maxLength={500}
            style={s.bioInput}
          />
        </View>

        {/* ── Details Card ── */}
        <View style={s.sectionCard}>
          <View style={s.sectionHeaderRow}>
            <Ionicons name="information-circle-outline" size={18} color={colors.foreground} />
            <RNText style={s.sectionTitle}>Details</RNText>
          </View>

          {/* ── Birthday ── */}
          <View style={s.fieldGroup}>
            <RNText style={s.label}>Birthday</RNText>
            <Pressable onPress={openDatePicker} style={s.pickerTrigger}>
              <Ionicons name="calendar-outline" size={18} color={birthday ? colors.foreground : colors.placeholder} />
              <RNText style={birthday ? s.pickerText : s.pickerPlaceholder}>
                {birthday ? formatBirthday(birthday) : 'Select your birthday'}
              </RNText>
              <Ionicons name="chevron-down" size={16} color={colors.placeholder} />
            </Pressable>
            {errors.birthday && <RNText style={s.errorText}>{errors.birthday}</RNText>}
          </View>

          {/* ── Location ── */}
          <View style={s.fieldGroup}>
            <RNText style={s.label}>Location</RNText>
            <View style={s.locationRow}>
              {locationLabel ? (
                <View style={s.locationDisplay}>
                  <Ionicons name="location" size={16} color={colors.brandRed} />
                  <Text style={s.locationText}>{locationLabel}</Text>
                </View>
              ) : (
                <Text muted style={s.locationText}>Not set</Text>
              )}
              <View style={s.locationButtons}>
                <Pressable onPress={setMyLocation} style={s.locationButton} disabled={locatingUser}>
                  {locatingUser ? (
                    <ActivityIndicator size="small" color={colors.primaryForeground} />
                  ) : (
                    <RNText style={s.locationButtonText}>{locationLabel ? 'Update' : 'Use GPS'}</RNText>
                  )}
                </Pressable>
                <Pressable onPress={() => setMapPickerVisible(true)} style={[s.locationButton, s.mapButton]}>
                  <Ionicons name="map-outline" size={14} color={colors.primaryForeground} />
                  <RNText style={s.locationButtonText}>Map</RNText>
                </Pressable>
              </View>
            </View>
          </View>
        </View>

        {/* ── Fitness & Interests Card ── */}
        <View style={s.sectionCard}>
          <View style={s.sectionHeaderRow}>
            <Ionicons name="fitness-outline" size={18} color={colors.foreground} />
            <RNText style={s.sectionTitle}>Fitness & Interests</RNText>
          </View>

          {/* ── Fitness Level ── */}
          <View style={s.fieldGroup}>
            <RNText style={s.label}>Fitness Level</RNText>
            <View style={s.levelRow}>
              {FITNESS_LEVEL_OPTIONS.map((level) => {
                const active = fitnessLevel === level;
                return (
                  <Pressable
                    key={level}
                    onPress={() => setFitnessLevel(active ? null : level)}
                    style={[s.levelChip, active && s.levelChipActive]}
                  >
                    <RNText style={[s.levelChipText, active && s.levelChipTextActive]}>
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </RNText>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {/* ── Interests ── */}
          <View style={s.fieldGroup}>
            <RNText style={s.label}>Interests</RNText>
            <View style={s.tagsContainer}>
              {INTEREST_OPTIONS.map((interest) => {
                const active = interests.includes(interest);
                return (
                  <Pressable
                    key={interest}
                    onPress={() => toggleInterest(interest)}
                    style={[s.tag, active && s.tagActive]}
                  >
                    <RNText style={[s.tagText, active && s.tagTextActive]}>{interest}</RNText>
                  </Pressable>
                );
              })}
            </View>
          </View>
        </View>

        {/* ── Submit ── */}
        <Button
          label={submitLabel}
          onPress={handleSubmit}
          loading={submitting}
          style={s.submitButton}
        />
      </ScrollView>

      {/* ── Date Picker Modal (iOS) ── */}
      <Modal visible={showDatePicker} transparent animationType="slide">
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <View style={s.modalHeader}>
              <Pressable onPress={() => setShowDatePicker(false)}>
                <RNText style={s.modalCancel}>Cancel</RNText>
              </Pressable>
              <RNText style={s.modalTitle}>Birthday</RNText>
              <Pressable onPress={handleDateDone}>
                <RNText style={s.modalDone}>Done</RNText>
              </Pressable>
            </View>
            <DateTimePicker
              value={tempDate ?? dateValue}
              mode="date"
              display="spinner"
              maximumDate={new Date()}
              onChange={handleDateChange}
              themeVariant="light"
              style={s.datePicker}
            />
          </View>
        </View>
      </Modal>

      {/* ── Map Location Picker ── */}
      <LocationPicker
        visible={mapPickerVisible}
        onClose={() => setMapPickerVisible(false)}
        initialCoords={locationCoords}
        onSelect={(loc) => {
          setLocationCoords(loc.coordinates);
          setLocationLabel(loc.label);
          setMapPickerVisible(false);
        }}
      />
    </>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  scroll: {
    paddingBottom: 100,
  },

  // ── Photo ──
  photoSection: { alignItems: 'center', marginBottom: spacing.lg },
  photoPressable: { width: PHOTO_SIZE, height: PHOTO_SIZE, position: 'relative' },
  photoWrapper: {
    width: PHOTO_SIZE, height: PHOTO_SIZE, borderRadius: PHOTO_SIZE / 2, overflow: 'hidden',
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.15, shadowRadius: 8,
  },
  photoImage: { width: PHOTO_SIZE, height: PHOTO_SIZE },
  photoPlaceholder: {
    width: PHOTO_SIZE, height: PHOTO_SIZE, borderRadius: PHOTO_SIZE / 2,
    backgroundColor: 'rgba(255,255,255,0.7)', justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: 'rgba(255,255,255,0.5)',
  },
  cameraOverlay: {
    position: 'absolute', bottom: 2, right: 2, backgroundColor: colors.primary,
    width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center',
    borderWidth: 2.5, borderColor: colors.background,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.2, shadowRadius: 4,
  },
  photoHint: { marginTop: spacing.sm, fontSize: fontSizes.xs },

  // ── Section Cards ──
  sectionCard: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: spacing.md,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  sectionTitle: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },

  // ── Fields ──
  fieldGroup: { gap: spacing.xs },
  label: { fontSize: fontSizes.sm, ...fonts.medium, color: colors.foreground },
  bioInput: { height: 100, textAlignVertical: 'top', paddingTop: spacing.sm },
  errorText: { fontSize: fontSizes.xs, color: colors.destructive, marginTop: 2 },

  // ── Date picker trigger ──
  pickerTrigger: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    backgroundColor: colors.muted,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  pickerText: { flex: 1, fontSize: fontSizes.base, color: colors.foreground },
  pickerPlaceholder: { flex: 1, fontSize: fontSizes.base, color: colors.placeholder },

  // ── Location ──
  locationRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  locationDisplay: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flex: 1 },
  locationText: { fontSize: fontSizes.sm },
  locationButtons: { flexDirection: 'row', gap: spacing.xs },
  locationButton: {
    backgroundColor: colors.primary, paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm, borderRadius: radii.md, minWidth: 80, alignItems: 'center',
  },
  mapButton: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  locationButtonText: { color: colors.primaryForeground, ...fonts.semibold, fontSize: fontSizes.sm },

  // ── Fitness level chips ──
  levelRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  levelChip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radii.full, borderWidth: 1.5, borderColor: colors.border,
    backgroundColor: 'rgba(255,255,255,0.5)',
  },
  levelChipActive: {
    backgroundColor: colors.primary, borderColor: colors.primary,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.15, shadowRadius: 3,
  },
  levelChipText: { fontSize: fontSizes.sm, color: colors.foreground, ...fonts.medium },
  levelChipTextActive: { color: colors.primaryForeground },

  // ── Interest tags ──
  tagsContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  tag: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radii.full, borderWidth: 1.5, borderColor: colors.border,
    backgroundColor: 'rgba(255,255,255,0.5)',
  },
  tagActive: {
    backgroundColor: colors.primary, borderColor: colors.primary,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.15, shadowRadius: 3,
  },
  tagText: { fontSize: fontSizes.sm, color: colors.foreground },
  tagTextActive: { color: colors.primaryForeground, ...fonts.semibold },

  // ── Submit ──
  submitButton: { marginTop: spacing.lg },

  // ── Date modal ──
  modalOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' },
  modalSheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radii.xl, borderTopRightRadius: radii.xl,
    paddingBottom: 34,
  },
  modalHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  modalTitle: { fontSize: fontSizes.base, ...fonts.semibold, color: colors.foreground },
  modalCancel: { fontSize: fontSizes.base, color: colors.mutedForeground },
  modalDone: { fontSize: fontSizes.base, ...fonts.semibold, color: colors.primary },
  datePicker: { height: 216 },
});
