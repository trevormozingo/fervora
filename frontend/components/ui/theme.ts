/**
 * Iron Guild Design Tokens
 *
 * Central place for colors, typography, spacing, and radii.
 * Import from '@/components/ui' and reference via the `theme` object.
 */

export const colors = {
  // Brand
  primary: '#111111',
  primaryForeground: '#FFFFFF',

  // Neutrals
  background: '#e9e9e9',
  foreground: '#111111',
  muted: '#F9F9F9',
  mutedForeground: '#666666',
  border: '#DDDDDD',
  placeholder: '#999999',

  // Feedback
  destructive: '#DC2626',
  destructiveForeground: '#FFFFFF',
  success: '#16A34A',
  successForeground: '#FFFFFF',
} as const;

export const fonts = {
  regular: {
    fontWeight: '400' as const,
  },
  medium: {
    fontWeight: '500' as const,
  },
  semibold: {
    fontWeight: '600' as const,
  },
  bold: {
    fontWeight: '700' as const,
  },
};

export const fontSizes = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
  '4xl': 36,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  '2xl': 48,
} as const;

export const radii = {
  sm: 5,
  md: 5,
  lg: 5,
  full: 9999,
} as const;

/** Shared style for floating action buttons (settings, edit, add, etc.) */
export const floatingButton = {
  position: 'absolute' as const,
  zIndex: 10,
  width: 44,
  height: 44,
  borderRadius: 22,
  backgroundColor: colors.muted,
  justifyContent: 'center' as const,
  alignItems: 'center' as const,
  shadowColor: '#000',
  shadowOffset: { width: 0, height: 2 },
  shadowOpacity: 0.15,
  shadowRadius: 4,
  elevation: 4,
} as const;

export const theme = {
  colors,
  fonts,
  fontSizes,
  spacing,
  radii,
  floatingButton,
} as const;
