import { ArrowLeftRight, Mic, RotateCw } from 'lucide-react-native';
import { Button, Copy, Field, Heading, IconButton, Notice, Sheet } from '../ui/primitives';
import tw from '../ui/tw';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import * as Speech from 'expo-speech';

import { RecordingPresets, requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder } from 'expo-audio';

import {
  Keyboard,
  KeyboardAvoidingView,
  Modal,
  Platform,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';


import { AttachmentMenu } from '../components/AttachmentMenu';

import { ChatBubble } from '../components/ChatBubble';

import { ChatInput } from '../components/ChatInput';

import { HistorySidebar } from '../components/HistorySidebar';

import { PatientModal } from '../components/PatientModal';

import { useChat } from '../hooks/useChat';

import '../i18n';

import { analyseRiskNote, fetchPatientSummary, generateVisitReport, setApiBaseUrl, transcribeSpeech, translateText } from '../services/api';

import type { PatientSummaryRecord } from '../services/api';

import { useChatStore } from '../store/chatStore';

import { useScenarioStore } from '../store/scenarioStore';

import {
  Attachment,
  AlertAction,
  CareTask,
  CareOutcomeFormAnswers,
  LocationSnapshot,
  MedicationSupportItem,
  MedicationSupportRecord,
  MedicationSupportStatus,
  Message,
  PatientInfo,
  RiskAlert,
  RiskSuggestion,
  TranslationResponse,
  ScenarioContext,
  VisitContext,
  VisitLifecycleStep,
  VisitQueueItem,
} from '../types';

import { formatDistance } from '../utils/location';


const emptyCareOutcomeForm: CareOutcomeFormAnswers = {
  overallCondition: '',
  conditionChanged: '',
  conditionChangeNotes: '',
  vitalsRequired: '',
  vitals: {
    bloodPressureSystolic: '',
    bloodPressureDiastolic: '',
    heartRate: '',
    temperature: '',
    oxygenSaturation: '',
    respiratoryRate: '',
    bloodGlucose: '',
    weight: '',
  },
  vitalsConcern: '',
  vitalsConcernNotes: '',
  tasksCompleted: '',
  incompleteReasons: [],
  incompleteOther: '',
  taskNotes: '',
  medicationRequired: '',
  medicationStatus: '',
  medicationConcern: '',
  medicationConcernNotes: '',
  wellbeingConcerns: [],
  wellbeingOther: '',
  observationNotes: '',
  followUpRequired: '',
  followUpDetails: '',
  overallOutcome: '',
  finalComments: '',
  confirmedAccurate: false,
};


function createEmptyCareOutcomeForm(): CareOutcomeFormAnswers {
  return { ...emptyCareOutcomeForm, vitals: { ...emptyCareOutcomeForm.vitals }, incompleteReasons: [], wellbeingConcerns: [] };
}


const overallConditionOptions = ['Stable', 'Improved', 'No significant change', 'Deteriorated', 'Unable to assess'];

const yesNoOptions = ['No', 'Yes'];

const vitalsRequiredOptions = ['Yes', 'No', 'Not required for this visit'];

const vitalsConcernOptions = ['No', 'Yes', 'Unsure'];

const tasksCompletedOptions = ['Yes', 'Partially completed', 'No'];

const incompleteReasonOptions = [
  'Patient declined',
  'Patient unavailable',
  'Task was no longer required',
  'Safety concern',
  'Insufficient time',
  'Required equipment/resources unavailable',
];

const medicationStatusOptions: MedicationSupportStatus[] = ['Completed', 'Delayed', 'Declined', 'Unavailable', 'Unable to Confirm'];

const wellbeingConcernOptions = [
  'No new concerns',
  'Pain or discomfort',
  'Mobility difficulty',
  'Eating or drinking concern',
  'Behaviour or mood change',
  'Skin or wound concern',
  'Breathing difficulty',
  'Confusion or cognitive change',
];

const followUpOptions = [
  'No follow-up required',
  'Routine follow-up required',
  'Supervisor review required',
  'Nurse/clinical review required',
  'Urgent escalation required',
];

const overallOutcomeOptions = [
  'Visit completed successfully',
  'Visit completed with minor issues',
  'Visit completed with concerns requiring follow-up',
  'Visit could not be fully completed',
  'Visit ended early',
];


function isCareOutcomeFormComplete(form: CareOutcomeFormAnswers) {
  const required =
    Boolean(form.overallCondition) &&
    Boolean(form.conditionChanged) &&
    Boolean(form.vitalsRequired) &&
    Boolean(form.tasksCompleted) &&
    Boolean(form.medicationRequired) &&
    form.wellbeingConcerns.length > 0 &&
    Boolean(form.followUpRequired) &&
    Boolean(form.overallOutcome) &&
    form.confirmedAccurate;

  if (!required) return false;
  if (form.conditionChanged === 'Yes' && !form.conditionChangeNotes.trim()) return false;
  if (form.tasksCompleted !== 'Yes' && form.incompleteReasons.length === 0 && !form.incompleteOther.trim()) return false;
  if (form.medicationRequired === 'Yes' && !form.medicationStatus) return false;
  if (form.medicationRequired === 'Yes' && form.medicationStatus && form.medicationStatus !== 'Completed' && !form.medicationConcernNotes.trim()) return false;
  if (form.medicationConcern === 'Yes' && !form.medicationConcernNotes.trim()) return false;
  if (form.wellbeingConcerns.includes('Other') && !form.wellbeingOther.trim()) return false;
  if (form.followUpRequired !== 'No follow-up required' && !form.followUpDetails.trim()) return false;
  return true;
}


function RiskReviewModal({
  visible,
  note,
  suggestions,
  loading,
  error,
  onChange,
  onAnalyse,
  onClose,
}: {
  visible: boolean;
  note: string;
  suggestions: RiskSuggestion[];
  loading: boolean;
  error: string | null;
  onChange: (value: string) => void;
  onAnalyse: () => void;
  onClose: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.finishModal}>
          <View style={styles.finishModalHeader}>
            <View style={styles.currentTaskCopy}>
              <Text style={styles.priorityLabel}>AI RISK REVIEW</Text>
              <Text style={styles.currentTaskTitle}>Review a care note</Text>
              <Text style={styles.currentTaskDetail}>
                AI suggestions require worker confirmation and do not create an official alert.
              </Text>
            </View>
            <TouchableOpacity style={styles.modalCloseButton} onPress={onClose} activeOpacity={0.75}>
              <Text style={styles.modalCloseText}>Close</Text>
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.finishFormScroll} contentContainerStyle={styles.finishFormContent}>
            <TextField label="Observation or care-worker note" value={note} onChange={onChange} />
            {error && <Text style={styles.errorText}>{error}</Text>}
            {suggestions.length === 0 && !loading && !error && (
              <Text style={styles.currentTaskDetail}>
                Enter a factual observation, such as a delayed medication, refusal, mobility concern, or communication barrier.
              </Text>
            )}
            {loading && <Text style={styles.currentTaskDetail}>Analysing the note...</Text>}
            {suggestions.map((suggestion) => (
              <View key={`${suggestion.riskType}-${suggestion.reason}`} style={styles.riskSuggestionCard}>
                <Text style={styles.priorityLabel}>{suggestion.level.toUpperCase()} SUGGESTION</Text>
                <Text style={styles.alertTitle}>{suggestion.riskType}</Text>
                <Text style={styles.alertMessage}>{suggestion.reason}</Text>
                {suggestion.recommendedActions.map((action) => (
                  <Text key={action} style={styles.suggestionAction}>• {action}</Text>
                ))}
                <Text style={styles.suggestionConfirmation}>Worker confirmation required</Text>
              </View>
            ))}
          </ScrollView>
          <View style={styles.finishModalFooter}>
            <ActionButton
              label={loading ? 'Analysing...' : 'Analyse note'}
              onPress={onAnalyse}
              disabled={!note.trim() || loading}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
}


