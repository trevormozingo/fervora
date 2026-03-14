/**
 * Push notification service — Expo Notifications + backend token registration.
 */

import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { getIdToken } from './auth';
import { config } from '@/config';

// ── Configure notification behavior ──────────────────────────────────

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

// ── Token registration ───────────────────────────────────────────────

/**
 * Request permission, get the Expo push token, and register it with the backend.
 * Returns the token string or null if permissions were denied.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  // Push notifications only work on physical devices
  if (!Device.isDevice) {
    console.log('[notifications] Skipping — not a physical device');
    return null;
  }

  // Check / request permission
  const { status: existing } = await Notifications.getPermissionsAsync();
  let finalStatus = existing;
  if (existing !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== 'granted') {
    console.log('[notifications] Permission not granted');
    return null;
  }

  // Get the Expo push token
  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    Constants.expoConfig?.slug ??
    'fervora';
  console.log('[notifications] Using projectId:', projectId);
  const tokenData = await Notifications.getExpoPushTokenAsync({
    projectId,
  });
  const expoPushToken = tokenData.data;
  console.log('[notifications] Got push token:', expoPushToken);

  // Android needs a notification channel
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Default',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#F5515F',
    });
  }

  // Register with the backend
  await saveTokenToBackend(expoPushToken);

  return expoPushToken;
}

async function saveTokenToBackend(token: string): Promise<void> {
  const idToken = getIdToken();
  if (!idToken) {
    console.warn('[notifications] No auth token — skipping backend registration');
    return;
  }
  try {
    const res = await fetch(`${config.apiBaseUrl}/profile/push-token`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${idToken}`,
      },
      body: JSON.stringify({ token }),
    });
    console.log('[notifications] Backend registration:', res.status);
  } catch (e) {
    console.warn('[notifications] Failed to save push token:', e);
  }
}

// ── Send notification to recipients ──────────────────────────────────

/**
 * Ask the backend to send a push notification to a list of UIDs.
 */
export async function sendPushToUsers(
  recipientUids: string[],
  title: string,
  body: string,
  data?: Record<string, string>,
): Promise<void> {
  const idToken = getIdToken();
  if (!idToken || recipientUids.length === 0) return;
  try {
    await fetch(`${config.apiBaseUrl}/profile/send-push`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${idToken}`,
      },
      body: JSON.stringify({
        recipientUids,
        title,
        body,
        data: data ?? {},
      }),
    });
  } catch (e) {
    console.warn('[notifications] Failed to send push:', e);
  }
}

// ── Listener helpers ─────────────────────────────────────────────────

/**
 * Subscribe to notification taps (when user taps a notification to open the app).
 */
export function addNotificationResponseListener(
  handler: (response: Notifications.NotificationResponse) => void,
): Notifications.EventSubscription {
  return Notifications.addNotificationResponseReceivedListener(handler);
}

/**
 * Subscribe to notifications received while the app is in the foreground.
 */
export function addNotificationReceivedListener(
  handler: (notification: Notifications.Notification) => void,
): Notifications.EventSubscription {
  return Notifications.addNotificationReceivedListener(handler);
}
