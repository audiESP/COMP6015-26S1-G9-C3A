import tw from '../ui/tw';
// src/components/PatientModal.tsx
import React, { useState, useEffect } from 'react';
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

  // `initial` can arrive after this component has already mounted with a
  // stale/default value (e.g. the visit's patient data resolves after the
  // modal's first render) — resync whenever it changes or the modal opens,
  // so `handleSave` never submits a previous patient's identity fields.
  useEffect(() => {
    if (visible) {
      setForm(initial ?? {});
    }
  }, [visible, initial]);

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
      pastMedicalHistory: form.pastMedicalHistory,
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
            {field('pastMedicalHistory', 'Past medical history', 'Type 2 diabetes; recurrent falls', true)}
            {field('notes', t('patient.notes'), 'Additional notes...', true)}
          </ScrollView>

          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.cancelBtn}
              onPress={onClose}
              activeOpacity={0.7}
              accessibilityRole="button"
            >
              <Text style={styles.cancelText}>{t('patient.cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.saveBtn, !form.name?.trim() && styles.disabled]}
              onPress={handleSave}
              activeOpacity={0.8}
              disabled={!form.name?.trim()}
              accessibilityRole="button"
            >
              <Text style={styles.saveText}>{t('patient.save')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
};

const styles = {
  overlay: tw.style('flex-1 justify-end', {"backgroundColor":"rgba(0,0,0,0.4)"}),
  sheet: tw.style('bg-[#FAFEFE] rounded-tl-[24px] rounded-tr-[24px] px-[20px] pb-[36px] max-h-[85%]'),
  handle: tw.style('w-[36px] h-[4px] bg-[#D1DFE0] rounded-[2px] self-center mt-[12px] mb-[16px]'),
  title: tw.style('text-[18px] font-semibold text-care-primary mb-[20px]'),
  field: tw.style('mb-[14px]'),
  label: tw.style('text-[12px] font-semibold text-[#6A9999] mb-[6px] tracking-[0.4px] uppercase'),
  input: tw.style('bg-white border-[1px] border-[#D8EAEA] rounded-[10px] px-[14px] py-[10px] text-[15px] text-care-ink'),
  multiline: tw.style('h-[80px] pt-[10px]', {"textAlignVertical":"top"}),
  actions: tw.style('flex-row mt-[20px] gap-[12px]'),
  cancelBtn: tw.style('flex-1 py-[14px] rounded-[12px] border-[1px] border-[#C0D8D8] items-center'),
  cancelText: tw.style('text-[#6A9999] font-semibold text-[15px]'),
  saveBtn: tw.style('py-[14px] rounded-[12px] bg-care-primary items-center', {"flex":2}),
  saveText: tw.style('text-white font-semibold text-[15px]'),
  disabled: tw.style('opacity-45'),
};
