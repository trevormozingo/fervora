import { useEffect, useState, useCallback } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { Ionicons } from '@expo/vector-icons';
import { restoreAuth, getIdToken } from '@/services/auth';
import { registerForPushNotifications } from '@/services/notifications';
import { startUnreadListener } from '@/services/unread';
import { config } from '@/config';
import { colors, Text, fonts, fontSizes, spacing, radii } from '@/components/ui';

export default function Index() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [connectionError, setConnectionError] = useState(false);

  const bootstrap = useCallback(async () => {
    setChecking(true);
    setConnectionError(false);

    const hasToken = await restoreAuth();

    if (!hasToken) {
      await SplashScreen.hideAsync();
      router.replace('/login');
      return;
    }

    // Has a token — check profile status
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/profile`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (res.ok) {
        registerForPushNotifications()
          .then((t) => console.log('[index] Push registration result:', t))
          .catch((e) => console.error('[index] Push registration error:', e));
        startUnreadListener();
        await SplashScreen.hideAsync();
        router.replace('/(home)/feed');
      } else {
        await SplashScreen.hideAsync();
        if (res.status === 404) {
          router.replace('/create-profile');
        } else {
          router.replace('/login');
        }
      }
    } catch {
      await SplashScreen.hideAsync();
      setChecking(false);
      setConnectionError(true);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, []);

  if (connectionError) {
    return (
      <LinearGradient
        colors={['#e8e0f0', '#d4e4f7', '#e0eef5']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.container}
      >
        <Ionicons name="cloud-offline-outline" size={56} color={colors.mutedForeground} />
        <Text style={styles.errorTitle}>Can't Connect</Text>
        <Text style={styles.errorSubtitle}>
          Unable to reach the server. Check your connection and try again.
        </Text>
        <Pressable style={styles.retryButton} onPress={bootstrap}>
          <Ionicons name="refresh" size={18} color={colors.primaryForeground} />
          <Text style={styles.retryText}>Retry</Text>
        </Pressable>
      </LinearGradient>
    );
  }

  if (checking) {
    return (
      <LinearGradient
        colors={['#e8e0f0', '#d4e4f7', '#e0eef5']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.container}
      >
        <ActivityIndicator size="large" color={colors.primary} />
      </LinearGradient>
    );
  }

  return null;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  errorTitle: {
    fontSize: fontSizes.xl,
    ...fonts.bold,
    color: colors.foreground,
    marginTop: spacing.md,
  },
  errorSubtitle: {
    fontSize: fontSizes.sm,
    color: colors.mutedForeground,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 20,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
    marginTop: spacing.lg,
  },
  retryText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
});
