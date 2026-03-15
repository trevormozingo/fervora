import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, gradientColors, gradientStart, gradientEnd } from '@/components/ui';
import { useUnreadCount } from '@/services/unread';

export default function HomeLayout() {
  const unreadCount = useUnreadCount();

  return (
    <LinearGradient
      colors={[...gradientColors]}
      start={gradientStart}
      end={gradientEnd}
      style={{ flex: 1 }}
    >
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.primary,
          tabBarInactiveTintColor: colors.mutedForeground,
          tabBarStyle: {
            backgroundColor: 'transparent',
            borderTopColor: 'rgba(255, 255, 255, 0.1)',
            elevation: 0,
          },
          sceneStyle: { backgroundColor: 'transparent' },
        }}
      >
      <Tabs.Screen
        name="feed"
        options={{
          title: 'Feed',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="events"
        options={{
          title: 'Events',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="calendar-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="messages"
        options={{
          title: 'Messages',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="chatbubble-outline" size={size} color={color} />
          ),
          tabBarBadge: unreadCount > 0 ? unreadCount : undefined,
          tabBarBadgeStyle: { backgroundColor: colors.primary, fontSize: 11 },
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
    </LinearGradient>
  );
}
