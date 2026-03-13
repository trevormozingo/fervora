import { useEffect, useRef } from 'react';
import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { addNotificationResponseListener } from '@/services/notifications';
import type { EventSubscription } from 'expo-notifications';

export default function RootLayout() {
  const router = useRouter();
  const notifListenerRef = useRef<EventSubscription>();

  useEffect(() => {
    // Handle notification taps → navigate to conversation
    notifListenerRef.current = addNotificationResponseListener((response) => {
      const data = response.notification.request.content.data;
      if (data?.conversationId && data?.otherUid) {
        router.push({
          pathname: '/conversation',
          params: {
            conversationId: data.conversationId as string,
            otherUid: data.otherUid as string,
          },
        });
      }
    });

    return () => {
      notifListenerRef.current?.remove();
    };
  }, []);

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="login" options={{ animationTypeForReplace: 'pop' }} />
        <Stack.Screen name="create-profile" />
        <Stack.Screen name="create-post" options={{ presentation: 'formSheet', headerShown: false, sheetCornerRadius: 0 }} />
        <Stack.Screen name="(home)" />
        <Stack.Screen name="settings" />
        <Stack.Screen name="edit-profile" />
        <Stack.Screen name="friends" />
        <Stack.Screen name="conversation" />
        <Stack.Screen name="new-chat" />
      </Stack>
    </>
  );
}
