import { useState, useCallback } from 'react';
import { Alert, Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Notifications from 'expo-notifications';
import * as ImagePicker from 'expo-image-picker';
import { GradientScreen, Text, colors, spacing, radii, fonts, fontSizes } from '@/components/ui';
import { signOut, deleteFirebaseAccount, getIdToken } from '@/services/auth';
import { stopUnreadListener } from '@/services/unread';
import { config } from '@/config';

type PermissionStatus = 'granted' | 'denied' | 'undetermined' | 'limited';

function statusLabel(s: PermissionStatus) {
  switch (s) {
    case 'granted': return 'Enabled';
    case 'limited': return 'Limited';
    case 'denied': return 'Disabled';
    default: return 'Not Set';
  }
}

function statusColor(s: PermissionStatus) {
  switch (s) {
    case 'granted': return '#34C759';
    case 'limited': return '#FF9500';
    default: return colors.mutedForeground;
  }
}

export default function SettingsScreen() {
  const router = useRouter();
  const [notifStatus, setNotifStatus] = useState<PermissionStatus>('undetermined');
  const [cameraStatus, setCameraStatus] = useState<PermissionStatus>('undetermined');
  const [photosStatus, setPhotosStatus] = useState<PermissionStatus>('undetermined');

  const checkPermissions = useCallback(async () => {
    const [notif, camera, photos] = await Promise.all([
      Notifications.getPermissionsAsync(),
      ImagePicker.getCameraPermissionsAsync(),
      ImagePicker.getMediaLibraryPermissionsAsync(),
    ]);
    setNotifStatus(notif.status as PermissionStatus);
    setCameraStatus(camera.status as PermissionStatus);
    setPhotosStatus(photos.status as PermissionStatus);
  }, []);

  useFocusEffect(
    useCallback(() => {
      checkPermissions();
    }, [])
  );

  const handleSignOut = async () => {
    stopUnreadListener();
    await signOut();
    router.dismissAll();
    router.replace('/login');
  };

  const handleDeleteAccount = () => {
    Alert.alert(
      'Delete Account',
      'This will permanently delete your profile and account. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              stopUnreadListener();
              const token = getIdToken();
              await fetch(`${config.apiBaseUrl}/profile`, {
                method: 'DELETE',
                headers: token ? { Authorization: `Bearer ${token}` } : {},
              });
              await deleteFirebaseAccount();
              router.dismissAll();
              router.replace('/login');
            } catch (e: any) {
              Alert.alert('Error', e.message ?? 'Failed to delete account');
            }
          },
        },
      ],
    );
  };

  const openSystemSettings = () => Linking.openSettings();

  return (
    <GradientScreen>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </Pressable>
        <Text variant="heading">Settings</Text>
        <View style={styles.backButton} />
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {/* ── Permissions ───────────────────────────────── */}
        <Text style={styles.sectionTitle}>Permissions</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="notifications-outline"
            label="Notifications"
            status={notifStatus}
            onPress={openSystemSettings}
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="camera-outline"
            label="Camera"
            status={cameraStatus}
            onPress={openSystemSettings}
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="images-outline"
            label="Photo Library"
            status={photosStatus}
            onPress={openSystemSettings}
          />
        </View>
        <Text style={styles.hint}>
          Permissions are managed by iOS. Tap to open system settings.
        </Text>

        {/* ── Account ───────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Account</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="pencil-outline"
            label="Edit Profile"
            onPress={() => router.push('/edit-profile')}
            showChevron
          />
        </View>

        {/* ── Support ───────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Support</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="document-text-outline"
            label="Terms of Service"
            onPress={() => {}}
            showChevron
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="shield-checkmark-outline"
            label="Privacy Policy"
            onPress={() => {}}
            showChevron
          />
        </View>

        {/* ── Danger Zone ───────────────────────────────── */}
        <View style={styles.dangerSection}>
          <Pressable style={styles.dangerRow} onPress={handleSignOut}>
            <Ionicons name="log-out-outline" size={20} color={colors.primary} />
            <Text style={styles.dangerText}>Sign Out</Text>
          </Pressable>
          <Pressable style={styles.dangerRow} onPress={handleDeleteAccount}>
            <Ionicons name="trash-outline" size={20} color="#FF3B30" />
            <Text style={[styles.dangerText, { color: '#FF3B30' }]}>Delete Account</Text>
          </Pressable>
        </View>
      </ScrollView>
    </GradientScreen>
  );
}

/* ── Reusable row component ─────────────────────────────────── */

function SettingsRow({
  icon,
  label,
  status,
  onPress,
  showChevron,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  status?: PermissionStatus;
  onPress: () => void;
  showChevron?: boolean;
}) {
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View style={styles.rowLeft}>
        <Ionicons name={icon} size={20} color={colors.foreground} />
        <Text style={styles.rowLabel}>{label}</Text>
      </View>
      <View style={styles.rowRight}>
        {status && (
          <Text style={[styles.rowStatus, { color: statusColor(status) }]}>
            {statusLabel(status)}
          </Text>
        )}
        {(showChevron || status) && (
          <Ionicons name="chevron-forward" size={16} color={colors.mutedForeground} />
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  backButton: {
    width: 40,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: 60,
  },
  sectionTitle: {
    fontSize: 13,
    ...fonts.semibold,
    color: colors.mutedForeground,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
    marginLeft: spacing.xs,
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    paddingHorizontal: spacing.md,
  },
  rowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  rowRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  rowLabel: {
    fontSize: 16,
    color: colors.foreground,
  },
  rowStatus: {
    fontSize: 14,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginLeft: 44,
  },
  hint: {
    fontSize: 12,
    color: colors.mutedForeground,
    marginTop: spacing.xs,
    marginLeft: spacing.xs,
  },
  dangerSection: {
    marginTop: spacing['2xl'],
    gap: spacing.sm,
  },
  dangerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: spacing.md,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
  },
  dangerText: {
    fontSize: 16,
    ...fonts.medium,
    color: colors.primary,
  },
});
