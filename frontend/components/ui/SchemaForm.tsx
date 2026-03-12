import { useState, useCallback } from 'react';
import { Modal, Platform, Pressable, StyleSheet, View } from 'react-native';
import type { ZodTypeAny } from 'zod';
import DateTimePicker from '@react-native-community/datetimepicker';
import type { FieldMeta } from '@/models/profile';
import { Input } from './Input';
import { Button } from './Button';
import { Text } from './Text';
import { colors, fontSizes, fonts, radii, spacing } from './theme';

interface SchemaFormProps {
  /** Array of field metadata objects describing the form fields */
  fields: FieldMeta[];
  /** Zod schema used for validation on submit */
  schema: ZodTypeAny;
  /** Called with validated data when the form passes validation */
  onSubmit: (data: Record<string, unknown>) => Promise<void> | void;
  /** Label shown on the submit button */
  submitLabel?: string;
  /** Optional initial values to pre-fill the form */
  initialValues?: Record<string, unknown>;
}

export function SchemaForm({
  fields,
  schema,
  onSubmit,
  submitLabel = 'Submit',
  initialValues,
}: SchemaFormProps) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of fields) init[f.name] = initialValues?.[f.name] != null ? String(initialValues[f.name]) : '';
    return init;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const setValue = useCallback((name: string, text: string) => {
    setValues((prev) => ({ ...prev, [name]: text }));
    setErrors((prev) => {
      if (!prev[name]) return prev;
      const next = { ...prev };
      delete next[name];
      return next;
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    // Build the data object — send empty optional strings as undefined
    const data: Record<string, unknown> = {};
    for (const f of fields) {
      const val = values[f.name];
      if (val === '' && !f.required) {
        // omit optional empty fields
        continue;
      }
      data[f.name] = val;
    }

    const result = schema.safeParse(data);
    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        const key = String(issue.path[0] ?? '');
        if (key && !fieldErrors[key]) {
          fieldErrors[key] = issue.message;
        }
      }
      setErrors(fieldErrors);
      return;
    }

    setErrors({});
    setLoading(true);
    try {
      await onSubmit(result.data as Record<string, unknown>);
    } finally {
      setLoading(false);
    }
  }, [fields, values, schema, onSubmit]);

  // Disable submit when all required fields are empty
  const hasAllRequired = fields
    .filter((f) => f.required)
    .every((f) => values[f.name]?.trim());

  return (
    <View style={styles.form}>
      {fields.map((field) => (
        <View key={field.name} style={styles.fieldContainer}>
          {field.inputType === 'date' ? (
            <DateField
              label={field.label}
              placeholder={field.placeholder}
              value={values[field.name]}
              onChange={(iso) => setValue(field.name, iso)}
              error={errors[field.name]}
            />
          ) : (
            <Input
              label={field.label}
              placeholder={field.placeholder}
              value={values[field.name]}
              onChangeText={(text) => setValue(field.name, text)}
              error={errors[field.name]}
              keyboardType={field.keyboard}
              secureTextEntry={field.secure}
              multiline={field.multiline}
              autoCapitalize="none"
              autoCorrect={false}
              maxLength={field.maxLength}
              style={field.multiline ? styles.multiline : undefined}
            />
          )}
        </View>
      ))}
      <Button
        label={submitLabel}
        onPress={handleSubmit}
        disabled={!hasAllRequired}
        loading={loading}
        style={styles.button}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: spacing.md,
  },
  fieldContainer: {
    gap: spacing.xs,
  },
  multiline: {
    height: 120,
    textAlignVertical: 'top',
    paddingTop: spacing.sm,
  },
  button: {
    marginTop: spacing.sm,
  },
});

// ── Date field sub-component ──────────────────────────────────────────────────

function formatDisplay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function DateField({
  label,
  placeholder,
  value,
  onChange,
  error,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (iso: string) => void;
  error?: string;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const [tempDate, setTempDate] = useState<Date | null>(null);

  const dateValue = value
    ? (() => { const [y, m, d] = value.split('-').map(Number); return new Date(y, m - 1, d); })()
    : new Date(2000, 0, 1);

  const openPicker = () => {
    setTempDate(dateValue);
    setShowPicker(true);
  };

  const handleChange = (_event: any, selected?: Date) => {
    if (Platform.OS === 'android') {
      setShowPicker(false);
      if (selected) {
        const iso = `${selected.getFullYear()}-${String(selected.getMonth() + 1).padStart(2, '0')}-${String(selected.getDate()).padStart(2, '0')}`;
        onChange(iso);
      }
    } else if (selected) {
      setTempDate(selected);
    }
  };

  const handleDone = () => {
    if (tempDate) {
      const iso = `${tempDate.getFullYear()}-${String(tempDate.getMonth() + 1).padStart(2, '0')}-${String(tempDate.getDate()).padStart(2, '0')}`;
      onChange(iso);
    }
    setShowPicker(false);
  };

  return (
    <View style={dateStyles.wrapper}>
      {label && <RNText style={dateStyles.label}>{label}</RNText>}
      <Pressable onPress={openPicker} style={dateStyles.trigger}>
        <Ionicons name="calendar-outline" size={18} color={value ? colors.foreground : colors.placeholder} />
        <RNText style={value ? dateStyles.triggerText : dateStyles.triggerPlaceholder}>
          {value ? formatDisplay(value) : placeholder}
        </RNText>
        <Ionicons name="chevron-down" size={16} color={colors.placeholder} />
      </Pressable>
      {error && <RNText style={dateStyles.error}>{error}</RNText>}

      <Modal visible={showPicker} transparent animationType="slide">
        <View style={dateStyles.modalOverlay}>
          <View style={dateStyles.modalSheet}>
            <View style={dateStyles.modalHeader}>
              <Pressable onPress={() => setShowPicker(false)}>
                <RNText style={dateStyles.modalCancel}>Cancel</RNText>
              </Pressable>
              <RNText style={dateStyles.modalTitle}>{label}</RNText>
              <Pressable onPress={handleDone}>
                <RNText style={dateStyles.modalDone}>Done</RNText>
              </Pressable>
            </View>
            <DateTimePicker
              value={tempDate ?? dateValue}
              mode="date"
              display="spinner"
              maximumDate={new Date()}
              onChange={handleChange}
              themeVariant="light"
              style={dateStyles.picker}
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}

import { Text as RNText } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const dateStyles = StyleSheet.create({
  wrapper: {
    gap: spacing.xs,
  },
  label: {
    fontSize: fontSizes.sm,
    ...fonts.medium,
    color: colors.foreground,
  },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  triggerText: {
    flex: 1,
    fontSize: fontSizes.base,
    color: colors.foreground,
  },
  triggerPlaceholder: {
    flex: 1,
    fontSize: fontSizes.base,
    color: colors.placeholder,
  },
  error: {
    fontSize: fontSizes.xs,
    color: colors.destructive,
    marginTop: 2,
  },
  modalOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  modalSheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: 0,
    borderTopRightRadius: 0,
    paddingBottom: 34, // safe area
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  modalTitle: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.foreground,
  },
  modalCancel: {
    fontSize: fontSizes.base,
    color: colors.mutedForeground,
  },
  modalDone: {
    fontSize: fontSizes.base,
    ...fonts.semibold,
    color: colors.primary,
  },
  picker: {
    height: 216,
  },
});