function FinishVisitFormModal({
  visible,
  form,
  report,
  reportError,
  isGenerating,
  isSaving,
  canGenerate,
  onChange,
  onGenerate,
  onFinish,
  onClose,
}: {
  visible: boolean;
  form: CareOutcomeFormAnswers;
  report: string;
  reportError: string | null;
  isGenerating: boolean;
  isSaving: boolean;
  canGenerate: boolean;
  onChange: (form: CareOutcomeFormAnswers) => void;
  onGenerate: () => void;
  onFinish: () => void;
  onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const stepNames = ['Patient condition', 'Care and observations', 'Follow-up and outcome', 'Review report'];
  const update = (patch: Partial<CareOutcomeFormAnswers>) => onChange({ ...form, ...patch });
  const updateVitals = (key: string, value: string) => update({ vitals: { ...form.vitals, [key]: value } });
  const toggleList = (key: 'incompleteReasons' | 'wellbeingConcerns', value: string) => {
    const current = form[key];
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    update({ [key]: next } as Pick<CareOutcomeFormAnswers, typeof key>);
  };

  return <Sheet visible={visible} title={`Finish visit · ${step + 1} / 4`} onClose={onClose} busy={isGenerating || isSaving}
    footer={<View style={tw`gap-2`}>
      {step > 0 && <Button secondary label="Previous step" disabled={isGenerating || isSaving} onPress={() => setStep(step - 1)} />}
      {step < 3 ? <Button label="Continue" onPress={() => setStep(step + 1)} /> : <>
        {!canGenerate && <Notice text="Complete the required questions in the previous steps and confirm the record before generating your report." />}
        <Button label={isGenerating ? 'Generating report...' : report ? 'Regenerate report' : 'Generate visit report'} onPress={onGenerate} disabled={!canGenerate || isSaving} busy={isGenerating} />
        <Button label="Review and finish visit" secondary onPress={onFinish} disabled={!report || !canGenerate || isGenerating || isSaving} />
      </>}
    </View>}>
    <View style={tw`flex-row gap-1.5 mb-4`}>{stepNames.map((name, index) => <View key={name} style={tw.style('flex-1 h-1 rounded-full', index <= step ? 'bg-care-primary' : 'bg-care-line')} />)}</View>
    <View style={tw`mb-4`}><Heading>{stepNames[step]}</Heading></View>

            {step === 0 && (<FormSection title="1. Patient Condition">
              <SingleChoice label="How was the patient's overall condition during this visit? *" value={form.overallCondition} options={overallConditionOptions} onChange={(overallCondition) => update({ overallCondition })} />
              <SingleChoice label="Were there any noticeable changes in the patient's condition? *" value={form.conditionChanged} options={yesNoOptions} onChange={(conditionChanged) => update({ conditionChanged })} />
              {form.conditionChanged === 'Yes' && (
                <TextField label="If Yes, please describe *" value={form.conditionChangeNotes} onChange={(conditionChangeNotes) => update({ conditionChangeNotes })} />
              )}
            </FormSection>)}

            {step === 0 && (<FormSection title="2. Vital Signs">
              <SingleChoice label="Were vital signs required or taken during this visit? *" value={form.vitalsRequired} options={vitalsRequiredOptions} onChange={(vitalsRequired) => update({ vitalsRequired })} />
              {form.vitalsRequired === 'Yes' && (
                <View style={styles.vitalsGrid}>
                  <TextField compact label="BP systolic" value={form.vitals.bloodPressureSystolic} onChange={(value) => updateVitals('bloodPressureSystolic', value)} keyboardType="numeric" />
                  <TextField compact label="BP diastolic" value={form.vitals.bloodPressureDiastolic} onChange={(value) => updateVitals('bloodPressureDiastolic', value)} keyboardType="numeric" />
                  <TextField compact label="Heart rate bpm" value={form.vitals.heartRate} onChange={(value) => updateVitals('heartRate', value)} keyboardType="numeric" />
                  <TextField compact label="Temperature C" value={form.vitals.temperature} onChange={(value) => updateVitals('temperature', value)} keyboardType="numeric" />
                  <TextField compact label="Oxygen saturation %" value={form.vitals.oxygenSaturation} onChange={(value) => updateVitals('oxygenSaturation', value)} keyboardType="numeric" />
                  <TextField compact label="Respiratory rate" value={form.vitals.respiratoryRate} onChange={(value) => updateVitals('respiratoryRate', value)} keyboardType="numeric" />
                  <TextField compact label="Blood glucose mmol/L" value={form.vitals.bloodGlucose} onChange={(value) => updateVitals('bloodGlucose', value)} keyboardType="numeric" />
                  <TextField compact label="Weight kg" value={form.vitals.weight} onChange={(value) => updateVitals('weight', value)} keyboardType="numeric" />
                </View>
              )}
              <SingleChoice label="Were any recorded vital signs outside the patient's expected range?" value={form.vitalsConcern} options={vitalsConcernOptions} onChange={(vitalsConcern) => update({ vitalsConcern })} />
              {(form.vitalsConcern === 'Yes' || form.vitalsConcern === 'Unsure') && (
                <TextField label="Describe the vital-sign concern" value={form.vitalsConcernNotes} onChange={(vitalsConcernNotes) => update({ vitalsConcernNotes })} />
              )}
            </FormSection>)}

            {step === 1 && (<FormSection title="3. Care Task Outcomes">
              <SingleChoice label="Were all scheduled care tasks completed? *" value={form.tasksCompleted} options={tasksCompletedOptions} onChange={(tasksCompleted) => update({ tasksCompleted })} />
              {form.tasksCompleted && form.tasksCompleted !== 'Yes' && (
                <>
                  <MultiChoice label="If not all tasks were completed, select the reason *" values={form.incompleteReasons} options={incompleteReasonOptions} onToggle={(value) => toggleList('incompleteReasons', value)} />
                  <TextField label="Other reason" value={form.incompleteOther} onChange={(incompleteOther) => update({ incompleteOther })} />
                </>
              )}
              <TextField label="Additional care task notes" value={form.taskNotes} onChange={(taskNotes) => update({ taskNotes })} />
            </FormSection>)}

            {step === 1 && (<FormSection title="4. Medication Support Outcome">
              <SingleChoice label="Was medication support required during this visit? *" value={form.medicationRequired} options={yesNoOptions} onChange={(medicationRequired) => update({ medicationRequired })} />
              {form.medicationRequired === 'Yes' && (
                <SingleChoice label="Medication support status *" value={form.medicationStatus} options={medicationStatusOptions} onChange={(medicationStatus) => update({ medicationStatus })} />
              )}
              {form.medicationRequired === 'Yes' && form.medicationStatus && form.medicationStatus !== 'Completed' && (
                <TextField label="Notes or reason for medication support status *" value={form.medicationConcernNotes} onChange={(medicationConcernNotes) => update({ medicationConcernNotes })} />
              )}
              <SingleChoice label="Were there any medication-related concerns?" value={form.medicationConcern} options={yesNoOptions} onChange={(medicationConcern) => update({ medicationConcern })} />
              {form.medicationConcern === 'Yes' && (
                <TextField label="Describe the medication concern *" value={form.medicationConcernNotes} onChange={(medicationConcernNotes) => update({ medicationConcernNotes })} />
              )}
            </FormSection>)}

            {step === 1 && (<FormSection title="5. Patient Wellbeing and Observations">
              <MultiChoice label="Did you observe any new concerns during the visit? *" values={form.wellbeingConcerns} options={[...wellbeingConcernOptions, 'Other']} onToggle={(value) => toggleList('wellbeingConcerns', value)} />
              {form.wellbeingConcerns.includes('Other') && (
                <TextField label="Other concern *" value={form.wellbeingOther} onChange={(wellbeingOther) => update({ wellbeingOther })} />
              )}
              <TextField label="Observation notes" value={form.observationNotes} onChange={(observationNotes) => update({ observationNotes })} />
            </FormSection>)}

            {step === 2 && (<FormSection title="6. Follow-up Required">
              <SingleChoice label="Does this visit require follow-up action? *" value={form.followUpRequired} options={followUpOptions} onChange={(followUpRequired) => update({ followUpRequired })} />
              {form.followUpRequired && form.followUpRequired !== 'No follow-up required' && (
                <TextField label="Follow-up details *" value={form.followUpDetails} onChange={(followUpDetails) => update({ followUpDetails })} />
              )}
            </FormSection>)}

            {step === 2 && (<FormSection title="7. Overall Visit Outcome">
              <SingleChoice label="Select the overall outcome of this visit *" value={form.overallOutcome} options={overallOutcomeOptions} onChange={(overallOutcome) => update({ overallOutcome })} />
              <TextField label="Final HCW comments" value={form.finalComments} onChange={(finalComments) => update({ finalComments })} />
              <TouchableOpacity style={styles.confirmRow} onPress={() => update({ confirmedAccurate: !form.confirmedAccurate })} activeOpacity={0.75}>
                <View style={[styles.taskCheck, form.confirmedAccurate && styles.taskCheckDone]}>
                  <Text style={styles.taskCheckText}>{form.confirmedAccurate ? '✓' : ''}</Text>
                </View>
                <Text style={styles.confirmText}>I confirm the information recorded above is accurate to the best of my knowledge. *</Text>
              </TouchableOpacity>
            </FormSection>)}

            {step === 3 && (<View style={styles.reportPanel}>
              <Text style={styles.priorityLabel}>GENERATED VISIT REPORT</Text>
              {reportError && <Text style={styles.errorText}>{reportError}</Text>}
              {report ? (
                <Text style={styles.reportText}>{report}</Text>
              ) : (
                <Text style={styles.currentTaskDetail}>
                  The report will appear here after all required questions are complete and the local AI finishes generation.
                </Text>
              )}
            </View>)}
          
  </Sheet>;
}


function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.formSection}>
      <Text style={styles.formSectionTitle}>{title}</Text>
      {children}
    </View>
  );
}


