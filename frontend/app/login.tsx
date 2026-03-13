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

  /** Strip to digits only */
  const digitsOnly = (value: string) => value.replace(/\D/g, '');

  /** Format 10 digits as (xxx) xxx-xxxx */
  const formatPhone = (raw: string) => {
    const digits = digitsOnly(raw);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
  };

  const handlePhoneChange = (text: string) => {
    const digits = digitsOnly(text).slice(0, 10);
    setPhone(formatPhone(digits));
  };

  /** Convert display format to E.164 */
  const toE164 = (value: string) => `+1${digitsOnly(value)}`;

  const isValidPhone = digitsOnly(phone).length === 10;

  const handleSendCode = async () => {
    if (!isValidPhone) {
      Alert.alert('Invalid Phone Number', 'Please enter a valid 10-digit US phone number.');
      return;
    }
    const e164 = toE164(phone);
    setLoading(true);
    try {
      const { sessionInfo, code: autoCode } = await sendVerificationCode(e164);
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

      // Register for push notifications now that we're signed in
      const { registerForPushNotifications } = await import('@/services/notifications');
      registerForPushNotifications();

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
                placeholder="(555) 123-4567"
                keyboardType="phone-pad"
                autoCapitalize="none"
                value={`+1 ${phone}`}
                onChangeText={(text) => handlePhoneChange(text.replace(/^\+1\s?/, ''))}
                maxLength={17}
              />
              <Button
                label="Send Verification Code"
                onPress={handleSendCode}
                disabled={!isValidPhone}
                loading={loading}
                style={styles.button}
              />
            </>
          ) : (
            <>
              <Text muted style={styles.codeHint}>
                Enter the code sent to +1 {phone}
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
