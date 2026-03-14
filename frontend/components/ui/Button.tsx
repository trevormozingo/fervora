import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  type TouchableOpacityProps,
} from 'react-native';
import { colors, fonts, fontSizes, radii, spacing } from './theme';

type Variant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends TouchableOpacityProps {
  label: string;
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export function Button({
  label,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  style,
  ...rest
}: ButtonProps) {
  return (
    <TouchableOpacity
      style={[
        styles.base,
        sizeStyles[size],
        variantStyles[variant],
        (disabled || loading) && styles.disabled,
        style,
      ]}
      disabled={disabled || loading}
      activeOpacity={0.7}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator
          color={variant === 'primary' || variant === 'destructive'
            ? colors.primaryForeground
            : colors.foreground}
        />
      ) : (
        <Text
          style={[
            styles.label,
            labelSizeStyles[size],
            labelVariantStyles[variant],
          ]}
        >
          {label}
        </Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radii.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: {
    opacity: 0.5,
  },
  label: {
    ...fonts.semibold,
  },
});

const sizeStyles = StyleSheet.create({
  sm: {
    height: 38,
    paddingHorizontal: spacing.md,
  },
  md: {
    height: 50,
    paddingHorizontal: spacing.lg,
  },
  lg: {
    height: 56,
    paddingHorizontal: spacing.xl,
  },
});

const labelSizeStyles = StyleSheet.create({
  sm: { fontSize: fontSizes.sm },
  md: { fontSize: fontSizes.base },
  lg: { fontSize: fontSizes.lg },
});

const variantStyles = StyleSheet.create({
  primary: {
    backgroundColor: colors.primary,
  },
  secondary: {
    backgroundColor: colors.muted,
  },
  outline: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.border,
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  destructive: {
    backgroundColor: colors.destructive,
  },
});

const labelVariantStyles = StyleSheet.create({
  primary: { color: colors.primaryForeground },
  secondary: { color: colors.foreground },
  outline: { color: colors.foreground },
  ghost: { color: colors.foreground },
  destructive: { color: colors.destructiveForeground },
});
