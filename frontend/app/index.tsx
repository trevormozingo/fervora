import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { restoreAuth, getIdToken } from '@/services/auth';
import { registerForPushNotifications } from '@/services/notifications';
import { config } from '@/config';
import { colors } from '@/components/ui';

export default function Index() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    (async () => {
      const hasToken = await restoreAuth();

      if (!hasToken) {
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
          router.replace('/(home)/feed');
        } else {
          // 404 or 401 — go to login or create-profile
          if (res.status === 404) {
            router.replace('/create-profile');
          } else {
            router.replace('/login');
          }
        }
      } catch {
        router.replace('/login');
      }
    })();
  }, []);

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
  },
});
