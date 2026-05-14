// src/components/PatientModal.tsx
import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Modal,
  ScrollView,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { PatientInfo } from '../types';

interface Props {
  visible: boolean;
  initial?: PatientInfo;
  onSave: (patient: PatientInfo) => void;
  onClose: () => void;
}

export const PatientModal: React.FC<Props> = ({
  visible,
  initial,
  onSave,
  onClose,
}) => {
  const { t } = useTranslation();
  const [form, setForm] = useState<Partial<PatientInfo>>(initial ?? {});

  const handleSave = () => {
    if (!form.name?.trim()) return;
    onSave({
      ...initial,
      id: initial?.id ?? `patient-${Date.now()}`,
      name: form.name!,
      age: form.age,
      gender: form.gender,
      medicalRecordNumber: form.medicalRecordNumber,
      diagnosis: form.diagnosis,
      notes: form.notes,
    });
    onClose();
  };

  const field = (
    key: keyof PatientInfo,
    label: string,
    placeholder?: string,
    multiline?: boolean,
  ) => (
    <View style={styles.field} key={key}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, multiline && styles.multiline]}
        value={form[key]?.toString() ?? ''}
        onChangeText={(v) =>
          setForm((prev) => ({
            ...prev,
            [key]: key === 'age' ? (v ? parseInt(v) : undefined) : v,
          }))
        }
        placeholder={placeholder ?? label}
        placeholderTextColor="#B0C4C4"
        multiline={multiline}
        numberOfLines={multiline ? 3 : 1}
        keyboardType={key === 'age' ? 'numeric' : 'default'}
      />
    </View>
  );

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView
        style={styles.overlay}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <Text style={styles.title}>{t('patient.title')}</Text>

          <ScrollView showsVerticalScrollIndicator={false}>
            {field('name', t('patient.name'), 'Zhang San')}
            {field('age', t('patient.age'), '45', false)}
            {field('gender', t('patient.gender'), 'Male / Female')}
            {field('medicalRecordNumber', t('patient.mrn'), 'MRN-000123')}
            {field('diagnosis', t('patient.diagnosis'), 'e.g. Hypertension')}
            {field('notes', t('patient.notes'), 'Additional notes...', true)}
          </ScrollView>

          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.cancelBtn}
              onPress={onClose}
              activeOpacity={0.7}
            >
              <Text style={styles.cancelText}>{t('patient.cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.saveBtn, !form.name?.trim() && styles.disabled]}
              onPress={handleSave}
              activeOpacity={0.8}
              disabled={!form.name?.trim()}
            >
              <Text style={styles.saveText}>{t('patient.save')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#FAFEFE',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingBottom: 36,
    maxHeight: '85%',
  },
  handle: {
    width: 36,
    height: 4,
    backgroundColor: '#D1DFE0',
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: 12,
    marginBottom: 16,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0D7377',
    marginBottom: 20,
  },
  field: { marginBottom: 14 },
  label: {
    fontSize: 12,
    fontWeight: '600',
    color: '#6A9999',
    marginBottom: 6,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D8EAEA',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#1A2B2B',
  },
  multiline: { height: 80, textAlignVertical: 'top', paddingTop: 10 },
  actions: {
    flexDirection: 'row',
    marginTop: 20,
    gap: 12,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#C0D8D8',
    alignItems: 'center',
  },
  cancelText: { color: '#6A9999', fontWeight: '600', fontSize: 15 },
  saveBtn: {
    flex: 2,
    paddingVertical: 14,
    borderRadius: 12,
    backgroundColor: '#0D7377',
    alignItems: 'center',
  },
  saveText: { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
  disabled: { opacity: 0.45 },
});
