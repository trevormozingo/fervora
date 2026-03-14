import { useEffect, useRef } from 'react';
import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { addNotificationResponseListener, addNotificationReceivedListener } from '@/services/notifications';
import { setScrollToPostIntent } from '@/services/scrollToPost';
import type { EventSubscription } from 'expo-notifications';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,      // data fresh for 30s
      gcTime: 5 * 60_000,     // keep in cache 5min after unmount
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export default function RootLayout() {
  const router = useRouter();
  const notifListenerRef = useRef<EventSubscription>();
  const fgListenerRef = useRef<EventSubscription>();

  useEffect(() => {
    // Refresh badge + notification list when a push arrives in the foreground
    fgListenerRef.current = addNotificationReceivedListener(() => {
      queryClient.invalidateQueries({ queryKey: ['unreadNotifCount'] });
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    });

    // Handle notification taps → navigate based on type
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
      } else if (data?.type === 'follow' && data?.followerUsername) {
        router.push(`/user/${data.followerUsername}` as any);
      } else if (data?.type === 'comment' || data?.type === 'reaction') {
        if (data?.postId) {
          setScrollToPostIntent(
            data.postId as string,
            data.type === 'comment' ? 'comments' : 'reactions',
            data.reactionType as string | undefined,
          );
        }
        router.navigate('/(home)/profile' as any);
      }
    });

    return () => {
      notifListenerRef.current?.remove();
      fgListenerRef.current?.remove();
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
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
        <Stack.Screen name="notifications" />
        <Stack.Screen name="follow-list" />
      </Stack>
    </QueryClientProvider>
  );
}
