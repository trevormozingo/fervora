import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { ProfileForm, type ProfileFormData } from '@/components/ProfileForm';
import { getIdToken } from '@/services/auth';
import { uploadProfilePhoto } from '@/services/storage';
import { config } from '@/config';

export default function EditProfileScreen() {
  const router = useRouter();
  const [initial, setInitial] = useState<Partial<ProfileFormData> | null>(null);
  const [existingPhotoUrl, setExistingPhotoUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const token = getIdToken();
        const res = await fetch(`${config.apiBaseUrl}/profile`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const profile = await res.json();
          setInitial({
            displayName: profile.displayName ?? '',
            bio: profile.bio ?? '',
            birthday: profile.birthday ?? '',
            locationCoords: profile.location?.coordinates ?? null,
            locationLabel: profile.location?.label ?? null,
            interests: profile.interests ?? [],
            fitnessLevel: profile.fitnessLevel ?? null,
          });
          if (profile.profilePhoto) setExistingPhotoUrl(profile.profilePhoto);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleSubmit = async (data: ProfileFormData) => {
    setSubmitting(true);
    try {
      const token = getIdToken();
      const authHeaders: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};

      if (data.photoUri) {
        await uploadProfilePhoto(data.photoUri);
      }

      const payload: Record<string, unknown> = {
        displayName: data.displayName,
        bio: data.bio || null,
        birthday: data.birthday || null,
      };
      if (data.locationCoords) {
        payload.location = { type: 'Point', coordinates: data.locationCoords, label: data.locationLabel };
      }
      payload.interests = data.interests.length > 0 ? data.interests : null;
      payload.fitnessLevel = data.fitnessLevel;

      const res = await fetch(`${config.apiBaseUrl}/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Failed to update profile (${res.status})`);
      }

      router.back();
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <GradientScreen>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </GradientScreen>
    );
  }

  return (
    <GradientScreen>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </Pressable>
        <Text variant="heading">Edit Profile</Text>
        <View style={styles.backButton} />
      </View>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.inner}
      >
        <ProfileForm
          initial={initial ?? undefined}
          existingPhotoUrl={existingPhotoUrl}
          submitLabel="Save"
          submitting={submitting}
          onSubmit={handleSubmit}
        />
      </KeyboardAvoidingView>
    </GradientScreen>
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
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  inner: {
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
});