function SingleChoice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.fieldBlock}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.choiceWrap}>
        {options.map((option) => (
          <TouchableOpacity
            key={option}
            style={[styles.choiceButton, value === option && styles.choiceButtonActive]}
            onPress={() => onChange(option)}
            activeOpacity={0.75}
          >
            <Text style={[styles.choiceText, value === option && styles.choiceTextActive]}>{option}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}


function MultiChoice({
  label,
  values,
  options,
  onToggle,
}: {
  label: string;
  values: string[];
  options: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <View style={styles.fieldBlock}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.choiceWrap}>
        {options.map((option) => {
          const active = values.includes(option);
          return (
            <TouchableOpacity
              key={option}
              style={[styles.choiceButton, active && styles.choiceButtonActive]}
              onPress={() => onToggle(option)}
              activeOpacity={0.75}
            >
              <Text style={[styles.choiceText, active && styles.choiceTextActive]}>{option}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}


function TextField({
  label,
  value,
  onChange,
  keyboardType = 'default',
  compact = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  keyboardType?: 'default' | 'numeric';
  compact?: boolean;
}) {
  return (
    <View style={[styles.fieldBlock, compact && styles.compactField]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={[styles.textInput, !compact && styles.textArea]}
        value={value}
        onChangeText={onChange}
        keyboardType={keyboardType}
        multiline={!compact}
        placeholder="Enter details"
        placeholderTextColor="#8A9B93"
      />
    </View>
  );
}


function LocationCheckCard({ visit }: { visit: VisitContext }) {
  const checkInWarning = visit.checkIn?.withinExpectedArea === false;
  const lowAccuracy =
    (visit.checkIn?.accuracyMeters ?? 0) > 100 ||
    (visit.checkOut?.accuracyMeters ?? 0) > 100;
  return (
    <View style={styles.locationCard}>
      <View style={styles.locationHeader}>
        <View style={styles.currentTaskCopy}>
          <Text style={styles.priorityLabel}>VISIT LOCATION</Text>
          <Text style={styles.currentTaskTitle}>Arrival and departure</Text>
          <Text style={styles.currentTaskDetail}>{visit.plannedAddress ?? visit.location}</Text>
        </View>
      </View>
      <View style={styles.locationSummaryGrid}>
        <LocationSnapshotLine label="Check-in" snapshot={visit.checkIn} />
        <LocationSnapshotLine label="Check-out" snapshot={visit.checkOut} />
      </View>
      {(checkInWarning || lowAccuracy) && (
        <Text style={styles.locationWarning}>
          {checkInWarning
            ? 'Outside expected area. Confirm address and document the reason if this is correct.'
            : 'Low GPS accuracy. Use manual confirmation if needed.'}
        </Text>
      )}
    </View>
  );
}


function LocationSnapshotLine({ label, snapshot }: { label: string; snapshot?: LocationSnapshot }) {
  const detail = snapshot
    ? `${snapshot.source === 'manual_override' ? 'Manual' : 'GPS'} · ${formatShortTime(snapshot.timestamp)} · ${formatDistance(snapshot.distanceFromPlannedMeters)}`
    : 'Not recorded';
  return (
    <View style={styles.locationMiniPanel}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{detail}</Text>
      {snapshot?.accuracyMeters !== undefined && (
        <Text style={styles.locationMeta}>Accuracy {Math.round(snapshot.accuracyMeters)} m</Text>
      )}
    </View>
  );
}


function ShiftSummary({ total, completed, followUps }: { total: number; completed: number; followUps: number }) {
  return (
    <View style={styles.reviewGate}>
      <Text style={styles.priorityLabel}>SHIFT SUMMARY</Text>
      <Text style={styles.currentTaskTitle}>{completed}/{total} visits completed</Text>
      <Text style={styles.currentTaskDetail}>
        {followUps > 0 ? `${followUps} visit(s) need follow-up or review attention.` : 'No follow-up visits are currently flagged.'}
      </Text>
    </View>
  );
}


type TranslationDirection = 'hcw_to_patient' | 'patient_to_hcw';

type VoiceStatus = 'idle' | 'recording' | 'reviewing' | 'translating' | 'speaking' | 'paused' | 'error';


// Keep this map deliberately small and explicit. We should never silently read a
// translation in an unrelated device voice when a patient's language is unknown.
const ttsLocales: Record<string, string> = {
  'english': 'en-AU',
  'english (australia)': 'en-AU',
  'mandarin': 'zh-CN',
  'mandarin chinese': 'zh-CN',
  'cantonese': 'yue-HK',
  'vietnamese': 'vi-VN',
  'arabic': 'ar-SA',
};


function localeForLanguage(language: string): string | null {
  return ttsLocales[language.trim().toLowerCase()] ?? null;
}


function isCompatibleVoice(voiceLanguage: string, locale: string): boolean {
  const normalisedVoiceLanguage = voiceLanguage.replace('_', '-').toLowerCase();
  const normalisedLocale = locale.toLowerCase();
  return (
    normalisedVoiceLanguage === normalisedLocale ||
    normalisedVoiceLanguage.split('-')[0] === normalisedLocale.split('-')[0]
  );
}


function TranslationTab({
  active = true,
  patientLanguage,
  workerLanguage,
  visitId,
}: {
  active?: boolean;
  patientLanguage: string;
  workerLanguage: string;
  visitId?: string;
}) {
  const [facingPatient, setFacingPatient] = useState(false);
  const [direction, setDirection] = useState<TranslationDirection>('hcw_to_patient');
  const [inputText, setInputText] = useState('');
  const [result, setResult] = useState<TranslationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle');
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const speechPressActive = useRef(false);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const requestSeq = useRef(0);
  const lastRequestedKey = useRef('');
  // expo-speech exposes stop rather than a native pause API. Its boundary events
  // let us resume from the word currently being spoken instead of replaying the
  // entire translation after a pause.
  const speechOffset = useRef(0);
  const speechPaused = useRef(false);

  const targetLanguage = direction === 'hcw_to_patient' ? patientLanguage : workerLanguage;
  const sourceLabel = direction === 'hcw_to_patient' ? workerLanguage : patientLanguage;
  const speakerLabel = direction === 'hcw_to_patient' ? 'Care worker speaks' : 'Patient speaks';
  const ttsLocale = localeForLanguage(targetLanguage);
  const commonPhrases = [
    'I am here for your scheduled care visit.',
    'Do you have any pain or discomfort today?',
    'I am going to help with your medication now.',
    'Please tell me if you feel dizzy or unwell.',
  ];

  const requestTranslation = useCallback(
    async (sourceText = inputText) => {
      const cleanText = sourceText.trim();
      if (!cleanText) {
        setResult(null);
        setError(null);
        return;
      }

      const requestKey = `${targetLanguage}|${cleanText}`;
      if (lastRequestedKey.current === requestKey) return;
      lastRequestedKey.current = requestKey;

      const seq = requestSeq.current + 1;
      requestSeq.current = seq;
      setIsTranslating(true);
      setVoiceStatus('translating');
      setError(null);

      try {
        const response = await translateText({
          text: cleanText,
          sourceLanguage: sourceLabel,
          targetLanguage,
        });
        if (requestSeq.current === seq) {
          setResult(response);
          setVoiceStatus('idle');
        }
      } catch (err) {
        if (requestSeq.current === seq) {
          setError(err instanceof Error ? err.message : 'Translation failed.');
          setVoiceStatus('reviewing');
        }
      } finally {
        if (requestSeq.current === seq) {
          setIsTranslating(false);
        }
      }
    },
    [inputText, targetLanguage, sourceLabel],
  );

  useEffect(() => () => {
    speechPaused.current = false;
    void Speech.stop();
  }, []);

  const invalidateTranslation = useCallback(() => {
    requestSeq.current += 1;
    lastRequestedKey.current = '';
    setResult(null);
    setError(null);
    setIsTranslating(false);
  }, []);

  const handleDirectionChange = (nextDirection: TranslationDirection) => {
    if (nextDirection === direction) return;
    void Speech.stop();
    speechPressActive.current = false;
    if (recorder.isRecording) {
      void recorder.stop().catch(() => undefined).then(() => setAudioModeAsync({ allowsRecording: false }));
    }
    invalidateTranslation();
    setInputText('');
    setVoiceStatus('idle');
    setVoiceNotice(null);
    setDirection(nextDirection);
  };

  const handleInputChange = (nextText: string) => {
    invalidateTranslation();
    setInputText(nextText);
    setVoiceStatus(nextText.trim() ? 'reviewing' : 'idle');
    setVoiceNotice(null);
  };

  const handlePhrase = (phrase: string) => {
    if (direction !== 'hcw_to_patient') handleDirectionChange('hcw_to_patient');
    handleInputChange(phrase);
  };

  const handleClear = () => {
    void Speech.stop();
    speechPressActive.current = false;
    if (recorder.isRecording) {
      void recorder.stop().catch(() => undefined).then(() => setAudioModeAsync({ allowsRecording: false }));
    }
    invalidateTranslation();
    setInputText('');
    setVoiceStatus('idle');
    setVoiceNotice(null);
  };

  useEffect(() => {
    if (!active) {
      speechPressActive.current = false;
      requestSeq.current += 1;
      lastRequestedKey.current = '';
      setIsTranslating(false);
      void Speech.stop();
      if (recorder.isRecording) void recorder.stop().catch(() => undefined).then(() => setAudioModeAsync({ allowsRecording: false }));
      setVoiceStatus('idle');
    }
  }, [active]);

  const handleSpeechUiPress = async () => {
    if (!active || isTranslating || recorder.isRecording) return;
    speechPressActive.current = true;
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) throw new Error('Microphone permission is required to transcribe speech.');
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      if (!speechPressActive.current) {
        await setAudioModeAsync({ allowsRecording: false });
        return;
      }
      recorder.record();
      setVoiceStatus('recording');
      setVoiceNotice('Recording… release to stop and transcribe.');
    } catch (err) {
      setVoiceStatus('error');
      setVoiceNotice(err instanceof Error ? err.message : 'Unable to start recording.');
    }
  };

  const handleSpeechUiRelease = async () => {
    speechPressActive.current = false;
    if (!recorder.isRecording) return;
    const transcriptionSeq = ++requestSeq.current;
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false });
      const uri = recorder.uri;
      if (!uri) throw new Error('Recording was unavailable.');
      setVoiceStatus('translating');
      setVoiceNotice('Transcribing speech…');
      const response = await transcribeSpeech(uri, sourceLabel, direction === 'hcw_to_patient' ? 'care_worker' : 'patient', visitId);
      if (transcriptionSeq !== requestSeq.current) return;
      invalidateTranslation();
      setInputText(response.transcript);
      setVoiceStatus('reviewing');
      setVoiceNotice('Review or edit the transcript, then select Confirm & translate.');
    } catch (err) {
      setVoiceStatus('error');
      setVoiceNotice(err instanceof Error ? err.message : 'Speech transcription failed. Please try again.');
    }
  };

  const resetSpeechPosition = () => {
    speechPaused.current = false;
    speechOffset.current = 0;
  };

  const playTranslation = async (startOffset: number) => {
    if (!result?.translatedText.trim()) return;
    if (!ttsLocale) {
      setVoiceStatus('error');
      setVoiceNotice(`A compatible voice has not been configured for ${targetLanguage}. The translation remains available as text.`);
      return;
    }

    try {
      const voices = await Speech.getAvailableVoicesAsync();
      const voice = voices.find((candidate) => isCompatibleVoice(candidate.language, ttsLocale));
      if (!voice) {
        setVoiceStatus('error');
        setVoiceNotice(`No ${targetLanguage} voice is installed on this device. Install a compatible ${ttsLocale} voice to play the translation.`);
        return;
      }

      await Speech.stop();
      const text = result.translatedText;
      const boundedStartOffset = Math.min(Math.max(startOffset, 0), text.length);
      speechOffset.current = boundedStartOffset;
      speechPaused.current = false;
      setVoiceNotice(null);
      Speech.speak(text.slice(boundedStartOffset), {
        language: ttsLocale,
        voice: voice.identifier,
        rate: 0.9,
        onStart: () => setVoiceStatus('speaking'),
        onBoundary: ({ charIndex }: { charIndex: number }) => {
          speechOffset.current = boundedStartOffset + charIndex;
        },
        onDone: () => {
          speechPaused.current = false;
          speechOffset.current = text.length;
          setVoiceStatus('idle');
        },
        onStopped: () => setVoiceStatus(speechPaused.current ? 'paused' : 'idle'),
        onError: () => {
          speechPaused.current = false;
          setVoiceStatus('error');
          setVoiceNotice('The device could not play this translation. The translated text is still available to read.');
        },
      });
    } catch {
      setVoiceStatus('error');
      setVoiceNotice('Unable to check voices installed on this device. The translated text is still available to read.');
    }
  };

  const handlePause = () => {
    speechPaused.current = true;
    void Speech.stop();
    setVoiceStatus('paused');
  };

  const handlePlay = () => {
    void playTranslation(speechPaused.current ? speechOffset.current : 0);
  };

  const handleReplay = () => {
    resetSpeechPosition();
    void playTranslation(0);
  };

  return <View>
    <View style={tw`bg-white rounded-card p-4 flex-row items-center justify-between mb-4`}>
      <View style={tw`flex-1`}><Copy small muted>{direction === 'hcw_to_patient' ? 'Care worker' : 'Patient'}</Copy><Heading>{sourceLabel}</Heading></View>
      <IconButton icon={ArrowLeftRight} label="Swap translation direction" disabled={isTranslating || voiceStatus === 'recording'} onPress={() => handleDirectionChange(direction === 'hcw_to_patient' ? 'patient_to_hcw' : 'hcw_to_patient')} />
      <View style={tw`flex-1 items-end`}><Copy small muted>{direction === 'hcw_to_patient' ? 'Patient' : 'Care worker'}</Copy><Heading>{targetLanguage}</Heading></View>
    </View>
    <Field label="Review the original text" value={inputText} onChangeText={handleInputChange} multiline placeholder="Type a phrase, or hold the microphone to speak." editable={voiceStatus !== 'recording' && !isTranslating} />
    <TouchableOpacity accessibilityRole="button" accessibilityLabel="Hold to speak" disabled={isTranslating} onPressIn={handleSpeechUiPress} onPressOut={handleSpeechUiRelease} style={tw.style('min-h-[60px] flex-row gap-3 items-center justify-center rounded-card mb-2', voiceStatus === 'recording' ? 'bg-care-danger' : 'bg-care-primary')}>
      <Mic size={22} color="white" /><Text style={tw`text-white font-semibold`}>{voiceStatus === 'recording' ? 'Release to transcribe' : 'Hold to speak'}</Text>
    </TouchableOpacity>
    <Copy muted small>Release to transcribe. Check the text before translating.</Copy>
    <View style={tw`mt-4 gap-2`}><Button label="Confirm and translate" busy={isTranslating} disabled={!inputText.trim() || voiceStatus === 'recording'} onPress={() => { lastRequestedKey.current = ''; void requestTranslation(inputText); }} /><Button secondary label="Clear" disabled={isTranslating} onPress={handleClear} /></View>
    {result && <View style={tw`bg-care-soft rounded-hero p-5 mt-5`}>
      <View style={tw`flex-row items-center justify-between`}><Copy muted small>{targetLanguage}</Copy><IconButton icon={RotateCw} label="Turn the translation towards the patient" onPress={() => setFacingPatient(!facingPatient)} /></View>
      <Text selectable style={[tw`text-[26px] leading-9 text-care-ink my-5`, facingPatient && { transform: [{ rotate: '180deg' }] }]}>{result.translatedText}</Text>
      <Button secondary label={voiceStatus === 'speaking' ? 'Pause speech' : voiceStatus === 'paused' ? 'Resume speech' : 'Play translation'} onPress={voiceStatus === 'speaking' ? handlePause : handlePlay} />
    </View>}
    <View style={tw`mt-3`}><Notice text={voiceNotice} /><Notice error text={error} /></View>
    <View style={tw`mt-5 gap-2`}><Heading>Common phrases</Heading>{commonPhrases.map(phrase => <Button key={phrase} secondary label={phrase} onPress={() => handlePhrase(phrase)} disabled={isTranslating || voiceStatus === 'recording'} />)}</View>
  </View>;
}


function PatientDetailsPanel({
  patient,
  worker,
  location,
  alerts,
  summary,
  summaryRecords,
  summaryLoading,
  summaryError,
  disabled,
  onAlertAction,
}: {
  patient: PatientInfo;
  worker: string;
  location: string;
  alerts: RiskAlert[];
  summary: string;
  summaryRecords: PatientSummaryRecord[];
  summaryLoading: boolean;
  summaryError: string | null;
  disabled: boolean;
  onAlertAction: (alertId: string, action: AlertAction, note?: string) => Promise<ScenarioContext>;
}) {
  const openAlerts = alerts.filter((alert) => !alert.status || alert.status === 'active' || alert.status === 'acknowledged');
  const closedAlerts = alerts.filter((alert) => alert.status === 'resolved' || alert.status === 'dismissed');
  return (
    <View style={styles.tabPanel}>
      <SectionHeader title="AI patient summary" detail="From clinical records" />
      <View style={styles.contextPanel}>
        {summaryLoading ? (
          <Text style={styles.summaryStatusText}>Generating patient summary…</Text>
        ) : summaryError ? (
          <Text style={styles.summaryStatusText}>Summary unavailable right now.</Text>
        ) : summary ? (
          <Text style={styles.summaryBody}>{summary}</Text>
        ) : (
          <Text style={styles.summaryStatusText}>No summary available for this patient.</Text>
        )}
      </View>

      {!summaryLoading && !summaryError && summaryRecords.length > 0 && (
        <SummarySources records={summaryRecords} />
      )}

      <SectionHeader title="Must know" detail="Care preferences" />
      <View style={styles.contextPanel}>
        <SummaryLine label="Language" value={`${patient.preferredLanguage ?? 'Unknown'}${patient.interpreterRequired ? ' · interpreter recommended' : ''}`} />
        <SummaryLine label="Mobility" value={patient.mobilitySupport ?? 'Not recorded'} />
        <SummaryLine label="Communication" value={patient.communicationNotes ?? 'Not recorded'} />
        <SummaryLine label="Dietary" value={patient.dietaryNotes ?? 'Not recorded'} />
        <View style={styles.flagRow}>
          {(patient.careRiskFlags?.length ? patient.careRiskFlags : ['No risk flags recorded']).map((flag) => (
            <View key={flag} style={styles.flagChip}>
              <Text style={styles.flagText}>{flag}</Text>
            </View>
          ))}
        </View>
      </View>

      <SectionHeader title="Clinical context" detail="Patient details" />
      <View style={styles.contextPanel}>
        <SummaryLine label="Diagnosis" value={patient.diagnosis ?? 'Not recorded'} />
        <SummaryLine label="History" value={patient.pastMedicalHistory ?? 'Not recorded'} />
        <SummaryLine label="Cognition" value={patient.cognitiveStatus ?? 'Not recorded'} />
        <SummaryLine label="Culture" value={patient.culturalBackground ?? 'Not recorded'} />
        <SummaryLine label="Allergies" value={patient.allergies?.length ? patient.allergies.join(', ') : 'Not recorded'} />
        <SummaryLine label="Medications" value={patient.medications?.length ? patient.medications.join(', ') : 'Not recorded'} />
        <SummaryLine label="Notes" value={patient.notes ?? 'Not recorded'} />
      </View>

      <SectionHeader title="Things to watch" detail={`${openAlerts.length} open`} />
      <View style={styles.alertStack}>
        {openAlerts.length === 0 ? (
          <Text style={styles.emptyTimeline}>Nothing urgent is flagged right now.</Text>
        ) : (
          openAlerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              disabled={disabled}
              onAction={onAlertAction}
            />
          ))
        )}
      </View>

      <SectionHeader title="Alert history" detail={`${closedAlerts.length} closed`} />
      <View style={styles.alertStack}>
        {closedAlerts.length === 0 ? (
          <Text style={styles.emptyTimeline}>No resolved or dismissed alerts.</Text>
        ) : (
          closedAlerts.map((alert) => <AlertCard key={alert.id} alert={alert} disabled />)
        )}
      </View>

      <SectionHeader title="Assignment" detail="Visit owner" />
      <View style={styles.contextPanel}>
        <SummaryLine label="Worker" value={worker} />
        <SummaryLine label="Visit" value={location} />
      </View>
    </View>
  );
}


