import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { ProfileForm, type ProfileFormData } from '@/components/ProfileForm';
import { getIdToken } from '@/services/auth';
import { uploadProfilePhoto } from '@/services/storage';
import { config } from '@/config';

export default function CreateProfileScreen() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (data: ProfileFormData) => {
    setSubmitting(true);
    try {
      const token = getIdToken();
      const authHeaders: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};

      // Upload photo first if picked
      let profilePhoto: string | null = null;
      if (data.photoUri) {
        const url = await uploadProfilePhoto(data.photoUri);
        profilePhoto = url;
      }

      const payload: Record<string, unknown> = {
        username: data.username,
        displayName: data.displayName,
        birthday: data.birthday || null,
        profilePhoto,
      };
      if (data.bio) payload.bio = data.bio;
      if (data.locationCoords) {
        payload.location = { type: 'Point', coordinates: data.locationCoords, label: data.locationLabel };
      }
      if (data.interests.length > 0) payload.interests = data.interests;
      if (data.fitnessLevel) payload.fitnessLevel = data.fitnessLevel;

      const res = await fetch(`${config.apiBaseUrl}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Failed to create profile (${res.status})`);
      }

      router.replace('/(home)/feed');
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <GradientScreen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.inner}
      >
        <View style={styles.header}>
          <Text variant="title">Create Profile</Text>
          <Text muted style={styles.subtitle}>Set up your profile to get started</Text>
        </View>

        <ProfileForm
          showUsername
          requirePhoto
          requireBirthday
          submitLabel="Create Profile"
          submitting={submitting}
          onSubmit={handleSubmit}
        />
      </KeyboardAvoidingView>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  inner: {
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing['2xl'],
    marginTop: spacing.xl,
  },
  subtitle: {
    marginTop: spacing.sm,
  },
});
