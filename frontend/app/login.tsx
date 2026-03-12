import { useState } from 'react';
import { Alert, Image, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Button, GradientScreen, Input, Text, colors, spacing } from '@/components/ui';

const logo = require('@/assets/images/logo.png');
import { sendVerificationCode, verifyCode, getIdToken } from '@/services/auth';
import { config } from '@/config';

export default function LoginScreen() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const codeSent = !!verificationId;

  const handleSendCode = async () => {
    setLoading(true);
    try {
      const { sessionInfo, code: autoCode } = await sendVerificationCode(phone);
      setVerificationId(sessionInfo);
      // In emulator mode, auto-fill the code
      if (autoCode) setCode(autoCode);
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Failed to send code');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!verificationId) return;
    setLoading(true);
    try {
      const { uid } = await verifyCode(verificationId, code);
      console.log('Signed in as', uid);

      // Fetch existing profile
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/profile`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (res.ok) {
        router.replace('/(home)/feed');
      } else if (res.status === 404) {
        // No profile yet — go to create
        router.replace('/create-profile');
      } else {
        throw new Error(`Failed to fetch profile (${res.status})`);
      }
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Invalid code');
    } finally {
      setLoading(false);
    }
  };

  return (
    <GradientScreen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.inner}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
        <View style={styles.header}>
          <Image source={logo} style={styles.logo} resizeMode="contain" />
          <Text variant="title">Fervora</Text>
          <Text muted style={styles.tagline}>Track. Compete. Conquer.</Text>
        </View>

        <View style={styles.form}>
          {!codeSent ? (
            <>
              <Input
                placeholder="Phone Number"
                keyboardType="phone-pad"
                autoCapitalize="none"
                value={phone}
                onChangeText={setPhone}
              />
              <Button
                label="Send Verification Code"
                onPress={handleSendCode}
                disabled={!phone.trim()}
                loading={loading}
                style={styles.button}
              />
            </>
          ) : (
            <>
              <Text muted style={styles.codeHint}>
                Enter the code sent to {phone}
              </Text>
              <Input
                placeholder="Verification Code"
                keyboardType="number-pad"
                autoCapitalize="none"
                value={code}
                onChangeText={setCode}
              />
              <Button
                label="Verify & Sign In"
                onPress={handleVerifyCode}
                disabled={!code.trim()}
                loading={loading}
                style={styles.button}
              />
              <Button
                label="Use a different number"
                variant="ghost"
                onPress={() => { setVerificationId(null); setCode(''); }}
              />
            </>
          )}
        </View>

        <View style={styles.features}>
          <View style={styles.featureRow}>
            <Ionicons name="barbell-outline" size={18} color={colors.mutedForeground} />
            <Text muted style={styles.featureText}>Log workouts & share PRs</Text>
          </View>
          <View style={styles.featureRow}>
            <Ionicons name="people-outline" size={18} color={colors.mutedForeground} />
            <Text muted style={styles.featureText}>Find lifters near you</Text>
          </View>
          <View style={styles.featureRow}>
            <Ionicons name="trophy-outline" size={18} color={colors.mutedForeground} />
            <Text muted style={styles.featureText}>Compete & stay accountable</Text>
          </View>
        </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </GradientScreen>
  );
}

const LOGO_SIZE = 120;

const styles = StyleSheet.create({
  inner: {
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingVertical: spacing['2xl'],
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing['2xl'],
  },
  logo: {
    width: LOGO_SIZE,
    height: LOGO_SIZE,
    marginBottom: spacing.lg,
  },
  tagline: {
    marginTop: spacing.sm,
    fontSize: 15,
    letterSpacing: 1.5,
  },
  form: {
    gap: spacing.md,
  },
  codeHint: {
    textAlign: 'center',
  },
  button: {
    marginTop: spacing.sm,
  },
  features: {
    marginTop: spacing['2xl'],
    gap: spacing.md,
    alignItems: 'center',
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  featureText: {
    fontSize: 14,
  },
});
