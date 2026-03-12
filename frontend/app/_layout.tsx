import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

export default function RootLayout() {
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
      </Stack>
    </>
  );
}
