import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { analyseRiskNote, fetchPatientSummary, generateVisitReport, setApiBaseUrl } from '../services/api';
import type { PatientSummaryRecord } from '../services/api';
import { useChatStore } from '../store/chatStore';
import { useScenarioStore } from '../store/scenarioStore';
import {
  Attachment,
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
  VisitContext,
  VisitLifecycleStep,
  VisitQueueItem,
} from '../types';
import { formatDistance } from '../utils/location';

interface Props {
  apiBaseUrl?: string;
}

type VisitSection = 'tasks' | 'patient' | 'assistant' | 'summary';
type TaskIssueType = 'cannot_complete' | 'patient_declined' | 'safety_concern' | 'medication_delayed' | 'medication_unavailable' | 'medication_unable_to_confirm';

const sections: { id: VisitSection; label: string }[] = [
  { id: 'tasks', label: 'Tasks' },
  { id: 'patient', label: 'Patient' },
  { id: 'assistant', label: 'Assistant' },
  { id: 'summary', label: 'Summary' },
];

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
const medicationTakenStatusOptions = ['Taken', 'Not Taken', 'Unable to Confirm'] as const;
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

const statusLabels: Record<string, string> = {
  scheduled: 'Scheduled',
  arrived: 'In progress',
  in_progress: 'In progress',
  delayed: 'Needs attention',
  incident: 'Needs attention',
  follow_up_required: 'Follow-up',
  review_required: 'Needs attention',
  completed: 'Completed',
};

const stepLabels: Record<VisitLifecycleStep, string> = {
  pre_visit: 'Ready to start',
  arrival: 'Visit started',
  care_tasks: 'Care in progress',
  incident_active: 'Needs attention',
  review: 'Needs follow-up',
  closed: 'Finished',
};