const summarySourceCategoryMeta: Record<string, { title: string }> = {
  patient: { title: 'Patient record' },
  cald_profile: { title: 'CALD profile' },
  condition: { title: 'Conditions' },
  medication: { title: 'Medication records' },
  allergy: { title: 'Allergies' },
  progress_note: { title: 'Progress notes / encounters' },
  observation: { title: 'Observations' },
};


function SummarySources({ records }: { records: PatientSummaryRecord[] }) {
  const [expanded, setExpanded] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => {
    const byCategory = new Map<string, PatientSummaryRecord[]>();
    for (const record of records) {
      const list = byCategory.get(record.category) ?? [];
      list.push(record);
      byCategory.set(record.category, list);
    }
    return Array.from(byCategory.entries());
  }, [records]);

  const toggleGroup = (category: string) => {
    setOpenGroups((current) => ({ ...current, [category]: !current[category] }));
  };

  return (
    <View style={styles.sourcesPanel}>
      <TouchableOpacity
        style={styles.sourcesHeader}
        onPress={() => setExpanded((current) => !current)}
        accessibilityRole="button"
      >
        <View style={styles.sourcesHeaderText}>
          <Text style={styles.sourcesTitle}>Sources used for this summary</Text>
          <Text style={styles.sourcesSubtitle}>
            {records.length} record{records.length === 1 ? '' : 's'} the AI referenced from the patient dataset.
          </Text>
        </View>
        <Text style={styles.sourcesChevron}>{expanded ? '▲' : '▼'}</Text>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.sourcesBody}>
          {groups.map(([category, items]) => {
            const isOpen = !!openGroups[category];
            return (
              <View key={category} style={styles.sourcesGroup}>
                <TouchableOpacity
                  style={styles.sourcesGroupHeader}
                  onPress={() => toggleGroup(category)}
                  accessibilityRole="button"
                >
                  <Text style={styles.sourcesGroupTitle}>
                    {summarySourceCategoryMeta[category]?.title ?? category} ({items.length})
                  </Text>
                  <Text style={styles.sourcesChevron}>{isOpen ? '▲' : '▼'}</Text>
                </TouchableOpacity>
                {isOpen && items.map((item, index) => (
                  <View key={`${item.label}-${index}`} style={styles.sourceItem}>
                    <Text style={styles.sourceLabel}>{item.label}</Text>
                    {item.detail ? <Text style={styles.sourceDetail}>{item.detail}</Text> : null}
                  </View>
                ))}
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}


function VisitSummaryPanel({
  status,
  lifecycle,
  completed,
  followUp,
  visit,
  shiftSummaryOpen,
  totalVisits,
  completedVisits,
  followUpCount,
}: {
  status: string;
  lifecycle: string;
  completed: string;
  followUp: string;
  visit: VisitContext;
  shiftSummaryOpen: boolean;
  totalVisits: number;
  completedVisits: number;
  followUpCount: number;
}) {
  return (
    <View style={styles.tabPanel}>
      <SectionHeader title="Visit record" detail="Status and location" />
      <View style={styles.summaryPanel}>
        <SummaryLine label="Visit" value={status} />
        <SummaryLine label="Stage" value={lifecycle} />
        <SummaryLine label="Progress" value={completed} />
        <SummaryLine label="Follow-up" value={followUp} />
        <SummaryLine label="Check-in" value={visit.checkIn ? locationSnapshotSummary(visit.checkIn) : 'Not recorded'} />
        <SummaryLine label="Check-out" value={visit.checkOut ? locationSnapshotSummary(visit.checkOut) : 'Not recorded'} />
      </View>

      <LocationCheckCard visit={visit} />

      {shiftSummaryOpen && (
        <ShiftSummary
          total={totalVisits}
          completed={completedVisits}
          followUps={followUpCount}
        />
      )}
    </View>
  );
}


function SectionHeader({ title, detail }: { title: string; detail: string }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={styles.sectionDetail}>{detail}</Text>
    </View>
  );
}


function AlertCard({
  alert,
  disabled = false,
  onAction,
}: {
  alert: RiskAlert;
  disabled?: boolean;
  onAction?: (alertId: string, action: AlertAction, note?: string) => Promise<ScenarioContext>;
}) {
  const [note, setNote] = useState(alert.reviewNote ?? '');
  const isOpen = !alert.status || alert.status === 'active' || alert.status === 'acknowledged';
  const status = alert.status ?? 'active';
  const actionDate = alert.resolvedAt ?? alert.dismissedAt ?? alert.acknowledgedAt ?? alert.createdAt;
  const actionWorker = alert.resolvedByWorkerId ?? alert.dismissedByWorkerId ?? alert.acknowledgedByWorkerId;
  const detailEntries = Object.entries(alert.details ?? {}).filter(
    ([key, value]) => key !== 'triggered_by' && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'),
  );
  return (
    <View style={[styles.alertCard, alertTone(alert.level)]}>
      <View style={styles.alertHeaderRow}>
        <Text style={styles.alertTitle}>{alert.title}</Text>
        <Text style={styles.alertStatus}>{status.toUpperCase()}</Text>
      </View>
      <Text style={styles.alertMessage}>{alert.message}</Text>
      <Text style={styles.alertMeta}>
        {(alert.riskType ?? 'risk').replace(/_/g, ' ')}
        {actionDate ? ` · ${formatSavedDateTime(actionDate)}` : ''}
        {actionWorker ? ` · ${actionWorker}` : ''}
      </Text>
      {detailEntries.length > 0 && (
        <Text style={styles.alertDetails}>
          {detailEntries.map(([key, value]) => `${key.replace(/_/g, ' ')}: ${String(value)}`).join(' · ')}
        </Text>
      )}
      {alert.reviewNote && <Text style={styles.alertReviewNote}>Note: {alert.reviewNote}</Text>}
      {isOpen && onAction && (
        <>
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="Optional review note"
            placeholderTextColor="#7A8B83"
            style={styles.alertNoteInput}
            editable={!disabled}
          />
          <View style={styles.alertActions}>
            {status === 'active' && (
              <ActionButton label="Review" tone="muted" onPress={() => onAction(alert.id, 'acknowledge', note)} disabled={disabled} />
            )}
            <ActionButton label="Resolve" tone="success" onPress={() => onAction(alert.id, 'resolve', note)} disabled={disabled} />
            <ActionButton label="Dismiss" tone="warn" onPress={() => onAction(alert.id, 'dismiss', note)} disabled={disabled} />
          </View>
        </>
      )}
    </View>
  );
}


function ActionButton({
  label,
  tone = 'default',
  onPress,
  disabled = false,
}: {
  label: string;
  tone?: 'default' | 'warn' | 'danger' | 'success' | 'muted';
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <TouchableOpacity
      style={[styles.actionButton, actionTone(tone), disabled && styles.actionDisabled]}
      onPress={onPress}
      activeOpacity={0.75}
      disabled={disabled}
    >
      <Text style={[styles.actionText, disabled && styles.actionTextDisabled]}>{label}</Text>
    </TouchableOpacity>
  );
}


function SummaryLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.summaryLine}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue}>{value}</Text>
    </View>
  );
}


