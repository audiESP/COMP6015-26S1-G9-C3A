import React, { useCallback, useEffect, useRef, useState } from 'react';
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
import { setApiBaseUrl } from '../services/api';
import { useChatStore } from '../store/chatStore';
import { useScenarioStore } from '../store/scenarioStore';
import {
  Attachment,
  CareTask,
  LocationSnapshot,
  Message,
  PatientInfo,
  RiskAlert,
  VisitContext,
  VisitLifecycleStep,
  VisitQueueItem,
} from '../types';
import { formatDistance } from '../utils/location';

interface Props {
  apiBaseUrl?: string;
}

type VisitSection = 'assistant' | 'care';
type TaskIssueType = 'cannot_complete' | 'patient_declined' | 'safety_concern';

const sections: { id: VisitSection; label: string }[] = [
  { id: 'assistant', label: 'Assistant' },
  { id: 'care', label: 'Care Plan' },
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
  const [activeSection, setActiveSection] = useState<VisitSection>('assistant');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [issueActionsOpen, setIssueActionsOpen] = useState(false);
  const [taskIssueMenuOpen, setTaskIssueMenuOpen] = useState<string | null>(null);
  const [shiftSummaryOpen, setShiftSummaryOpen] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [patientModalOpen, setPatientModalOpen] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);

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
  const pendingTasks = scenario.tasks.filter((task) => task.status === 'pending');
  const pendingTaskCount = pendingTasks.length;
  const isCompleted = scenario.visit.status === 'completed' || scenario.lifecycleStep === 'closed';
  const canFinishVisit = visitStarted && pendingTaskCount === 0 && !isCompleted && !workflowSaving;
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
    setActiveSection('care');
  };

  const handleSelectTask = useCallback((task: CareTask) => {
    setSelectedTaskId(task.id);
    setActiveSection('care');
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
    setActiveSection('care');
  }, [isCompleted, requestLocationCheckIn, scenario.visit.checkIn, startVisit, workflowSaving]);

  const handleFinishVisitWithCheckOut = useCallback(async () => {
    if (isCompleted || workflowSaving || pendingTaskCount > 0) return;
    const checkOut = scenario.visit.checkOut
      ? undefined
      : await requestLocationCheckOut('Departure recorded when finishing the visit.');
    await completeVisit(checkOut);
  }, [completeVisit, isCompleted, pendingTaskCount, requestLocationCheckOut, scenario.visit.checkOut, workflowSaving]);

  const handleTaskIssue = async (taskId: string, type: TaskIssueType) => {
    if (workflowSaving) return;
    setTaskIssueMenuOpen(null);
    await reportTaskIssue(taskId, type);
    setActiveSection('care');
  };

  const handleNextPatient = () => {
    if (workflowSaving) return;
    goToNextVisit();
    startNewChat();
    setPendingAttachments([]);
    setShiftSummaryOpen(false);
    setActiveSection('assistant');
  };

  const handleSelectVisit = (id: string) => {
    if (workflowSaving) return;
    selectVisit(id);
    startNewChat();
    setPendingAttachments([]);
    setQueueOpen(false);
    setShiftSummaryOpen(false);
    setActiveSection('assistant');
  };

  const handleAskAi = () => {
    setActiveSection('assistant');
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
  };

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

          <LocationCheckCard
            visit={scenario.visit}
          />

          <CurrentTaskCard
            task={selectedTask ?? currentTask}
            nextStep={nextStep}
          />

          <SimpleVisitActions
            isCompleted={isCompleted}
            isLastVisit={isLastVisit}
            visitStarted={visitStarted}
            currentTask={selectedTask ?? currentTask}
            tasks={scenario.tasks}
            openTaskCount={openTasks.length}
            pendingTaskCount={pendingTaskCount}
            canFinish={canFinishVisit}
            visit={scenario.visit}
            disabled={workflowSaving}
            issueActionsOpen={issueActionsOpen}
            onStartVisit={handleStartVisitWithCheckIn}
            onCompleteTask={handleCompleteSelectedTask}
            onToggleTask={handleToggleTask}
            onSelectTask={handleSelectTask}
            onToggleIssueActions={() => setIssueActionsOpen((value) => !value)}
            onIssue={handleIssue}
            onAskAi={handleAskAi}
            onCompleteVisit={handleFinishVisitWithCheckOut}
            onNextPatient={handleNextPatient}
            onShiftSummary={() => setShiftSummaryOpen((value) => !value)}
          />

          {shiftSummaryOpen && (
            <ShiftSummary
              total={visitQueue.length}
              completed={Math.min(visitQueue.length, visitsCompleted + (currentVisitCounted ? 1 : 0))}
              followUps={followUpCount}
            />
          )}

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

          {activeSection === 'assistant' ? (
            <AssistantTab
              error={chatError}
              messages={messages}
              isLoading={chatLoading}
              contextLabel={`${scenario.patient.name} · ${stepLabels[scenario.lifecycleStep]} · ${currentTask.label}`}
              onOpenHistory={() => setHistoryOpen(true)}
              onEditPatient={() => setPatientModalOpen(true)}
            />
          ) : (
            <CareDetailsPanel
              patient={scenario.patient}
              worker={scenario.worker.name}
              location={scenario.visit.location}
              status={statusLabels[scenario.visit.status]}
              lifecycle={stepLabels[scenario.lifecycleStep]}
              completed={`${completedTasks}/${scenario.tasks.length}`}
              followUp={
                scenario.visit.status === 'follow_up_required' || scenario.visit.status === 'incident'
                  ? 'Follow-up needed'
                  : 'No follow-up noted'
              }
              visitStarted={visitStarted}
              disabled={workflowSaving}
              tasks={scenario.tasks}
              alerts={activeAlerts}
              visit={scenario.visit}
              selectedTaskId={selectedTaskId}
              onSelectTask={handleSelectTask}
              onToggleTask={handleToggleTask}
              openIssueTaskId={taskIssueMenuOpen}
              onToggleTaskIssueMenu={(taskId) =>
                setTaskIssueMenuOpen((current) => (current === taskId ? null : taskId))
              }
              onTaskIssue={handleTaskIssue}
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
    </SafeAreaView>
  );
};

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
  tasks,
  openTaskCount,
  pendingTaskCount,
  canFinish,
  visit,
  disabled,
  issueActionsOpen,
  onStartVisit,
  onCompleteTask,
  onToggleTask,
  onSelectTask,
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
  tasks: CareTask[];
  openTaskCount: number;
  pendingTaskCount: number;
  canFinish: boolean;
  visit: VisitContext;
  disabled: boolean;
  issueActionsOpen: boolean;
  onStartVisit: () => void;
  onCompleteTask: () => void;
  onToggleTask: (task: CareTask) => void;
  onSelectTask: (task: CareTask) => void;
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

      <View style={styles.taskListInline}>
        <Text style={styles.priorityLabel}>ALL TASKS</Text>
        {tasks.map((task) => {
          const isDone = task.status === 'completed';
          const hasIssue = task.status === 'issue' || task.status === 'delayed' || task.status === 'skipped';
          return (
            <View key={task.id} style={[styles.taskRowContainer, disabled && styles.taskRowDisabled, task.id === currentTask.id && styles.taskRowSelected]}>
              <View style={styles.taskRow}>
                <TouchableOpacity
                  style={styles.taskContentButton}
                  onPress={() => onSelectTask(task)}
                  activeOpacity={0.8}
                  disabled={disabled}
                >
                  <View style={[styles.taskCheck, isDone && styles.taskCheckDone, hasIssue && styles.taskCheckIssue]}>
                    <Text style={styles.taskCheckText}>{isDone ? '✓' : hasIssue ? '!' : ''}</Text>
                  </View>
                  <View style={styles.taskCopy}>
                    <Text style={styles.taskLabel}>{task.label}</Text>
                    <Text style={styles.taskDetail}>{task.dueAt ? `${task.dueAt} · ` : ''}{task.detail}</Text>
                  </View>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.taskActionButton, isDone && styles.taskActionButtonDone, disabled && styles.taskActionButtonDisabled]}
                  onPress={() => onToggleTask(task)}
                  disabled={disabled}
                  activeOpacity={0.75}
                >
                  <Text style={[styles.taskActionText, disabled && styles.taskActionTextDisabled]}>{isDone ? 'Undo' : 'Done'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
      </View>

      <View style={styles.finishBox}>
        <View style={styles.finishCopy}>
          <Text style={styles.finishText}>Finished the visit?</Text>
          <Text style={styles.finishHint}>
            {pendingTaskCount > 0
              ? `${pendingTaskCount} task${pendingTaskCount > 1 ? 's' : ''} still pending. Complete or mark an issue before finishing.`
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
          <Text style={styles.finishButtonText}>{disabled ? 'Saving...' : 'Finish visit'}</Text>
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
  onOpenHistory,
  onEditPatient,
}: {
  error: string | null;
  messages: Message[];
  isLoading: boolean;
  contextLabel: string;
  onOpenHistory: () => void;
  onEditPatient: () => void;
}) {
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

function CareDetailsPanel({
  patient,
  worker,
  location,
  visit,
  status,
  lifecycle,
  completed,
  followUp,
  tasks,
  alerts,
  visitStarted,
  disabled,
  openIssueTaskId,
  selectedTaskId,
  onSelectTask,
  onToggleTask,
  onToggleTaskIssueMenu,
  onTaskIssue,
}: {
  patient: PatientInfo;
  worker: string;
  location: string;
  visit: VisitContext;
  status: string;
  lifecycle: string;
  completed: string;
  followUp: string;
  visitStarted: boolean;
  disabled: boolean;
  openIssueTaskId: string | null;
  selectedTaskId: string | null;
  tasks: CareTask[];
  alerts: RiskAlert[];
  onSelectTask: (task: CareTask) => void;
  onToggleTask: (task: CareTask) => void;
  onToggleTaskIssueMenu: (taskId: string) => void;
  onTaskIssue: (taskId: string, type: TaskIssueType) => void;
}) {
  return (
    <View style={styles.tabPanel}>
      <SectionHeader title="Today’s care" detail="Simple checklist" />
      <View style={styles.summaryPanel}>
        <SummaryLine label="Visit" value={status} />
        <SummaryLine label="Stage" value={lifecycle} />
        <SummaryLine label="Progress" value={completed} />
        <SummaryLine label="Follow-up" value={followUp} />
        <SummaryLine label="Check-in" value={visit.checkIn ? locationSnapshotSummary(visit.checkIn) : 'Not recorded'} />
        <SummaryLine label="Check-out" value={visit.checkOut ? locationSnapshotSummary(visit.checkOut) : 'Not recorded'} />
      </View>

      <SectionHeader title="Care checklist" detail={visitStarted ? 'Tap Done or Problem' : 'Start visit first'} />
      <View style={styles.taskList}>
        {tasks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            isSelected={selectedTaskId === task.id}
            disabled={!visitStarted || disabled}
            issueMenuOpen={openIssueTaskId === task.id}
            onSelect={() => onSelectTask(task)}
            onDone={() => onToggleTask(task)}
            onToggleIssue={() => onToggleTaskIssueMenu(task.id)}
            onIssue={(type) => onTaskIssue(task.id, type)}
          />
        ))}
      </View>

      <SectionHeader title="What to keep in mind" detail="Patient needs" />
      <View style={styles.contextPanel}>
        <SummaryLine label="Language" value={`${patient.preferredLanguage ?? 'Unknown'}${patient.interpreterRequired ? ' · interpreter recommended' : ''}`} />
        <SummaryLine label="Mobility" value={patient.mobilitySupport ?? 'Not recorded'} />
        <SummaryLine label="Communication" value={patient.communicationNotes ?? 'Not recorded'} />
        <SummaryLine label="Dietary" value={patient.dietaryNotes ?? 'Not recorded'} />
        <SummaryLine label="Diagnosis" value={patient.diagnosis ?? 'Not recorded'} />
        <SummaryLine label="Culture" value={patient.culturalBackground ?? 'Not recorded'} />
        <SummaryLine label="Cognition" value={patient.cognitiveStatus ?? 'Not recorded'} />
        <SummaryLine label="Worker" value={worker} />
        <SummaryLine label="Visit" value={location} />
        <View style={styles.flagRow}>
          {patient.careRiskFlags?.map((flag) => (
            <View key={flag} style={styles.flagChip}>
              <Text style={styles.flagText}>{flag}</Text>
            </View>
          ))}
        </View>
      </View>

      <SectionHeader title="Things to watch" detail={`${alerts.length} noted`} />
      <View style={styles.alertStack}>
        {alerts.length === 0 ? (
          <Text style={styles.emptyTimeline}>Nothing urgent is flagged right now.</Text>
        ) : (
          alerts.map((alert) => <AlertCard key={alert.id} alert={alert} />)
        )}
      </View>
    </View>
  );
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
  sectionTitle: { color: '#16231E', fontSize: 17, fontWeight: '800' },
  sectionDetail: { color: '#60746B', fontSize: 11, flexShrink: 1, textAlign: 'right' },
  contextPanel: { backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#D9E2DE', paddingHorizontal: 12 },
  flagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingVertical: 12 },
  flagChip: { backgroundColor: '#E6EFEA', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 },
  flagText: { color: '#2E6F73', fontSize: 11, fontWeight: '700' },
  alertStack: { gap: 8 },
  alertCard: { borderRadius: 8, borderLeftWidth: 5, padding: 12, backgroundColor: '#FFFFFF' },
  alertHigh: { borderLeftColor: '#A83B32', backgroundColor: '#FFF5F3' },
  alertModerate: { borderLeftColor: '#B27A1A', backgroundColor: '#FFF9EC' },
  alertLow: { borderLeftColor: '#2E6F73', backgroundColor: '#F0F8F7' },
  alertTitle: { color: '#16231E', fontSize: 14, fontWeight: '800' },
  alertMessage: { color: '#3D4E47', fontSize: 13, lineHeight: 19, marginTop: 4 },
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
  drawerBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.32)', justifyContent: 'flex-start' },
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