export const VisitScreen: React.FC<Props> = ({ apiBaseUrl }) => {
  const scrollRef = useRef<ScrollView>(null);
  const [activeSection, setActiveSection] = useState<VisitSection>('tasks');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [issueActionsOpen, setIssueActionsOpen] = useState(false);
  const [taskIssueMenuOpen, setTaskIssueMenuOpen] = useState<string | null>(null);
  const [shiftSummaryOpen, setShiftSummaryOpen] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [patientModalOpen, setPatientModalOpen] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const [finishFormOpen, setFinishFormOpen] = useState(false);
  const [careOutcomeForm, setCareOutcomeForm] = useState<CareOutcomeFormAnswers>(() => createEmptyCareOutcomeForm());
  const [visitReport, setVisitReport] = useState('');
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [patientSummary, setPatientSummary] = useState('');
  const [summaryRecords, setSummaryRecords] = useState<PatientSummaryRecord[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [riskReviewOpen, setRiskReviewOpen] = useState(false);
  const [riskReviewNote, setRiskReviewNote] = useState('');
  const [riskSuggestions, setRiskSuggestions] = useState<RiskSuggestion[]>([]);
  const [riskReviewLoading, setRiskReviewLoading] = useState(false);
  const [riskReviewError, setRiskReviewError] = useState<string | null>(null);

  const {
    scenario,
    activeAlerts,
    visitQueue,
    activeVisitIndex,
    isLastVisit,
    isLoading: workflowLoading,
    isSaving: workflowSaving,
    error: workflowError,
    startVisit,
    completeCurrentTask,
    reportTaskIssue,
    requestLocationCheckIn,
    requestLocationCheckOut,
    completeVisit,
    updateTask,
    updateMedicationSupport,
    updatePatient,
    selectVisit,
    goToNextVisit,
  } = useScenarioStore();

  const {
    sessions,
    activeSession,
    activeSessionId,
    ensureActiveSession,
    addMessage,
    updateMessage,
    deleteSession,
    linkPatient,
    selectSession,
    startNewChat,
  } = useChatStore();

  const { sendMessage, isLoading: chatLoading, error: chatError } = useChat({
    ensureActiveSession,
    addMessage,
    updateMessage,
    activeSession,
    scenarioContext: scenario,
  });

  const messages: Message[] = activeSession?.messages ?? [];
  const patientId = scenario.patient.id;

  useEffect(() => {
    let cancelled = false;
    setPatientSummary('');
    setSummaryRecords([]);
    setSummaryError(null);
    setSummaryLoading(true);
    fetchPatientSummary(patientId)
      .then((res) => {
        if (!cancelled) {
          setPatientSummary(res.summary);
          setSummaryRecords(res.records ?? []);
        }
      })
      .catch((err) => {
        if (!cancelled) setSummaryError(err instanceof Error ? err.message : 'Summary unavailable');
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId]);
  const completedTasks = scenario.tasks.filter((task) => task.status === 'completed').length;
  const priorityAlert = activeAlerts[0];
  const visitStarted = scenario.visit.status !== 'scheduled' && scenario.lifecycleStep !== 'pre_visit';
  const currentTask =
    scenario.tasks.find((task) => ['issue', 'delayed', 'pending'].includes(task.status)) ??
    scenario.tasks[scenario.tasks.length - 1];
  useEffect(() => {
    if (!selectedTaskId || !scenario.tasks.some((task) => task.id === selectedTaskId)) {
      setSelectedTaskId(currentTask?.id ?? null);
    }
  }, [currentTask, scenario.tasks, selectedTaskId]);
  const selectedTask = scenario.tasks.find((task) => task.id === selectedTaskId) ?? currentTask;
  const openTasks = scenario.tasks.filter((task) => task.status !== 'completed');
  const incompleteRequiredTasks = scenario.tasks.filter((task) => task.status !== 'completed');
  const incompleteRequiredTaskCount = incompleteRequiredTasks.length;
  const isCompleted = scenario.visit.status === 'completed' || scenario.lifecycleStep === 'closed';
  const canFinishVisit = visitStarted && incompleteRequiredTaskCount === 0 && !isCompleted && !workflowSaving;
  const nextStep = getNextStepCopy(scenario.lifecycleStep, scenario.visit.status, currentTask, priorityAlert);
  const visitsCompleted = visitQueue.filter(
    (visit) => visit.status === 'completed' && visit.id !== scenario.visit.id,
  ).length;
  const currentVisitCounted = isCompleted && !visitQueue.some((visit) => visit.id === scenario.visit.id && visit.status === 'completed');
  const followUpCount = visitQueue.filter(
    (visit) =>
      visit.id !== scenario.visit.id &&
      (visit.status === 'follow_up_required' || visit.status === 'incident'),
  ).length + (scenario.visit.status === 'follow_up_required' || scenario.visit.status === 'incident' ? 1 : 0);

  useEffect(() => {
    setApiBaseUrl(apiBaseUrl);
  }, [apiBaseUrl]);

  useEffect(() => {
    const sessionId = ensureActiveSession();
    linkPatient(sessionId, scenario.patient);
  }, [ensureActiveSession, linkPatient, scenario.patient]);

  useEffect(() => {
    setCareOutcomeForm(createEmptyCareOutcomeForm());
    setVisitReport('');
    setReportError(null);
    setFinishFormOpen(false);
  }, [scenario.visit.id]);

  useEffect(() => {
    if (activeSection === 'assistant' && activeSession?.messages.length) {
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 120);
    }
  }, [activeSession?.messages.length, activeSession?.messages[activeSession.messages.length - 1]?.content, activeSection]);

  const handleSend = useCallback(
    (text: string, attachments: Attachment[]) => {
      Keyboard.dismiss();
      setActiveSection('assistant');
      sendMessage(text, attachments);
      setPendingAttachments([]);
    },
    [sendMessage],
  );

  const handlePatientSave = useCallback(
    (patient: PatientInfo) => {
      if (workflowSaving) return;
      updatePatient(patient);
      linkPatient(ensureActiveSession(), patient);
    },
    [ensureActiveSession, linkPatient, updatePatient, workflowSaving],
  );

  const handleIssue = async (type: TaskIssueType) => {
    if (workflowSaving || !selectedTask) return;
    setIssueActionsOpen(false);
    setTaskIssueMenuOpen(null);
    await reportTaskIssue(selectedTask.id, type);
    setActiveSection('tasks');
  };

  const handleSelectTask = useCallback((task: CareTask) => {
    setSelectedTaskId(task.id);
    setActiveSection('tasks');
  }, []);

  const handleToggleTask = useCallback((task: CareTask) => {
    setSelectedTaskId(task.id);
    return updateTask(task.id, task.status === 'completed' ? 'pending' : 'completed');
  }, [updateTask]);

  const handleCompleteSelectedTask = useCallback(() => {
    if (!selectedTask) return;
    return updateTask(selectedTask.id, selectedTask.status === 'completed' ? 'pending' : 'completed');
  }, [selectedTask, updateTask]);

  const handleStartVisitWithCheckIn = useCallback(async () => {
    if (isCompleted || workflowSaving) return;
    const checkIn = scenario.visit.checkIn
      ? undefined
      : await requestLocationCheckIn('Arrival recorded when starting the visit.');
    await startVisit(checkIn);
    setActiveSection('tasks');
  }, [isCompleted, requestLocationCheckIn, scenario.visit.checkIn, startVisit, workflowSaving]);

  const handleOpenFinishVisitForm = useCallback(() => {
    if (isCompleted || workflowSaving || incompleteRequiredTaskCount > 0) return;
    setFinishFormOpen(true);
  }, [incompleteRequiredTaskCount, isCompleted, workflowSaving]);

  const handleGenerateVisitReport = useCallback(async () => {
    if (!isCareOutcomeFormComplete(careOutcomeForm) || reportGenerating) return;
    setReportGenerating(true);
    setReportError(null);
    try {
      const response = await generateVisitReport(scenario.visit.id, {
        patientContext: scenario.patient,
        workerContext: scenario.worker,
        visitContext: scenario.visit,
        taskContext: scenario.tasks,
        medicationSupportContext: scenario.medicationSupport,
        eventContext: scenario.events,
        riskContext: scenario.alerts,
        careOutcomeForm,
      });
      setVisitReport(response.report);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : 'Failed to generate visit report.');
    } finally {
      setReportGenerating(false);
    }
  }, [careOutcomeForm, reportGenerating, scenario]);

  const handleFinishVisitWithCheckOut = useCallback(async () => {
    if (isCompleted || workflowSaving || incompleteRequiredTaskCount > 0 || !visitReport) return;
    const checkOut = scenario.visit.checkOut
      ? undefined
      : await requestLocationCheckOut('Departure recorded when finishing the visit.');
    await completeVisit(checkOut);
    setFinishFormOpen(false);
    setCareOutcomeForm(createEmptyCareOutcomeForm());
    setVisitReport('');
    setReportError(null);
  }, [completeVisit, incompleteRequiredTaskCount, isCompleted, requestLocationCheckOut, scenario.visit.checkOut, visitReport, workflowSaving]);

  const handleTaskIssue = async (taskId: string, type: TaskIssueType) => {
    if (workflowSaving) return;
    setTaskIssueMenuOpen(null);
    await reportTaskIssue(taskId, type);
    setActiveSection('tasks');
  };

  const handleMedicationSupportSave = useCallback((record: Omit<MedicationSupportRecord, 'id' | 'visitId'>) => {
    if (workflowSaving) return;
    return updateMedicationSupport(record);
  }, [updateMedicationSupport, workflowSaving]);

  const handleNextPatient = () => {
    if (workflowSaving) return;
    goToNextVisit();
    startNewChat();
    setPendingAttachments([]);
    setShiftSummaryOpen(false);
    setActiveSection('tasks');
  };

  const handleSelectVisit = (id: string) => {
    if (workflowSaving) return;
    selectVisit(id);
    startNewChat();
    setPendingAttachments([]);
    setQueueOpen(false);
    setShiftSummaryOpen(false);
    setActiveSection('tasks');
  };

  const handleAskAi = () => {
    setActiveSection('assistant');
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
  };

  const handleAnalyseRiskNote = useCallback(async () => {
    if (!riskReviewNote.trim() || riskReviewLoading) return;
    setRiskReviewLoading(true);
    setRiskReviewError(null);
    setRiskSuggestions([]);
    try {
      const result = await analyseRiskNote({
        note: riskReviewNote.trim(),
        patientContext: scenario.patient,
        workerContext: scenario.worker,
        visitContext: scenario.visit,
        currentTaskContext: selectedTask,
        taskContext: scenario.tasks,
        eventContext: scenario.events,
        riskContext: scenario.alerts,
      });
      setRiskSuggestions(result.suggestions);
    } catch (error) {
      setRiskReviewError(error instanceof Error ? error.message : 'Risk analysis failed.');
    } finally {
      setRiskReviewLoading(false);
    }
  }, [riskReviewLoading, riskReviewNote, scenario, selectedTask]);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" backgroundColor="#F7FAF8" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.flex}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.header}>
            <TouchableOpacity
              style={styles.iconButton}
              onPress={() => setQueueOpen(true)}
              activeOpacity={0.75}
            >
              <Text style={styles.iconButtonText}>☰</Text>
            </TouchableOpacity>
            <View style={styles.headerCopy}>
              <Text style={styles.kicker}>Visit {activeVisitIndex + 1} of {visitQueue.length}</Text>
              <Text style={styles.title}>Care assistant</Text>
            </View>
            <View style={[styles.statusPill, statusTone(scenario.visit.status)]}>
              <Text style={styles.statusText}>{statusLabels[scenario.visit.status]}</Text>
            </View>
          </View>

          {(workflowLoading || workflowSaving || workflowError) && (
            <View style={[styles.errorBanner, !workflowError && styles.infoBanner]}>
              <Text style={[styles.errorText, !workflowError && styles.infoText]}>
                {workflowError ?? (workflowSaving ? 'Saving visit changes...' : 'Loading visits from database...')}
              </Text>
            </View>
          )}

          <VisitSnapshot
            patientName={scenario.patient.name}
            patientMeta={`${scenario.patient.age} yrs · ${scenario.patient.gender} · ${scenario.patient.preferredLanguage}`}
            time={formatScheduleTime(scenario.visit.scheduledAt)}
            worker={`${scenario.worker.name}, care worker`}
            mobility={`${completedTasks}/${scenario.tasks.length} tasks complete`}
            step={stepLabels[scenario.lifecycleStep]}
          />

          {priorityAlert && <PriorityAlert alert={priorityAlert} />}

          <CurrentTaskCard
            task={selectedTask ?? currentTask}
            nextStep={nextStep}
          />

          <SimpleVisitActions
            isCompleted={isCompleted}
            isLastVisit={isLastVisit}
            visitStarted={visitStarted}
            currentTask={selectedTask ?? currentTask}
            openTaskCount={openTasks.length}
            incompleteRequiredTaskCount={incompleteRequiredTaskCount}
            canFinish={canFinishVisit}
            visit={scenario.visit}
            disabled={workflowSaving}
            issueActionsOpen={issueActionsOpen}
            onStartVisit={handleStartVisitWithCheckIn}
            onCompleteTask={handleCompleteSelectedTask}
            onToggleIssueActions={() => setIssueActionsOpen((value) => !value)}
            onIssue={handleIssue}
            onAskAi={handleAskAi}
            onCompleteVisit={handleOpenFinishVisitForm}
            onNextPatient={handleNextPatient}
            onShiftSummary={() => {
              setShiftSummaryOpen((value) => !value);
              setActiveSection('summary');
            }}
          />

          <View style={styles.tabBar}>
            {sections.map((section) => (
              <TouchableOpacity
                key={section.id}
                style={[styles.tabButton, activeSection === section.id && styles.tabButtonActive]}
                onPress={() => setActiveSection(section.id)}
                activeOpacity={0.75}
              >
                <Text style={[styles.tabText, activeSection === section.id && styles.tabTextActive]}>
                  {section.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {activeSection === 'tasks' && (
            <TasksPanel
              tasks={scenario.tasks}
              patient={scenario.patient}
              workerId={scenario.worker.id}
              workerName={scenario.worker.name}
              medicationSupport={scenario.medicationSupport}
              visitStarted={visitStarted}
              disabled={workflowSaving}
              selectedTaskId={selectedTaskId}
              openIssueTaskId={taskIssueMenuOpen}
              onSelectTask={handleSelectTask}
              onToggleTask={handleToggleTask}
              onToggleTaskIssueMenu={(taskId) =>
                setTaskIssueMenuOpen((current) => (current === taskId ? null : taskId))
              }
              onTaskIssue={handleTaskIssue}
              onMedicationSupportSave={handleMedicationSupportSave}
            />
          )}

          {activeSection === 'patient' && (
            <PatientDetailsPanel
              patient={scenario.patient}
              worker={scenario.worker.name}
              location={scenario.visit.location}
              alerts={activeAlerts}
              summary={patientSummary}
              summaryRecords={summaryRecords}
              summaryLoading={summaryLoading}
              summaryError={summaryError}
            />
          )}

          {activeSection === 'assistant' && (
            <AssistantTab
              error={chatError}
              messages={messages}
              isLoading={chatLoading}
              contextLabel={`${scenario.patient.name} · ${stepLabels[scenario.lifecycleStep]} · ${currentTask.label}`}
              patientLanguage={scenario.patient.preferredLanguage ?? 'the patient preferred language'}
              onSuggestedQuestion={handleSend}
              onOpenHistory={() => setHistoryOpen(true)}
              onEditPatient={() => setPatientModalOpen(true)}
              onAnalyseRisk={() => setRiskReviewOpen(true)}
            />
          )}

          {activeSection === 'summary' && (
            <VisitSummaryPanel
              status={statusLabels[scenario.visit.status]}
              lifecycle={stepLabels[scenario.lifecycleStep]}
              completed={`${completedTasks}/${scenario.tasks.length}`}
              followUp={
                scenario.visit.status === 'follow_up_required' || scenario.visit.status === 'incident'
                  ? 'Follow-up needed'
                  : 'No follow-up noted'
              }
              visit={scenario.visit}
              shiftSummaryOpen={shiftSummaryOpen}
              totalVisits={visitQueue.length}
              completedVisits={Math.min(visitQueue.length, visitsCompleted + (currentVisitCounted ? 1 : 0))}
              followUpCount={followUpCount}
            />
          )}
        </ScrollView>

        {activeSection === 'assistant' && (
          <ChatInput
            onSend={handleSend}
            onPressPlus={() => setAttachMenuOpen(true)}
            isLoading={chatLoading || workflowSaving}
            pendingAttachments={pendingAttachments}
            onRemoveAttachment={(id) =>
              setPendingAttachments((prev) => prev.filter((item) => item.id !== id))
            }
          />
        )}
      </KeyboardAvoidingView>

      <VisitQueueModal
        visible={queueOpen}
        visits={visitQueue}
        activeVisitId={scenario.visit.id}
        onSelect={handleSelectVisit}
        onClose={() => setQueueOpen(false)}
      />

      <HistorySidebar
        visible={historyOpen}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={(id) => {
          selectSession(id);
          setActiveSection('assistant');
        }}
        onDelete={deleteSession}
        onNewChat={() => {
          startNewChat();
          setActiveSection('assistant');
        }}
        onClose={() => setHistoryOpen(false)}
      />

      <AttachmentMenu
        visible={attachMenuOpen}
        onClose={() => setAttachMenuOpen(false)}
        onLinkPatient={() => setPatientModalOpen(true)}
      />

      <PatientModal
        visible={patientModalOpen}
        initial={scenario.patient}
        onSave={handlePatientSave}
        onClose={() => setPatientModalOpen(false)}
      />

      <RiskReviewModal
        visible={riskReviewOpen}
        note={riskReviewNote}
        suggestions={riskSuggestions}
        loading={riskReviewLoading}
        error={riskReviewError}
        onChange={(value) => {
          setRiskReviewNote(value);
          setRiskSuggestions([]);
          setRiskReviewError(null);
        }}
        onAnalyse={handleAnalyseRiskNote}
        onClose={() => setRiskReviewOpen(false)}
      />

      <FinishVisitFormModal
        visible={finishFormOpen}
        form={careOutcomeForm}
        report={visitReport}
        reportError={reportError}
        isGenerating={reportGenerating}
        isSaving={workflowSaving}
        canGenerate={isCareOutcomeFormComplete(careOutcomeForm)}
        onChange={(nextForm) => {
          setCareOutcomeForm(nextForm);
          setVisitReport('');
          setReportError(null);
        }}
        onGenerate={handleGenerateVisitReport}
        onFinish={handleFinishVisitWithCheckOut}
        onClose={() => setFinishFormOpen(false)}
      />
    </SafeAreaView>
  );
};

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
  const update = (patch: Partial<CareOutcomeFormAnswers>) => onChange({ ...form, ...patch });
  const updateVitals = (key: string, value: string) => update({ vitals: { ...form.vitals, [key]: value } });
  const toggleList = (key: 'incompleteReasons' | 'wellbeingConcerns', value: string) => {
    const current = form[key];
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    update({ [key]: next } as Pick<CareOutcomeFormAnswers, typeof key>);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.finishModal}>
          <View style={styles.finishModalHeader}>
            <View style={styles.currentTaskCopy}>
              <Text style={styles.priorityLabel}>FINISH VISIT</Text>
              <Text style={styles.currentTaskTitle}>Care outcome form</Text>
              <Text style={styles.currentTaskDetail}>
                Complete the preset form, generate the visit report, then finish the visit.
              </Text>
            </View>
            <TouchableOpacity style={styles.modalCloseButton} onPress={onClose} activeOpacity={0.75}>
              <Text style={styles.modalCloseText}>Close</Text>
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.finishFormScroll} contentContainerStyle={styles.finishFormContent}>
            <FormSection title="1. Patient Condition">
              <SingleChoice label="How was the patient's overall condition during this visit? *" value={form.overallCondition} options={overallConditionOptions} onChange={(overallCondition) => update({ overallCondition })} />
              <SingleChoice label="Were there any noticeable changes in the patient's condition? *" value={form.conditionChanged} options={yesNoOptions} onChange={(conditionChanged) => update({ conditionChanged })} />
              {form.conditionChanged === 'Yes' && (
                <TextField label="If Yes, please describe *" value={form.conditionChangeNotes} onChange={(conditionChangeNotes) => update({ conditionChangeNotes })} />
              )}
            </FormSection>

            <FormSection title="2. Vital Signs">
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
            </FormSection>

            <FormSection title="3. Care Task Outcomes">
              <SingleChoice label="Were all scheduled care tasks completed? *" value={form.tasksCompleted} options={tasksCompletedOptions} onChange={(tasksCompleted) => update({ tasksCompleted })} />
              {form.tasksCompleted && form.tasksCompleted !== 'Yes' && (
                <>
                  <MultiChoice label="If not all tasks were completed, select the reason *" values={form.incompleteReasons} options={incompleteReasonOptions} onToggle={(value) => toggleList('incompleteReasons', value)} />
                  <TextField label="Other reason" value={form.incompleteOther} onChange={(incompleteOther) => update({ incompleteOther })} />
                </>
              )}
              <TextField label="Additional care task notes" value={form.taskNotes} onChange={(taskNotes) => update({ taskNotes })} />
            </FormSection>

            <FormSection title="4. Medication Support Outcome">
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
            </FormSection>

            <FormSection title="5. Patient Wellbeing and Observations">
              <MultiChoice label="Did you observe any new concerns during the visit? *" values={form.wellbeingConcerns} options={[...wellbeingConcernOptions, 'Other']} onToggle={(value) => toggleList('wellbeingConcerns', value)} />
              {form.wellbeingConcerns.includes('Other') && (
                <TextField label="Other concern *" value={form.wellbeingOther} onChange={(wellbeingOther) => update({ wellbeingOther })} />
              )}
              <TextField label="Observation notes" value={form.observationNotes} onChange={(observationNotes) => update({ observationNotes })} />
            </FormSection>

            <FormSection title="6. Follow-up Required">
              <SingleChoice label="Does this visit require follow-up action? *" value={form.followUpRequired} options={followUpOptions} onChange={(followUpRequired) => update({ followUpRequired })} />
              {form.followUpRequired && form.followUpRequired !== 'No follow-up required' && (
                <TextField label="Follow-up details *" value={form.followUpDetails} onChange={(followUpDetails) => update({ followUpDetails })} />
              )}
            </FormSection>

            <FormSection title="7. Overall Visit Outcome">
              <SingleChoice label="Select the overall outcome of this visit *" value={form.overallOutcome} options={overallOutcomeOptions} onChange={(overallOutcome) => update({ overallOutcome })} />
              <TextField label="Final HCW comments" value={form.finalComments} onChange={(finalComments) => update({ finalComments })} />
              <TouchableOpacity style={styles.confirmRow} onPress={() => update({ confirmedAccurate: !form.confirmedAccurate })} activeOpacity={0.75}>
                <View style={[styles.taskCheck, form.confirmedAccurate && styles.taskCheckDone]}>
                  <Text style={styles.taskCheckText}>{form.confirmedAccurate ? '✓' : ''}</Text>
                </View>
                <Text style={styles.confirmText}>I confirm the information recorded above is accurate to the best of my knowledge. *</Text>
              </TouchableOpacity>
            </FormSection>

            <View style={styles.reportPanel}>
              <Text style={styles.priorityLabel}>GENERATED VISIT REPORT</Text>
              {reportError && <Text style={styles.errorText}>{reportError}</Text>}
              {report ? (
                <Text style={styles.reportText}>{report}</Text>
              ) : (
                <Text style={styles.currentTaskDetail}>
                  The report will appear here after all required questions are complete and the local AI finishes generation.
                </Text>
              )}
            </View>
          </ScrollView>
          <View style={styles.finishModalFooter}>
            <ActionButton
              label={isGenerating ? 'Generating...' : 'Generate Visit Report'}
              onPress={onGenerate}
              disabled={!canGenerate || isGenerating || isSaving}
            />
            <ActionButton
              label={isSaving ? 'Finishing...' : 'Finish Visit'}
              tone="success"
              onPress={onFinish}
              disabled={!report || isGenerating || isSaving}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
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

function VisitSnapshot({
  patientName,
  patientMeta,
  time,
  worker,
  mobility,
  step,
}: {
  patientName: string;
  patientMeta: string;
  time: string;
  worker: string;
  mobility: string;
  step: string;
}) {
  return (
    <View style={styles.visitPanel}>
      <View style={styles.visitTopRow}>
        <View style={styles.patientBlock}>
          <Text style={styles.patientName}>{patientName}</Text>
          <Text style={styles.patientMeta}>{patientMeta}</Text>
        </View>
        <View style={styles.scheduleBlock}>
          <Text style={styles.scheduleTime}>{time}</Text>
          <Text style={styles.scheduleLabel}>{step}</Text>
        </View>
      </View>
      <View style={styles.compactInfoRow}>
        <CompactInfo label="Worker" value={worker} />
        <CompactInfo label="Mobility" value={mobility} />
      </View>
    </View>
  );
}

function CompactInfo({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.compactInfo}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

function PriorityAlert({ alert }: { alert: RiskAlert }) {
  return (
    <View style={[styles.priorityAlert, alertTone(alert.level)]}>
      <Text style={styles.priorityLabel}>{alert.level.toUpperCase()} PRIORITY</Text>
      <Text style={styles.alertTitle}>{alert.title}</Text>
      <Text style={styles.alertMessage}>{alert.message}</Text>
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

function CurrentTaskCard({
  task,
  nextStep,
}: {
  task: CareTask;
  nextStep: string;
}) {
  return (
    <View style={styles.currentTaskCard}>
      <View style={styles.currentTaskCopy}>
        <Text style={styles.priorityLabel}>SUGGESTED NEXT STEP</Text>
        <Text style={styles.currentTaskTitle}>{nextStep}</Text>
        <Text style={styles.currentTaskDetail}>
          Current care item: {task.label}{task.dueAt ? ` around ${task.dueAt}` : ''}.
        </Text>
      </View>
    </View>
  );
}

function SimpleVisitActions({
  isCompleted,
  isLastVisit,
  visitStarted,
  currentTask,
  openTaskCount,
  incompleteRequiredTaskCount,
  canFinish,
  visit,
  disabled,
  issueActionsOpen,
  onStartVisit,
  onCompleteTask,
  onToggleIssueActions,
  onIssue,
  onAskAi,
  onCompleteVisit,
  onNextPatient,
  onShiftSummary,
}: {
  isCompleted: boolean;
  isLastVisit: boolean;
  visitStarted: boolean;
  currentTask: CareTask;
  openTaskCount: number;
  incompleteRequiredTaskCount: number;
  canFinish: boolean;
  visit: VisitContext;
  disabled: boolean;
  issueActionsOpen: boolean;
  onStartVisit: () => void;
  onCompleteTask: () => void;
  onToggleIssueActions: () => void;
  onIssue: (type: TaskIssueType) => void;
  onAskAi: () => void;
  onCompleteVisit: () => void;
  onNextPatient: () => void;
  onShiftSummary: () => void;
}) {
  if (isCompleted) {
    return (
      <View style={styles.reviewGate}>
        <Text style={styles.priorityLabel}>FINISHED</Text>
        <Text style={styles.currentTaskTitle}>Visit finished</Text>
        <Text style={styles.currentTaskDetail}>
          This visit is closed. Move to the next patient when ready.
        </Text>
        <View style={styles.quickActionBar}>
          <ActionButton label={isLastVisit ? 'Shift summary' : 'Next patient'} onPress={isLastVisit ? onShiftSummary : onNextPatient} disabled={disabled} />
          <ActionButton label="Ask AI" tone="muted" onPress={onAskAi} />
        </View>
      </View>
    );
  }

  if (!visitStarted) {
    return (
      <View style={styles.workflowPanel}>
        <Text style={styles.priorityLabel}>STEP 1</Text>
        <Text style={styles.currentTaskTitle}>Start when you are with the patient</Text>
        <Text style={styles.currentTaskDetail}>
          Starts the visit and records arrival location. After that, the care checklist becomes active.
        </Text>
        <InlineLocationStatus
          label="Check-in"
          snapshot={visit.checkIn}
          fallback="Will be recorded when starting this visit"
        />
        <View style={styles.singleActionRow}>
          <ActionButton label={disabled ? 'Saving...' : 'Start visit'} onPress={onStartVisit} disabled={disabled} />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.workflowPanel}>
      <Text style={styles.priorityLabel}>STEP 2</Text>
      <Text style={styles.currentTaskTitle}>{currentTask.label}</Text>
      <Text style={styles.currentTaskDetail}>
        {currentTask.detail} {openTaskCount > 1 ? `${openTaskCount} items still need attention.` : 'This is the last open item.'}
      </Text>
      <View style={styles.quickActionBar}>
        <ActionButton label={disabled ? 'Saving...' : currentTask.status === 'completed' ? 'Undo' : 'Done'} tone="success" onPress={onCompleteTask} disabled={disabled} />
        <ActionButton label="Problem" tone="warn" onPress={onToggleIssueActions} disabled={disabled} />
        <ActionButton label="Ask AI" tone="muted" onPress={onAskAi} />
      </View>
      {issueActionsOpen && (
        <View style={styles.issueGrid}>
          <ActionButton label="Cannot complete" tone="warn" onPress={() => onIssue('cannot_complete')} disabled={disabled} />
          <ActionButton label="Patient declined" tone="warn" onPress={() => onIssue('patient_declined')} disabled={disabled} />
          <ActionButton label="Safety concern" tone="danger" onPress={() => onIssue('safety_concern')} disabled={disabled} />
        </View>
      )}

      <View style={styles.finishBox}>
        <View style={styles.finishCopy}>
          <Text style={styles.finishText}>Finished the visit?</Text>
          <Text style={styles.finishHint}>
            {incompleteRequiredTaskCount > 0
              ? `${incompleteRequiredTaskCount} required task${incompleteRequiredTaskCount > 1 ? 's' : ''} must be completed before finishing.`
              : visit.checkOut
                ? `Check-out: ${locationSnapshotSummary(visit.checkOut)}`
                : 'Check-out will be recorded when finishing this visit'}
          </Text>
        </View>
        <TouchableOpacity
          style={[styles.finishButton, (!canFinish || disabled) && styles.finishButtonDisabled]}
          onPress={onCompleteVisit}
          activeOpacity={0.75}
          disabled={!canFinish || disabled}
        >
          <Text style={styles.finishButtonText}>{disabled ? 'Saving...' : 'Finish Visit'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function InlineLocationStatus({
  label,
  snapshot,
  fallback,
}: {
  label: string;
  snapshot?: LocationSnapshot;
  fallback: string;
}) {
  return (
    <View style={styles.inlineLocationStatus}>
      <Text style={styles.inlineLocationLabel}>{label}</Text>
      <Text style={styles.inlineLocationValue}>
        {snapshot ? locationSnapshotSummary(snapshot) : fallback}
      </Text>
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

function AssistantTab({
  error,
  messages,
  isLoading,
  contextLabel,
  patientLanguage,
  onSuggestedQuestion,
  onOpenHistory,
  onEditPatient,
  onAnalyseRisk,
}: {
  error: string | null;
  messages: Message[];
  isLoading: boolean;
  contextLabel: string;
  patientLanguage: string;
  onSuggestedQuestion: (text: string, attachments: Attachment[]) => void;
  onOpenHistory: () => void;
  onEditPatient: () => void;
  onAnalyseRisk: () => void;
}) {
  const [translationText, setTranslationText] = useState('');
  const commonPhrases = [
    'I am here for your scheduled care visit.',
    'Do you have any pain or discomfort today?',
    'I am going to help with your medication now.',
  ];

  const requestTranslation = (sourceText: string) => {
    const cleanText = sourceText.trim();
    if (!cleanText) return;
    onSuggestedQuestion(
      `Translate this care-worker message into ${patientLanguage}. Keep it clear, respectful, and easy for an older patient to understand: "${cleanText}"`,
      [],
    );
    setTranslationText('');
  };

  return (
    <View style={styles.tabPanel}>
      <View style={styles.assistantToolbar}>
        <View style={styles.contextBadge}>
          <Text style={styles.contextBadgeText}>{contextLabel}</Text>
        </View>
        <View style={styles.toolbarButtons}>
          <TouchableOpacity style={styles.smallButton} onPress={onOpenHistory} activeOpacity={0.75}>
            <Text style={styles.smallButtonText}>Chat history</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.smallButton} onPress={onEditPatient} activeOpacity={0.75}>
            <Text style={styles.smallButtonText}>Patient</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.smallButton} onPress={onAnalyseRisk} activeOpacity={0.75}>
            <Text style={styles.smallButtonText}>Review note</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.suggestedQuestionRow}>
          <TouchableOpacity
            style={styles.suggestedQuestionButton}
            onPress={() => onSuggestedQuestion('Explain the current care task and its basic steps.', [])}
            activeOpacity={0.75}
          >
            <Text style={styles.suggestedQuestionText}>Explain current task</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.suggestedQuestionButton}
            onPress={() => onSuggestedQuestion('Based on the current patient, visit stage, task, and active risks, what should I do next?', [])}
            activeOpacity={0.75}
          >
            <Text style={styles.suggestedQuestionText}>What should I do next?</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.translatePanel}>
        <View style={styles.sectionHeaderCompact}>
          <Text style={styles.sectionTitle}>Translate</Text>
          <Text style={styles.sectionDetail}>{patientLanguage}</Text>
        </View>
        <TextInput
          style={[styles.textInput, styles.translateInput]}
          value={translationText}
          onChangeText={setTranslationText}
          placeholder="Type what you want to say to the patient"
          placeholderTextColor="#8A9B93"
          multiline
        />
        <View style={styles.quickActionBar}>
          <ActionButton
            label="Translate"
            onPress={() => requestTranslation(translationText)}
            disabled={!translationText.trim() || isLoading}
          />
        </View>
        <View style={styles.phraseGrid}>
          {commonPhrases.map((phrase) => (
            <TouchableOpacity
              key={phrase}
              style={styles.phraseButton}
              onPress={() => requestTranslation(phrase)}
              disabled={isLoading}
              activeOpacity={0.75}
            >
              <Text style={styles.phraseText}>{phrase}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.chatPanel}>
        {error && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
        {messages.length === 0 ? (
          <View style={styles.emptyChat}>
            <Text style={styles.emptyChatTitle}>Ask what to do next</Text>
            <Text style={styles.emptyChatText}>Try: “Based on this patient, task and risk, what should I do next?”</Text>
          </View>
        ) : (
          messages.map((message) => <ChatBubble key={message.id} message={message} />)
        )}
        {isLoading && (
          <ChatBubble
            message={{
              id: '__typing__',
              role: 'assistant',
              content: '',
              timestamp: new Date(),
            }}
            isTyping
          />
        )}
      </View>
    </View>
  );
}

function TasksPanel({
  patient,
  workerId,
  workerName,
  tasks,
  visitStarted,
  disabled,
  openIssueTaskId,
  selectedTaskId,
  onSelectTask,
  onToggleTask,
  onToggleTaskIssueMenu,
  onTaskIssue,
  medicationSupport,
  onMedicationSupportSave,
}: {
  patient: PatientInfo;
  workerId: string;
  workerName: string;
  visitStarted: boolean;
  disabled: boolean;
  openIssueTaskId: string | null;
  selectedTaskId: string | null;
  tasks: CareTask[];
  medicationSupport?: MedicationSupportRecord | null;
  onSelectTask: (task: CareTask) => void;
  onToggleTask: (task: CareTask) => void;
  onToggleTaskIssueMenu: (taskId: string) => void;
  onTaskIssue: (taskId: string, type: TaskIssueType) => void;
  onMedicationSupportSave: (record: Omit<MedicationSupportRecord, 'id' | 'visitId'>) => void;
}) {
  const medicationTask = tasks.find((task) => task.type === 'medication');
  const completedCount = tasks.filter((task) => task.status === 'completed').length;

  return (
    <View style={styles.tabPanel}>
      <SectionHeader title="Today’s tasks" detail={`${completedCount}/${tasks.length} complete`} />
      <View style={styles.taskList}>
        {tasks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            isSelected={task.id === selectedTaskId}
            disabled={disabled}
            issueMenuOpen={openIssueTaskId === task.id}
            onSelect={() => onSelectTask(task)}
            onDone={() => onToggleTask(task)}
            onToggleIssue={() => onToggleTaskIssueMenu(task.id)}
            onIssue={(type) => onTaskIssue(task.id, type)}
          />
        ))}
      </View>

      {medicationTask && (
        <MedicationSupportPanel
          task={medicationTask}
          patient={patient}
          record={medicationSupport}
          disabled={disabled || !visitStarted}
          workerId={workerId}
          workerName={workerName}
          onSave={onMedicationSupportSave}
        />
      )}
    </View>
  );
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
}: {
  patient: PatientInfo;
  worker: string;
  location: string;
  alerts: RiskAlert[];
  summary: string;
  summaryRecords: PatientSummaryRecord[];
  summaryLoading: boolean;
  summaryError: string | null;
}) {
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

      <SectionHeader title="Things to watch" detail={`${alerts.length} noted`} />
      <View style={styles.alertStack}>
        {alerts.length === 0 ? (
          <Text style={styles.emptyTimeline}>Nothing urgent is flagged right now.</Text>
        ) : (
          alerts.map((alert) => <AlertCard key={alert.id} alert={alert} />)
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
  const groups = useMemo(() => {
    const byCategory = new Map<string, PatientSummaryRecord[]>();
    for (const record of records) {
      const list = byCategory.get(record.category) ?? [];
      list.push(record);
      byCategory.set(record.category, list);
    }
    return Array.from(byCategory.entries());
  }, [records]);

  return (
    <View style={styles.sourcesPanel}>
      <Text style={styles.sourcesTitle}>Sources used for this summary</Text>
      <Text style={styles.sourcesSubtitle}>
        Records the AI referenced from the patient dataset. Review these before acting on the summary.
      </Text>
      {groups.map(([category, items]) => (
        <View key={category} style={styles.sourcesGroup}>
          <Text style={styles.sourcesGroupTitle}>
            {summarySourceCategoryMeta[category]?.title ?? category} ({items.length})
          </Text>
          {items.map((item, index) => (
            <View key={`${item.label}-${index}`} style={styles.sourceItem}>
              <Text style={styles.sourceLabel}>{item.label}</Text>
              {item.detail ? <Text style={styles.sourceDetail}>{item.detail}</Text> : null}
            </View>
          ))}
        </View>
      ))}
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

function MedicationSupportPanel({
  task,
  patient,
  record,
  workerId,
  workerName,
  disabled,
  onSave,
}: {
  task: CareTask;
  patient: PatientInfo;
  record?: MedicationSupportRecord | null;
  workerId: string;
  workerName: string;
  disabled: boolean;
  onSave: (record: Omit<MedicationSupportRecord, 'id' | 'visitId'>) => void;
}) {
  const medicationNames = patient.medications?.length
    ? patient.medications
    : ['Medication list unavailable'];
  const [status, setStatus] = useState<MedicationSupportStatus | ''>(record?.status ?? '');
  const [notes, setNotes] = useState(record?.notes ?? '');
  const [medicationItems, setMedicationItems] = useState<MedicationSupportItem[]>(() =>
    createMedicationSupportItems(medicationNames, record?.medicationItems),
  );

  useEffect(() => {
    setStatus(record?.status ?? '');
    setNotes(record?.notes ?? '');
    setMedicationItems(createMedicationSupportItems(medicationNames, record?.medicationItems));
  }, [record?.status, record?.notes, record?.medicationItems, task.id, patient.medications]);

  const notesRequired = Boolean(status && status !== 'Completed');
  const medicationItemsComplete = medicationItems.every((item) => item.takenStatus);
  const canSave = Boolean(status) && medicationItemsComplete && (!notesRequired || notes.trim().length > 0) && !disabled;
  const timestampLabel = record?.timestamp ? formatShortTime(record.timestamp) : 'Not recorded';

  const updateMedicationTakenStatus = (name: string, takenStatus: MedicationSupportItem['takenStatus']) => {
    setMedicationItems((current) =>
      current.map((item) => {
        if (item.name !== name) return item;
        return {
          ...item,
          takenStatus,
          takenAt: takenStatus === 'Taken' ? (item.takenAt ?? new Date().toISOString()) : undefined,
        };
      }),
    );
  };

  const handleSave = () => {
    if (!canSave || !status) return;
    onSave({
      taskId: task.id,
      status,
      notes: notes.trim(),
      timestamp: new Date().toISOString(),
      hcwId: workerId,
      medicationNames,
      medicationItems,
    });
  };

  return (
    <>
      <SectionHeader title="Medication support" detail={record ? `${record.status} · ${timestampLabel}` : 'Not recorded'} />
      <View style={styles.medicationPanel}>
        <Text style={styles.priorityLabel}>CURRENT MEDICATION RECORDS</Text>
        <View style={styles.medicationItemList}>
          {medicationItems.map((item) => (
            <View key={item.name} style={styles.medicationItemRow}>
              <Text style={styles.medicationName}>{item.name}</Text>
              {item.takenStatus === 'Taken' && item.takenAt && (
                <Text style={styles.medicationTakenAt}>Taken at {formatMedicationTakenTime(item.takenAt)}</Text>
              )}
              <View style={styles.medicationTakenOptions}>
                {medicationTakenStatusOptions.map((option) => (
                  <TouchableOpacity
                    key={option}
                    style={[styles.medicationTakenButton, item.takenStatus === option && styles.medicationTakenButtonActive]}
                    onPress={() => updateMedicationTakenStatus(item.name, option)}
                    disabled={disabled}
                    activeOpacity={0.75}
                  >
                    <Text style={[styles.medicationTakenText, item.takenStatus === option && styles.medicationTakenTextActive]}>{option}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          ))}
        </View>
        <Text style={styles.taskDetail}>{task.dueAt ? `${task.dueAt} · ` : ''}{task.detail}</Text>
        <SingleChoice
          label="Medication support status *"
          value={status}
          options={medicationStatusOptions}
          onChange={(nextStatus) => setStatus(nextStatus as MedicationSupportStatus)}
        />
        {notesRequired && (
          <TextField
            label="Notes or reason *"
            value={notes}
            onChange={setNotes}
          />
        )}
        {!notesRequired && (
          <TextField
            label="Medication support notes"
            value={notes}
            onChange={setNotes}
          />
        )}
        {record && (
          <View style={styles.inlineLocationStatus}>
            <Text style={styles.inlineLocationLabel}>Audit record</Text>
            <Text style={styles.inlineLocationValue}>
              Patient {patient.name} · Care worker {workerName}
            </Text>
            <Text style={styles.inlineLocationValue}>
              Saved {formatSavedDateTime(record.timestamp)}
            </Text>
          </View>
        )}
        {status && status !== 'Completed' && (
          <Text style={styles.locationWarning}>
            This status is available to follow-up rules, risk alerts, and VHA context.
          </Text>
        )}
        {!medicationItemsComplete && (
          <Text style={styles.locationWarning}>
            Select whether each listed medication was taken before saving.
          </Text>
        )}
        <View style={styles.singleActionRow}>
          <ActionButton label="Save medication status" tone="success" onPress={handleSave} disabled={!canSave} />
        </View>
      </View>
    </>
  );
}

function createMedicationSupportItems(
  medicationNames: string[],
  existingItems?: MedicationSupportItem[],
): MedicationSupportItem[] {
  const existingByName = new Map((existingItems ?? []).map((item) => [item.name, item]));
  return medicationNames.map((name) => ({
    name,
    takenStatus: existingByName.get(name)?.takenStatus,
    takenAt: existingByName.get(name)?.takenAt,
  }));
}

function VisitQueueModal({
  visible,
  visits,
  activeVisitId,
  onSelect,
  onClose,
}: {
  visible: boolean;
  visits: VisitQueueItem[];
  activeVisitId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableOpacity style={styles.drawerBackdrop} activeOpacity={1} onPress={onClose}>
        <View style={styles.queueDrawer}>
          <Text style={styles.drawerTitle}>Today's visits</Text>
          {visits.map((visit) => (
            <TouchableOpacity
              key={visit.id}
              style={[styles.queueItem, visit.id === activeVisitId && styles.queueItemActive]}
              onPress={() => onSelect(visit.id)}
              activeOpacity={0.75}
            >
              <View style={styles.queueTimeBlock}>
                <Text style={styles.queueTime}>{formatScheduleTime(visit.scheduledAt)}</Text>
                <Text style={[styles.queueStatus, statusTextTone(visit.status)]}>{statusLabels[visit.status]}</Text>
              </View>
              <View style={styles.queueCopy}>
                <Text style={styles.queuePatient}>{visit.patientName}</Text>
                <Text style={styles.queueMeta}>{visit.patientMeta}</Text>
                <Text style={styles.queuePurpose}>{visit.purpose}</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </TouchableOpacity>
    </Modal>
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

function AlertCard({ alert }: { alert: RiskAlert }) {
  return (
    <View style={[styles.alertCard, alertTone(alert.level)]}>
      <Text style={styles.alertTitle}>{alert.title}</Text>
      <Text style={styles.alertMessage}>{alert.message}</Text>
    </View>
  );
}

function TaskRow({
  task,
  isSelected,
  disabled,
  issueMenuOpen,
  onSelect,
  onDone,
  onToggleIssue,
  onIssue,
}: {
  task: CareTask;
  isSelected: boolean;
  disabled: boolean;
  issueMenuOpen: boolean;
  onSelect: () => void;
  onDone: () => void;
  onToggleIssue: () => void;
  onIssue: (type: TaskIssueType) => void;
}) {
  const isDone = task.status === 'completed';
  const hasProblem = task.status === 'issue' || task.status === 'delayed' || task.status === 'skipped';
  return (
    <View style={[styles.taskRowContainer, disabled && styles.taskRowDisabled, isSelected && styles.taskRowSelected]}>
      <View style={styles.taskRow}>
        <TouchableOpacity style={styles.taskContentButton} onPress={onSelect} activeOpacity={0.8} disabled={disabled}>
          <View style={[styles.taskCheck, isDone && styles.taskCheckDone, hasProblem && styles.taskCheckIssue]}>
            <Text style={styles.taskCheckText}>{isDone ? '✓' : hasProblem ? '!' : ''}</Text>
          </View>
          <View style={styles.taskCopy}>
            <Text style={styles.taskLabel}>{task.label}</Text>
            <Text style={styles.taskDetail}>{task.dueAt} · {task.detail}</Text>
            {hasProblem && <Text style={styles.taskProblemText}>{taskStatusCopy(task.status)}</Text>}
          </View>
        </TouchableOpacity>
        <View style={styles.taskButtons}>
          <TouchableOpacity
            style={[styles.taskActionButton, isDone && styles.taskActionButtonDone, disabled && styles.taskActionButtonDisabled]}
            onPress={onDone}
            disabled={disabled}
            activeOpacity={0.75}
          >
            <Text style={[styles.taskActionText, disabled && styles.taskActionTextDisabled]}>{isDone ? 'Undo' : 'Done'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.taskActionButton, styles.taskProblemButton, disabled && styles.taskActionButtonDisabled]}
            onPress={onToggleIssue}
            disabled={disabled || isDone}
            activeOpacity={0.75}
          >
            <Text style={[styles.taskActionText, disabled && styles.taskActionTextDisabled]}>Problem</Text>
          </TouchableOpacity>
        </View>
      </View>
      {issueMenuOpen && !disabled && !isDone && (
        <View style={styles.taskIssueMenu}>
          <ActionButton label="Cannot complete" tone="warn" onPress={() => onIssue('cannot_complete')} />
          <ActionButton label="Patient declined" tone="warn" onPress={() => onIssue('patient_declined')} />
          <ActionButton label="Safety concern" tone="danger" onPress={() => onIssue('safety_concern')} />
          {task.type === 'medication' && (
            <>
              <ActionButton label="Medication delayed" tone="warn" onPress={() => onIssue('medication_delayed')} />
              <ActionButton label="Medication unavailable" tone="warn" onPress={() => onIssue('medication_unavailable')} />
              <ActionButton label="Unable to confirm medication" tone="warn" onPress={() => onIssue('medication_unable_to_confirm')} />
            </>
          )}
        </View>
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

function formatScheduleTime(raw: string) {
  return new Date(raw).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatShortTime(raw: string) {
  return new Date(raw).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatMedicationTakenTime(raw: string) {
  return new Date(raw).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatSavedDateTime(raw: string) {
  const date = new Date(raw);
  const pad = (value: number) => value.toString().padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function getNextStepCopy(
  step: VisitLifecycleStep,
  status: string,
  task: CareTask,
  alert?: RiskAlert,
) {
  if (status === 'completed' || step === 'closed') {
    return 'Review visit details before moving on';
  }
  if (alert?.level === 'high') {
    return 'Pause and deal with the safety concern first';
  }
  if (status === 'follow_up_required' || step === 'review') {
    return 'Make sure follow-up is clear before finishing';
  }
  if (step === 'pre_visit') {
    return 'Start the visit when you are with the patient';
  }
  if (task.status === 'delayed' || task.status === 'issue') {
    return 'Check this care item before continuing';
  }
  return `Continue with ${task.label.toLowerCase()}`;
}

function locationSnapshotSummary(snapshot: LocationSnapshot) {
  const source = snapshot.source === 'manual_override' ? 'manual confirmation' : 'GPS';
  const distance = snapshot.distanceFromPlannedMeters !== undefined
    ? `, ${formatDistance(snapshot.distanceFromPlannedMeters)} from planned location`
    : '';
  const status = snapshot.withinExpectedArea === false ? ', outside expected area' : '';
  return `${source} at ${formatShortTime(snapshot.timestamp)}${distance}${status}`;
}

function statusTone(status: string) {
  if (status === 'incident') return styles.statusIncident;
  if (status === 'delayed' || status === 'follow_up_required' || status === 'review_required') return styles.statusWarn;
  if (status === 'completed') return styles.statusDone;
  return styles.statusDefault;
}

function statusTextTone(status: string) {
  if (status === 'completed') return styles.queueStatusDone;
  if (status === 'incident' || status === 'delayed') return styles.queueStatusWarn;
  return styles.queueStatusDefault;
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

function taskStatusCopy(status: string) {
  if (status === 'issue') return 'Problem recorded';
  if (status === 'delayed') return 'Delayed';
  if (status === 'skipped') return 'Not completed';
  return status;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F7FAF8' },
  flex: { flex: 1 },
  content: { padding: 14, paddingBottom: 18 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D9E2DE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonText: { color: '#2E6F73', fontSize: 18, fontWeight: '800' },
  headerCopy: { flex: 1 },
  kicker: { color: '#60746B', fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  title: { color: '#16231E', fontSize: 24, fontWeight: '800', marginTop: 2 },
  statusPill: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  statusText: { color: '#FFFFFF', fontWeight: '800', fontSize: 12 },
  statusDefault: { backgroundColor: '#2E6F73' },
  statusWarn: { backgroundColor: '#9A6A13' },
  statusIncident: { backgroundColor: '#A83B32' },
  statusDone: { backgroundColor: '#2F7D46' },
  visitPanel: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 14,
  },
  visitTopRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  patientBlock: { flex: 1 },
  patientName: { color: '#16231E', fontSize: 22, fontWeight: '800' },
  patientMeta: { color: '#60746B', fontSize: 13, marginTop: 4 },
  scheduleBlock: { alignItems: 'flex-end' },
  scheduleTime: { color: '#2E6F73', fontSize: 24, fontWeight: '800' },
  scheduleLabel: { color: '#60746B', fontSize: 12 },
  compactInfoRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  compactInfo: { flex: 1, backgroundColor: '#F4F7F6', borderRadius: 8, padding: 10 },
  infoLabel: { color: '#60746B', fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
  infoValue: { color: '#16231E', fontSize: 13, fontWeight: '600', marginTop: 4 },
  priorityAlert: { borderRadius: 8, borderLeftWidth: 5, padding: 12, marginTop: 12, gap: 6 },
  priorityLabel: { color: '#60746B', fontSize: 11, fontWeight: '900', textTransform: 'uppercase' },
  currentTaskCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    marginTop: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  currentTaskCopy: { flex: 1 },
  currentTaskTitle: { color: '#16231E', fontSize: 17, fontWeight: '800', marginTop: 4 },
  currentTaskDetail: { color: '#60746B', fontSize: 12, lineHeight: 18, marginTop: 4 },
  locationCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    marginTop: 12,
  },
  locationHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  locationSummaryGrid: { flexDirection: 'row', gap: 8, marginTop: 10 },
  locationMiniPanel: { flex: 1, backgroundColor: '#F4F7F6', borderRadius: 8, padding: 10 },
  locationMeta: { color: '#60746B', fontSize: 11, marginTop: 4 },
  locationWarning: { color: '#9A6A13', fontSize: 12, fontWeight: '800', lineHeight: 17, marginTop: 8 },
  actionHint: { color: '#60746B', fontSize: 12, marginTop: 10 },
  quickActionBar: { flexDirection: 'row', gap: 8, marginTop: 12 },
  issueGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  workflowPanel: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    marginTop: 12,
  },
  singleActionRow: { marginTop: 12 },
  inlineLocationStatus: {
    backgroundColor: '#F4F7F6',
    borderRadius: 8,
    padding: 10,
    marginTop: 10,
  },
  inlineLocationLabel: { color: '#60746B', fontSize: 11, fontWeight: '900', textTransform: 'uppercase' },
  inlineLocationValue: { color: '#16231E', fontSize: 12, fontWeight: '700', marginTop: 4, lineHeight: 17 },
  finishBox: {
    backgroundColor: '#F4F7F6',
    borderRadius: 8,
    marginTop: 12,
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  finishCopy: { flex: 1 },
  finishText: { color: '#3D4E47', fontSize: 13, fontWeight: '800' },
  finishHint: { color: '#60746B', fontSize: 11, fontWeight: '700', marginTop: 3, lineHeight: 15 },
  finishButton: { backgroundColor: '#2F7D46', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 9 },
  finishButtonDisabled: { backgroundColor: '#9BA9A2' },
  finishButtonText: { color: '#FFFFFF', fontWeight: '900', fontSize: 12 },
  reviewGate: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    marginTop: 12,
  },
  tabBar: { flexDirection: 'row', backgroundColor: '#E8EFEA', borderRadius: 8, padding: 3, marginTop: 16 },
  tabButton: { flex: 1, minHeight: 38, alignItems: 'center', justifyContent: 'center', borderRadius: 6 },
  tabButtonActive: { backgroundColor: '#FFFFFF' },
  tabText: { color: '#60746B', fontSize: 12, fontWeight: '800' },
  tabTextActive: { color: '#2E6F73' },
  tabPanel: { marginTop: 12 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 8, gap: 12 },
  sectionHeaderCompact: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  sectionTitle: { color: '#16231E', fontSize: 17, fontWeight: '800' },
  sectionDetail: { color: '#60746B', fontSize: 11, flexShrink: 1, textAlign: 'right' },
  contextPanel: { backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', paddingHorizontal: 12 },
  flagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingVertical: 12 },
  flagChip: { backgroundColor: '#E6EFEA', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 },
  flagText: { color: '#2E6F73', fontSize: 11, fontWeight: '700' },
  medicationPanel: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    gap: 10,
    marginBottom: 12,
  },
  medicationList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  medicationChip: { backgroundColor: '#EEF7F1', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 5 },
  medicationChipText: { color: '#2D6A4F', fontSize: 11, fontWeight: '800' },
  medicationItemList: { gap: 8 },
  medicationItemRow: {
    backgroundColor: '#F7FAF8',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 10,
    gap: 8,
  },
  medicationName: { color: '#16231E', fontSize: 13, fontWeight: '900', lineHeight: 18 },
  medicationTakenOptions: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  medicationTakenButton: {
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#C9D7D1',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  medicationTakenButtonActive: { backgroundColor: '#2E6F73', borderColor: '#2E6F73' },
  medicationTakenText: { color: '#3D4E47', fontSize: 11, fontWeight: '900' },
  medicationTakenTextActive: { color: '#FFFFFF' },
  medicationTakenAt: { color: '#2F7D46', fontSize: 12, fontWeight: '800', lineHeight: 17 },
  alertStack: { gap: 8 },
  alertCard: { borderRadius: 8, borderLeftWidth: 5, padding: 12, backgroundColor: '#FFFFFF' },
  alertHigh: { borderLeftColor: '#A83B32', backgroundColor: '#FFF5F3' },
  alertModerate: { borderLeftColor: '#B27A1A', backgroundColor: '#FFF9EC' },
  alertLow: { borderLeftColor: '#2E6F73', backgroundColor: '#F0F8F7' },
  alertTitle: { color: '#16231E', fontSize: 14, fontWeight: '800' },
  alertMessage: { color: '#3D4E47', fontSize: 13, lineHeight: 19, marginTop: 4 },
  riskSuggestionCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D6E5DF',
    backgroundColor: '#F4FAF7',
    padding: 12,
    marginTop: 10,
  },
  suggestionAction: { color: '#3D4E47', fontSize: 13, lineHeight: 19, marginTop: 5 },
  suggestionConfirmation: { color: '#0D7377', fontSize: 12, fontWeight: '700', marginTop: 9 },
  taskList: { backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', overflow: 'hidden', marginBottom: 12 },
  taskListInline: { backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', overflow: 'hidden', marginTop: 12 },
  taskRowContainer: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#E4ECE8' },
  taskRowSelected: { backgroundColor: '#EEF7F1', borderBottomColor: '#2D6A4F' },
  taskRow: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12 },
  taskRowDisabled: { opacity: 0.62 },
  taskContentButton: { flex: 1, flexDirection: 'row', alignItems: 'center', marginRight: 8 },
  taskCheck: { width: 24, height: 24, borderRadius: 6, borderWidth: 1, borderColor: '#B8C9C1', alignItems: 'center', justifyContent: 'center' },
  taskCheckDone: { backgroundColor: '#2F7D46', borderColor: '#2F7D46' },
  taskCheckIssue: { backgroundColor: '#A83B32', borderColor: '#A83B32' },
  taskCheckText: { color: '#FFFFFF', fontWeight: '900' },
  taskCopy: { flex: 1 },
  taskLabel: { color: '#16231E', fontSize: 14, fontWeight: '800' },
  taskDetail: { color: '#60746B', fontSize: 12, lineHeight: 17, marginTop: 2 },
  taskProblemText: { color: '#A83B32', fontSize: 12, fontWeight: '800', marginTop: 4 },
  taskButtons: { width: 92, gap: 6 },
  taskActionButton: { backgroundColor: '#2F7D46', borderRadius: 7, paddingVertical: 7, alignItems: 'center' },
  taskActionButtonDone: { backgroundColor: '#2F7D46' },
  taskProblemButton: { backgroundColor: '#9A6A13' },
  taskActionButtonDisabled: { backgroundColor: '#D6DED9' },
  taskActionText: { color: '#FFFFFF', fontSize: 11, fontWeight: '900' },
  taskActionTextDisabled: { color: '#7A8B83' },
  taskIssueMenu: { flexDirection: 'row', gap: 8, paddingHorizontal: 12, paddingBottom: 12 },
  actionButton: { flex: 1, borderRadius: 8, paddingVertical: 12, paddingHorizontal: 10 },
  actionDefault: { backgroundColor: '#2E6F73' },
  actionWarn: { backgroundColor: '#9A6A13' },
  actionDanger: { backgroundColor: '#A83B32' },
  actionSuccess: { backgroundColor: '#2F7D46' },
  actionMuted: { backgroundColor: '#4F625A' },
  actionDisabled: { backgroundColor: '#D6DED9' },
  actionText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800', textAlign: 'center' },
  actionTextDisabled: { color: '#7A8B83' },
  assistantToolbar: { gap: 8, marginBottom: 10 },
  contextBadge: { backgroundColor: '#E6EFEA', borderRadius: 8, padding: 10 },
  contextBadgeText: { color: '#2E6F73', fontSize: 12, fontWeight: '800' },
  toolbarButtons: { flexDirection: 'row', gap: 8 },
  smallButton: { flex: 1, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#D9E2DE', borderRadius: 8, paddingVertical: 10, alignItems: 'center' },
  smallButtonText: { color: '#2E6F73', fontWeight: '800' },
  suggestedQuestionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  suggestedQuestionButton: { flexGrow: 1, flexBasis: 150, minHeight: 40, backgroundColor: '#2E6F73', borderRadius: 8, paddingVertical: 10, paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center' },
  suggestedQuestionText: { color: '#FFFFFF', fontSize: 12, fontWeight: '800', textAlign: 'center' },
  translatePanel: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    gap: 10,
    marginBottom: 12,
  },
  translateInput: { minHeight: 74, textAlignVertical: 'top' },
  phraseGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  phraseButton: {
    flexGrow: 1,
    flexBasis: 150,
    minHeight: 42,
    backgroundColor: '#F4F7F6',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    paddingHorizontal: 10,
    paddingVertical: 9,
    justifyContent: 'center',
  },
  phraseText: { color: '#3D4E47', fontSize: 12, fontWeight: '800', lineHeight: 16 },
  chatPanel: { backgroundColor: '#EFF5F2', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', paddingVertical: 8, minHeight: 260 },
  emptyChat: { padding: 22, alignItems: 'center' },
  emptyChatTitle: { color: '#16231E', fontSize: 16, fontWeight: '800' },
  emptyChatText: { color: '#60746B', fontSize: 13, marginTop: 6, textAlign: 'center' },
  errorBanner: { backgroundColor: '#FFF5F3', padding: 10, marginHorizontal: 10, borderRadius: 8 },
  errorText: { color: '#A83B32', fontSize: 13 },
  infoBanner: { backgroundColor: '#F0F8F7' },
  infoText: { color: '#2E6F73' },
  summaryPanel: { backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', paddingHorizontal: 12 },
  summaryLine: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#E4ECE8' },
  summaryLabel: { color: '#60746B', fontSize: 12, fontWeight: '800', width: 100 },
  summaryValue: { color: '#16231E', fontSize: 12, fontWeight: '700', flex: 1, textAlign: 'right' },
  timeline: { backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', padding: 12, gap: 10 },
  timelineItem: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  timelineTitle: { color: '#16231E', fontSize: 13, fontWeight: '800' },
  timelineTime: { color: '#60746B', fontSize: 12, flex: 1, textAlign: 'right' },
  emptyTimeline: { color: '#60746B', fontSize: 13 },
  summaryBody: { color: '#16231E', fontSize: 13, lineHeight: 20, paddingVertical: 10 },
  summaryStatusText: { color: '#60746B', fontSize: 13, paddingVertical: 12 },
  sourcesPanel: { backgroundColor: '#F3F6F4', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', padding: 12, marginTop: 12, gap: 10 },
  sourcesTitle: { color: '#16231E', fontSize: 13, fontWeight: '800' },
  sourcesSubtitle: { color: '#60746B', fontSize: 12, lineHeight: 17 },
  sourcesGroup: { gap: 6 },
  sourcesGroupTitle: { color: '#1E3A2F', fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4 },
  sourceItem: { backgroundColor: '#FFFFFF', borderRadius: 6, borderWidth: 1, borderColor: '#E3EAE6', paddingHorizontal: 10, paddingVertical: 8 },
  sourceLabel: { color: '#16231E', fontSize: 12, fontWeight: '600' },
  sourceDetail: { color: '#60746B', fontSize: 11, marginTop: 2, lineHeight: 15 },
  drawerBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.32)', justifyContent: 'flex-start' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.34)', justifyContent: 'flex-end' },
  finishModal: {
    maxHeight: '94%',
    backgroundColor: '#F7FAF8',
    borderTopLeftRadius: 8,
    borderTopRightRadius: 8,
    overflow: 'hidden',
  },
  finishModalHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    padding: 14,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#D9E2DE',
  },
  modalCloseButton: {
    backgroundColor: '#E8EFEA',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  modalCloseText: { color: '#2E6F73', fontSize: 12, fontWeight: '900' },
  finishFormScroll: { maxHeight: 560 },
  finishFormContent: { padding: 14, gap: 12 },
  formSection: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    gap: 10,
  },
  formSectionTitle: { color: '#16231E', fontSize: 16, fontWeight: '900' },
  fieldBlock: { gap: 7 },
  fieldLabel: { color: '#3D4E47', fontSize: 12, fontWeight: '800', lineHeight: 17 },
  choiceWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  choiceButton: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#C9D7D1',
    backgroundColor: '#F7FAF8',
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  choiceButtonActive: { backgroundColor: '#2E6F73', borderColor: '#2E6F73' },
  choiceText: { color: '#3D4E47', fontSize: 12, fontWeight: '800' },
  choiceTextActive: { color: '#FFFFFF' },
  vitalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  compactField: { width: '48%', minWidth: 145 },
  textInput: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#C9D7D1',
    borderRadius: 8,
    color: '#16231E',
    fontSize: 13,
    fontWeight: '600',
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  textArea: { minHeight: 74, textAlignVertical: 'top' },
  confirmRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 9, paddingTop: 4 },
  confirmText: { flex: 1, color: '#3D4E47', fontSize: 12, fontWeight: '800', lineHeight: 17 },
  reportPanel: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 12,
    gap: 8,
  },
  reportText: { color: '#16231E', fontSize: 12, lineHeight: 18, fontWeight: '600' },
  finishModalFooter: {
    flexDirection: 'row',
    gap: 8,
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#D9E2DE',
  },
  queueDrawer: { width: '86%', maxWidth: 360, backgroundColor: '#F7FAF8', minHeight: '100%', paddingTop: 54, paddingHorizontal: 14 },
  drawerTitle: { color: '#16231E', fontSize: 22, fontWeight: '900', marginBottom: 14 },
  queueItem: { flexDirection: 'row', gap: 12, backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', padding: 12, marginBottom: 8 },
  queueItemActive: { borderColor: '#2E6F73', backgroundColor: '#EEF7F5' },
  queueTimeBlock: { width: 60 },
  queueTime: { color: '#16231E', fontSize: 16, fontWeight: '900' },
  queueStatus: { fontSize: 11, fontWeight: '900', marginTop: 4 },
  queueStatusDefault: { color: '#2E6F73' },
  queueStatusWarn: { color: '#9A6A13' },
  queueStatusDone: { color: '#2F7D46' },
  queueCopy: { flex: 1 },
  queuePatient: { color: '#16231E', fontSize: 15, fontWeight: '900' },
  queueMeta: { color: '#60746B', fontSize: 12, marginTop: 2 },
  queuePurpose: { color: '#3D4E47', fontSize: 12, marginTop: 5, lineHeight: 17 },
});
