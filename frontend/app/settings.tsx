import { Alert, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Button, GradientScreen, Text, colors, spacing } from '@/components/ui';
import { signOut, deleteFirebaseAccount, getIdToken } from '@/services/auth';
import { stopUnreadListener } from '@/services/unread';
import { config } from '@/config';

export default function SettingsScreen() {
  const router = useRouter();

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
              // Delete profile from backend
              await fetch(`${config.apiBaseUrl}/profile`, {
                method: 'DELETE',
                headers: token ? { Authorization: `Bearer ${token}` } : {},
              });
              // Delete Firebase account
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

  return (
    <GradientScreen>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </Pressable>
        <Text variant="heading">Settings</Text>
        <View style={styles.backButton} />
      </View>
      <View style={styles.content}>
        {/* Settings options will go here */}
      </View>
      <View style={styles.footer}>
        <Button label="Delete Account" variant="outline" onPress={handleDeleteAccount} />
        <View style={styles.buttonGap} />
        <Button label="Sign Out" variant="destructive" onPress={handleSignOut} />
      </View>
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
  content: {
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },
  buttonGap: {
    height: spacing.md,
  },
});