function formatShortTime(raw: string) {
  return new Date(raw).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}


function formatSavedDateTime(raw: string) {
  const date = new Date(raw);
  const pad = (value: number) => value.toString().padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}


function locationSnapshotSummary(snapshot: LocationSnapshot) {
  const source = snapshot.source === 'manual_override' ? 'manual confirmation' : 'GPS';
  const distance = snapshot.distanceFromPlannedMeters !== undefined
    ? `, ${formatDistance(snapshot.distanceFromPlannedMeters)} from planned location`
    : '';
  const status = snapshot.withinExpectedArea === false ? ', outside expected area' : '';
  return `${source} at ${formatShortTime(snapshot.timestamp)}${distance}${status}`;
}


function alertTone(level: RiskAlert['level']) {
  if (level === 'high') return styles.alertHigh;
  if (level === 'moderate') return styles.alertModerate;
  return styles.alertLow;
}


function actionTone(tone: 'default' | 'warn' | 'danger' | 'success' | 'muted') {
  if (tone === 'danger') return styles.actionDanger;
  if (tone === 'warn') return styles.actionWarn;
  if (tone === 'success') return styles.actionSuccess;
  if (tone === 'muted') return styles.actionMuted;
  return styles.actionDefault;
}


const styles = {
  safe: tw.style('flex-1 bg-care-canvas'),
  flex: tw.style('flex-1'),
  content: tw.style('p-[14px] pb-[18px]'),
  header: tw.style('flex-row items-center gap-[10px] mb-[12px]'),
  iconButton: tw.style('w-[40px] h-[40px] rounded-[20px] bg-white border-[1px] border-care-line items-center justify-center'),
  iconButtonText: tw.style('text-care-primary text-[18px] font-semibold'),
  headerCopy: tw.style('flex-1'),
  kicker: tw.style('text-care-muted text-[12px] font-semibold uppercase'),
  title: tw.style('text-care-ink text-[24px] font-semibold mt-[2px]'),
  statusPill: tw.style('px-[12px] py-[8px] rounded-[20px]'),
  statusText: tw.style('text-white font-semibold text-[12px]'),
  statusDefault: tw.style('bg-care-primary'),
  statusWarn: tw.style('bg-care-amber'),
  statusIncident: tw.style('bg-care-danger'),
  statusDone: tw.style('bg-[#2F7D46]'),
  visitPanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[14px]'),
  visitTopRow: tw.style('flex-row justify-between gap-[12px]'),
  patientBlock: tw.style('flex-1'),
  patientName: tw.style('text-care-ink text-[22px] font-semibold'),
  patientMeta: tw.style('text-care-muted text-[13px] mt-[4px]'),
  scheduleBlock: tw.style('items-end'),
  scheduleTime: tw.style('text-care-primary text-[24px] font-semibold'),
  scheduleLabel: tw.style('text-care-muted text-[12px]'),
  compactInfoRow: tw.style('flex-row gap-[8px] mt-[12px]'),
  compactInfo: tw.style('flex-1 bg-care-soft rounded-[20px] p-[10px]'),
  infoLabel: tw.style('text-care-muted text-[12px] font-semibold uppercase'),
  infoValue: tw.style('text-care-ink text-[13px] font-semibold mt-[4px]'),
  priorityAlert: tw.style('rounded-[20px] border-l-[5px] p-[12px] mt-[12px] gap-[6px]'),
  priorityLabel: tw.style('text-care-muted text-[12px] font-semibold uppercase'),
  currentTaskCard: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] mt-[12px] flex-row items-center gap-[12px]'),
  currentTaskCopy: tw.style('flex-1'),
  currentTaskTitle: tw.style('text-care-ink text-[17px] font-semibold mt-[4px]'),
  currentTaskDetail: tw.style('text-care-muted text-[12px] leading-[18px] mt-[4px]'),
  locationCard: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] mt-[12px]'),
  locationHeader: tw.style('flex-row items-center gap-[10px]'),
  locationSummaryGrid: tw.style('flex-row gap-[8px] mt-[10px]'),
  locationMiniPanel: tw.style('flex-1 bg-care-soft rounded-[20px] p-[10px]'),
  locationMeta: tw.style('text-care-muted text-[12px] mt-[4px]'),
  locationWarning: tw.style('text-care-amber text-[12px] font-semibold leading-[17px] mt-[8px]'),
  actionHint: tw.style('text-care-muted text-[12px] mt-[10px]'),
  quickActionBar: tw.style('flex-row gap-[8px] mt-[12px]'),
  issueGrid: tw.style('flex-row flex-wrap gap-[8px] mt-[8px]'),
  workflowPanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] mt-[12px]'),
  singleActionRow: tw.style('mt-[12px]'),
  inlineLocationStatus: tw.style('bg-care-soft rounded-[20px] p-[10px] mt-[10px]'),
  inlineLocationLabel: tw.style('text-care-muted text-[12px] font-semibold uppercase'),
  inlineLocationValue: tw.style('text-care-ink text-[12px] font-semibold mt-[4px] leading-[17px]'),
  finishBox: tw.style('bg-care-soft rounded-[20px] mt-[12px] p-[10px] flex-row items-center gap-[10px]'),
  finishCopy: tw.style('flex-1'),
  finishText: tw.style('text-[#3D4E47] text-[13px] font-semibold'),
  finishHint: tw.style('text-care-muted text-[12px] font-semibold mt-[3px] leading-[15px]'),
  finishButton: tw.style('bg-[#2F7D46] rounded-[20px] px-[12px] py-[9px]'),
  finishButtonDisabled: tw.style('bg-[#9BA9A2]'),
  finishButtonText: tw.style('text-white font-semibold text-[12px]'),
  reviewGate: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] mt-[12px]'),
  tabBar: tw.style('flex-row bg-care-soft rounded-[20px] p-[3px] mt-[16px]'),
  tabButton: tw.style('flex-1 min-h-[38px] items-center justify-center rounded-[6px]'),
  tabButtonActive: tw.style('bg-white'),
  tabText: tw.style('text-care-muted text-[12px] font-semibold'),
  tabTextActive: tw.style('text-care-primary'),
  tabPanel: tw.style('mt-[12px]'),
  sectionHeader: tw.style('flex-row justify-between items-end mb-[8px] gap-[12px]'),
  sectionHeaderCompact: tw.style('flex-row justify-between items-center gap-[12px]'),
  sectionTitle: tw.style('text-care-ink text-[17px] font-semibold'),
  sectionDetail: tw.style('text-care-muted text-[12px] text-right', {"flexShrink":1}),
  contextPanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line px-[12px]'),
  flagRow: tw.style('flex-row flex-wrap gap-[6px] py-[12px]'),
  flagChip: tw.style('bg-[#E6EFEA] rounded-[6px] px-[8px] py-[4px]'),
  flagText: tw.style('text-care-primary text-[12px] font-semibold'),
  medicationPanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] gap-[10px] mb-[12px]'),
  medicationList: tw.style('flex-row flex-wrap gap-[6px]'),
  medicationChip: tw.style('bg-[#EEF7F1] rounded-[6px] px-[8px] py-[5px]'),
  medicationChipText: tw.style('text-[#2D6A4F] text-[12px] font-semibold'),
  medicationItemList: tw.style('gap-[8px]'),
  medicationItemRow: tw.style('bg-care-canvas rounded-[20px] border-[1px] border-care-line p-[10px] gap-[8px]'),
  medicationName: tw.style('text-care-ink text-[13px] font-semibold leading-[18px]'),
  medicationTakenOptions: tw.style('flex-row flex-wrap gap-[6px]'),
  medicationTakenButton: tw.style('rounded-[7px] border-[1px] border-[#C9D7D1] bg-white px-[9px] py-[7px]'),
  medicationTakenButtonActive: tw.style('bg-care-primary border-care-primary'),
  medicationTakenText: tw.style('text-[#3D4E47] text-[12px] font-semibold'),
  medicationTakenTextActive: tw.style('text-white'),
  medicationTakenAt: tw.style('text-[#2F7D46] text-[12px] font-semibold leading-[17px]'),
  alertStack: tw.style('gap-[8px]'),
  alertCard: tw.style('rounded-[20px] border-l-[5px] p-[12px] bg-white'),
  alertHigh: tw.style('bg-[#FFF5F3]', {"borderLeftColor":"#A83B32"}),
  alertModerate: tw.style('bg-[#FFF9EC]', {"borderLeftColor":"#B27A1A"}),
  alertLow: tw.style('bg-[#F0F8F7]', {"borderLeftColor":"#2E6F73"}),
  alertHeaderRow: tw.style('flex-row items-start justify-between gap-[10px]'),
  alertTitle: tw.style('text-care-ink text-[14px] font-semibold flex-1'),
  alertStatus: tw.style('text-care-muted text-[12px] font-semibold', {"flexShrink":0}),
  alertMessage: tw.style('text-[#3D4E47] text-[13px] leading-[19px] mt-[4px]'),
  alertMeta: tw.style('text-care-muted text-[12px] font-semibold mt-[7px]'),
  alertDetails: tw.style('text-[#3D4E47] text-[12px] leading-[16px] mt-[5px]'),
  alertReviewNote: tw.style('text-[#3D4E47] text-[12px] leading-[17px] mt-[6px]'),
  alertNoteInput: tw.style('bg-white border-[1px] border-[#C9D7D1] rounded-[7px] text-care-ink text-[12px] mt-[9px] px-[9px] py-[8px]'),
  alertActions: tw.style('flex-row gap-[7px] mt-[8px]'),
  riskSuggestionCard: tw.style('rounded-[20px] border-[1px] border-[#D6E5DF] bg-[#F4FAF7] p-[12px] mt-[10px]'),
  suggestionAction: tw.style('text-[#3D4E47] text-[13px] leading-[19px] mt-[5px]'),
  suggestionConfirmation: tw.style('text-care-primary text-[12px] font-semibold mt-[9px]'),
  taskList: tw.style('bg-white rounded-[20px] border-[1px] border-care-line overflow-hidden mb-[12px]'),
  taskListInline: tw.style('bg-white rounded-[20px] border-[1px] border-care-line overflow-hidden mt-[12px]'),
  taskRowContainer: tw.style('border-b-[0.5px] border-b-care-line'),
  taskRowSelected: tw.style('bg-[#EEF7F1] border-b-[#2D6A4F]'),
  taskRow: tw.style('flex-row items-center gap-[10px] p-[12px]'),
  taskRowDisabled: tw.style('opacity-62'),
  taskContentButton: tw.style('flex-1 flex-row items-center mr-[8px]'),
  taskCheck: tw.style('w-[24px] h-[24px] rounded-[6px] border-[1px] border-[#B8C9C1] items-center justify-center'),
  taskCheckDone: tw.style('bg-[#2F7D46] border-[#2F7D46]'),
  taskCheckIssue: tw.style('bg-care-danger border-care-danger'),
  taskCheckText: tw.style('text-white font-semibold'),
  taskCopy: tw.style('flex-1'),
  taskLabel: tw.style('text-care-ink text-[14px] font-semibold'),
  taskDetail: tw.style('text-care-muted text-[12px] leading-[17px] mt-[2px]'),
  taskProblemText: tw.style('text-care-danger text-[12px] font-semibold mt-[4px]'),
  taskButtons: tw.style('w-[92px] gap-[6px]'),
  taskActionButton: tw.style('bg-[#2F7D46] rounded-[7px] py-[7px] items-center'),
  taskActionButtonDone: tw.style('bg-[#2F7D46]'),
  taskProblemButton: tw.style('bg-care-amber'),
  taskActionButtonDisabled: tw.style('bg-[#D6DED9]'),
  taskActionText: tw.style('text-white text-[12px] font-semibold'),
  taskActionTextDisabled: tw.style('text-[#7A8B83]'),
  taskIssueMenu: tw.style('flex-row gap-[8px] px-[12px] pb-[12px]'),
  actionButton: tw.style('flex-1 rounded-[20px] py-[12px] px-[10px]'),
  actionDefault: tw.style('bg-care-primary'),
  actionWarn: tw.style('bg-care-amber'),
  actionDanger: tw.style('bg-care-danger'),
  actionSuccess: tw.style('bg-[#2F7D46]'),
  actionMuted: tw.style('bg-[#4F625A]'),
  actionDisabled: tw.style('bg-[#D6DED9]'),
  actionText: tw.style('text-white text-[13px] font-semibold text-center'),
  actionTextDisabled: tw.style('text-[#7A8B83]'),
  assistantToolbar: tw.style('gap-[8px] mb-[10px]'),
  contextBadge: tw.style('bg-[#E6EFEA] rounded-[20px] p-[10px]'),
  contextBadgeText: tw.style('text-care-primary text-[12px] font-semibold'),
  toolbarButtons: tw.style('flex-row gap-[8px]'),
  smallButton: tw.style('flex-1 bg-white border-[1px] border-care-line rounded-[20px] py-[10px] items-center'),
  smallButtonText: tw.style('text-care-primary font-semibold'),
  suggestedQuestionRow: tw.style('flex-row flex-wrap gap-[8px]'),
  suggestedQuestionButton: tw.style('min-h-[40px] bg-care-primary rounded-[20px] py-[10px] px-[12px] items-center justify-center', {"flexGrow":1,"flexBasis":150}),
  suggestedQuestionText: tw.style('text-white text-[12px] font-semibold text-center'),
  translatePanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] gap-[10px] mb-[12px]'),
  translateInput: tw.style('min-h-[74px]', {"textAlignVertical":"top"}),
  directionRow: tw.style('flex-row bg-care-soft rounded-[20px] p-[3px] gap-[3px]'),
  directionButton: tw.style('flex-1 min-h-[38px] items-center justify-center rounded-[6px] px-[8px]'),
  directionButtonActive: tw.style('bg-care-primary'),
  directionText: tw.style('text-care-muted text-[12px] font-semibold text-center'),
  directionTextActive: tw.style('text-white'),
  speechPanel: tw.style('bg-[#F0F8F7] rounded-[20px] border-[1px] border-[#C8DDD6] p-[12px] gap-[7px]'),
  speechContext: tw.style('text-[#244A4C] text-[13px] font-semibold'),
  speechStatus: tw.style('text-care-muted text-[12px] font-semibold uppercase'),
  holdToSpeakButton: tw.style('min-h-[48px] rounded-[20px] bg-care-primary items-center justify-center px-[12px]'),
  holdToSpeakButtonActive: tw.style('bg-care-danger'),
  holdToSpeakText: tw.style('text-white text-[14px] font-semibold'),
  speechHelper: tw.style('text-[#4F625A] text-[12px] leading-[17px]'),
  voiceNotice: tw.style('bg-[#FFF9E8] rounded-[20px] border-[1px] border-[#E4C66A] p-[10px]'),
  voiceNoticeText: tw.style('text-[#765808] text-[12px] leading-[17px]'),
  translationResult: tw.style('bg-care-soft rounded-[20px] border-[1px] border-care-line p-[12px] gap-[6px]'),
  translationMeta: tw.style('text-care-muted text-[12px] font-semibold uppercase'),
  translationText: tw.style('text-care-ink text-[18px] font-semibold leading-[25px]'),
  phraseGrid: tw.style('flex-row flex-wrap gap-[8px]'),
  phraseButton: tw.style('min-h-[42px] bg-care-soft rounded-[20px] border-[1px] border-care-line px-[10px] py-[9px] justify-center', {"flexGrow":1,"flexBasis":150}),
  phraseText: tw.style('text-[#3D4E47] text-[12px] font-semibold leading-[16px]'),
  chatPanel: tw.style('bg-[#EFF5F2] rounded-[20px] border-[1px] border-care-line py-[8px] min-h-[260px]'),
  emptyChat: tw.style('p-[22px] items-center'),
  emptyChatTitle: tw.style('text-care-ink text-[16px] font-semibold'),
  emptyChatText: tw.style('text-care-muted text-[13px] mt-[6px] text-center'),
  errorBanner: tw.style('bg-[#FFF5F3] p-[10px] mx-[10px] rounded-[20px]'),
  errorText: tw.style('text-care-danger text-[13px]'),
  infoBanner: tw.style('bg-[#F0F8F7]'),
  infoText: tw.style('text-care-primary'),
  summaryPanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line px-[12px]'),
  summaryLine: tw.style('flex-row justify-between gap-[12px] py-[10px] border-b-[0.5px] border-b-care-line'),
  summaryLabel: tw.style('text-care-muted text-[12px] font-semibold w-[100px]'),
  summaryValue: tw.style('text-care-ink text-[12px] font-semibold flex-1 text-right'),
  timeline: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] gap-[10px]'),
  timelineItem: tw.style('flex-row justify-between gap-[12px]'),
  timelineTitle: tw.style('text-care-ink text-[13px] font-semibold'),
  timelineTime: tw.style('text-care-muted text-[12px] flex-1 text-right'),
  emptyTimeline: tw.style('text-care-muted text-[13px]'),
  summaryBody: tw.style('text-care-ink text-[13px] leading-[20px] py-[10px]'),
  summaryStatusText: tw.style('text-care-muted text-[13px] py-[12px]'),
  sourcesPanel: tw.style('bg-[#F3F6F4] rounded-[20px] border-[1px] border-care-line p-[12px] mt-[12px]'),
  sourcesHeader: tw.style('flex-row items-center justify-between gap-[10px]'),
  sourcesHeaderText: tw.style('flex-1 gap-[3px]'),
  sourcesChevron: tw.style('text-care-muted text-[13px]'),
  sourcesBody: tw.style('mt-[10px] gap-[10px]'),
  sourcesTitle: tw.style('text-care-ink text-[13px] font-semibold'),
  sourcesSubtitle: tw.style('text-care-muted text-[12px] leading-[17px]'),
  sourcesGroup: tw.style('gap-[6px]'),
  sourcesGroupHeader: tw.style('flex-row items-center justify-between gap-[10px]'),
  sourcesGroupTitle: tw.style('text-[#1E3A2F] text-[12px] font-semibold uppercase tracking-[0.4px]'),
  sourceItem: tw.style('bg-white rounded-[6px] border-[1px] border-[#E3EAE6] px-[10px] py-[8px]'),
  sourceLabel: tw.style('text-care-ink text-[12px] font-semibold'),
  sourceDetail: tw.style('text-care-muted text-[12px] mt-[2px] leading-[15px]'),
  drawerBackdrop: tw.style('flex-1 justify-start', {"backgroundColor":"rgba(0,0,0,0.32)"}),
  modalBackdrop: tw.style('flex-1 justify-end', {"backgroundColor":"rgba(0,0,0,0.34)"}),
  finishModal: tw.style('max-h-[94%] bg-care-canvas rounded-tl-[8px] rounded-tr-[8px] overflow-hidden'),
  finishModalHeader: tw.style('flex-row items-start gap-[12px] p-[14px] bg-white border-b-[1px] border-b-care-line'),
  modalCloseButton: tw.style('bg-care-soft rounded-[20px] px-[12px] py-[9px]'),
  modalCloseText: tw.style('text-care-primary text-[12px] font-semibold'),
  finishFormScroll: tw.style('max-h-[560px]'),
  finishFormContent: tw.style('p-[14px] gap-[12px]'),
  formSection: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] gap-[10px]'),
  formSectionTitle: tw.style('text-care-ink text-[16px] font-semibold'),
  fieldBlock: tw.style('gap-[7px]'),
  fieldLabel: tw.style('text-[#3D4E47] text-[12px] font-semibold leading-[17px]'),
  choiceWrap: tw.style('flex-row flex-wrap gap-[7px]'),
  choiceButton: tw.style('min-h-[44px] rounded-[20px] border-[1px] border-[#C9D7D1] bg-care-canvas px-[10px] py-[8px]'),
  choiceButtonActive: tw.style('bg-care-primary border-care-primary'),
  choiceText: tw.style('text-[#3D4E47] text-[12px] font-semibold'),
  choiceTextActive: tw.style('text-white'),
  vitalsGrid: tw.style('flex-row flex-wrap gap-[8px]'),
  compactField: tw.style('w-full'),
  textInput: tw.style('text-base bg-white border-[1px] border-[#C9D7D1] rounded-[20px] text-care-ink text-[13px] font-semibold px-[10px] py-[9px]'),
  textArea: tw.style('min-h-[74px]', {"textAlignVertical":"top"}),
  confirmRow: tw.style('flex-row items-start gap-[9px] pt-[4px]'),
  confirmText: tw.style('flex-1 text-[#3D4E47] text-[12px] font-semibold leading-[17px]'),
  reportPanel: tw.style('bg-white rounded-[20px] border-[1px] border-care-line p-[12px] gap-[8px]'),
  reportText: tw.style('text-care-ink text-[12px] leading-[18px] font-semibold'),
  finishModalFooter: tw.style('flex-row gap-[8px] p-[12px] bg-white border-t-[1px] border-t-care-line'),
  queueDrawer: tw.style('w-[86%] max-w-[360px] bg-care-canvas min-h-[100%] pt-[54px] px-[14px]'),
  drawerTitle: tw.style('text-care-ink text-[22px] font-semibold mb-[14px]'),
  queueItem: tw.style('flex-row gap-[12px] bg-white rounded-[20px] border-[1px] border-care-line p-[12px] mb-[8px]'),
  queueItemActive: tw.style('border-care-primary bg-[#EEF7F5]'),
  queueTimeBlock: tw.style('w-[60px]'),
  queueTime: tw.style('text-care-ink text-[16px] font-semibold'),
  queueStatus: tw.style('text-[12px] font-semibold mt-[4px]'),
  queueStatusDefault: tw.style('text-care-primary'),
  queueStatusWarn: tw.style('text-care-amber'),
  queueStatusDone: tw.style('text-[#2F7D46]'),
  queueCopy: tw.style('flex-1'),
  queuePatient: tw.style('text-care-ink text-[15px] font-semibold'),
  queueMeta: tw.style('text-care-muted text-[12px] mt-[2px]'),
  queuePurpose: tw.style('text-[#3D4E47] text-[12px] mt-[5px] leading-[17px]'),
};
export { FinishVisitFormModal, RiskReviewModal, TranslationTab, PatientDetailsPanel, VisitSummaryPanel, createEmptyCareOutcomeForm, isCareOutcomeFormComplete };
