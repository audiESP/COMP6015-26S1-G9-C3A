import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as Location from 'expo-location';
import {
  CareTaskStatus,
  GeoPoint,
  IncidentChecklistItem,
  LocationPermissionStatus,
  LocationSnapshot,
  MedicationSupportRecord,
  PatientInfo,
  RiskAlert,
  ScenarioEvent,
  ScenarioContext,
  VisitStatus,
  VisitQueueItem,
} from '../types';
import { createDemoScenario, createVisitQueue } from '../data/demoScenario';
import { distanceMeters } from '../utils/location';
import {
  completeTask,
  fetchVisitQueue,
  fetchVisitScenario,
  finishVisit,
  reportTaskIssue as reportTaskIssueApi,
  startVisit as startVisitApi,
  updateMedicationSupport as updateMedicationSupportApi,
  updatePatientProfile,
  updateTaskStatus,
} from '../services/api';

const DEFAULT_WORKER_ID = 'cw-001';
const DEFAULT_SHIFT_DATE = '2026-05-12';
const OFFLINE_WORKFLOW_MESSAGE =
  'Backend is unreachable, so this visit update was saved locally for the demo session.';

function timestamp() {
  return new Date().toISOString();
}

function createEvent(
  type: ScenarioEvent['type'],
  note?: string,
): ScenarioEvent {
  return {
    id: `${type}-${Date.now()}-${Math.round(Math.random() * 1000)}`,
    type,
    timestamp: timestamp(),
    note,
  };
}

function isTransientNetworkError(err: unknown) {
  if (!(err instanceof Error)) return false;

  const message = err.message.toLowerCase();
  return (
    err.name === 'AbortError' ||
    message.includes('network request failed') ||
    message.includes('failed to fetch') ||
    message.includes('networkerror') ||
    message.includes('the request timed out')
  );
}

function locationEventType(snapshot: LocationSnapshot, isCheckIn: boolean): ScenarioEvent['type'] {
  if (snapshot.permissionStatus === 'denied' || snapshot.source === 'manual_override') {
    return 'location_permission_denied';
  }
  if (snapshot.withinExpectedArea === false) {
    return 'location_out_of_range';
  }
  return isCheckIn ? 'location_check_in' : 'location_check_out';
}

function withEventIfMissing(
  events: ScenarioEvent[],
  type: ScenarioEvent['type'],
  note?: string,
) {
  return events.some((event) => event.type === type)
    ? events
    : [...events, createEvent(type, note)];
}

function applyLocalStartVisit(
  current: ScenarioContext,
  checkIn?: LocationSnapshot,
): ScenarioContext {
  const events = checkIn
    ? [...current.events, createEvent(locationEventType(checkIn, true), checkIn.note)]
    : current.events;
  const withArrived = withEventIfMissing(events, 'arrived');
  const withCareStarted = withEventIfMissing(withArrived, 'care_started');

  return {
    ...current,
    lifecycleStep: 'care_tasks',
    visit: {
      ...current.visit,
      status: 'in_progress',
      arrivedAt: current.visit.arrivedAt ?? timestamp(),
      checkIn: checkIn ?? current.visit.checkIn,
    },
    tasks: current.tasks.map((task) =>
      task.id === 'arrival' || task.type === 'arrival'
        ? { ...task, status: 'completed' }
        : task,
    ),
    events: withCareStarted,
  };
}

function applyLocalTaskStatus(
  current: ScenarioContext,
  taskId: string,
  status: CareTaskStatus,
): ScenarioContext {
  const task = current.tasks.find((item) => item.id === taskId);
  const medicationCompleted = task?.type === 'medication' && status === 'completed';
  return {
    ...current,
    lifecycleStep: current.lifecycleStep === 'pre_visit' || current.lifecycleStep === 'arrival'
      ? 'care_tasks'
      : current.lifecycleStep,
    visit: {
      ...current.visit,
      status: current.visit.status === 'scheduled' || current.visit.status === 'arrived'
        ? 'in_progress'
        : current.visit.status,
    },
    tasks: current.tasks.map((item) =>
      item.id === taskId ? { ...item, status } : item,
    ),
    events: medicationCompleted
      ? [...current.events, createEvent('medication_given')]
      : current.events,
  };
}

function medicationSupportAlert(record: MedicationSupportRecord): RiskAlert | null {
  if (record.status === 'Completed') return null;
  return {
    id: `local-medication-support-${Date.now()}`,
    level: record.status === 'Delayed' || record.status === 'Unable to Confirm' ? 'high' : 'moderate',
    title: 'Medication support needs follow-up',
    message: `${record.status}: ${record.notes || 'No reason recorded.'}`,
    source: 'rules',
  };
}

function medicationSupportVisitStatus(status: MedicationSupportRecord['status']): VisitStatus {
  if (status === 'Completed') return 'in_progress';
  if (status === 'Delayed' || status === 'Unable to Confirm') return 'delayed';
  return 'follow_up_required';
}

function medicationSupportEventType(status: MedicationSupportRecord['status']): ScenarioEvent['type'] {
  return status === 'Completed' ? 'medication_given' : status === 'Delayed' ? 'medication_delayed' : 'follow_up_required';
}

function applyLocalMedicationSupport(
  current: ScenarioContext,
  record: Omit<MedicationSupportRecord, 'id' | 'visitId'>,
): ScenarioContext {
  const medicationTask = current.tasks.find((task) => task.type === 'medication');
  const nextRecord: MedicationSupportRecord = {
    ...record,
    visitId: current.visit.id,
    taskId: record.taskId ?? medicationTask?.id,
  };
  const alert = medicationSupportAlert(nextRecord);
  const status = medicationSupportVisitStatus(nextRecord.status);
  return {
    ...current,
    medicationSupport: nextRecord,
    lifecycleStep: nextRecord.status === 'Completed' ? 'care_tasks' : 'review',
    visit: {
      ...current.visit,
      status: current.visit.status === 'completed' ? current.visit.status : status,
    },
    tasks: current.tasks.map((task) =>
      task.id === (nextRecord.taskId ?? medicationTask?.id)
        ? { ...task, status: 'completed' }
        : task,
    ),
    events: [
      ...current.events,
      createEvent(medicationSupportEventType(nextRecord.status), `${nextRecord.status}: ${nextRecord.notes ?? ''}`.trim()),
    ],
    alerts: alert
      ? [...current.alerts, alert]
      : current.alerts.filter((item) => item.title !== 'Medication support needs follow-up'),
  };
}

function localIssueDetails(
  taskLabel: string,
  issueType: 'cannot_complete' | 'patient_declined' | 'safety_concern',
  taskType?: string,
): {
  note: string;
  visitStatus: VisitStatus;
  lifecycleStep: ScenarioContext['lifecycleStep'];
  alert: RiskAlert;
  eventType: ScenarioEvent['type'];
} {
  if (issueType === 'safety_concern') {
    return {
      note: `${taskLabel}: safety concern`,
      visitStatus: 'incident',
      lifecycleStep: 'incident_active',
      eventType: 'escalation_triggered',
      alert: {
        id: `local-safety-${Date.now()}`,
        level: 'high',
        title: 'Safety concern recorded',
        message: 'Pause routine tasks and follow escalation guidance before continuing.',
        source: 'rules',
      },
    };
  }

  if (taskType === 'medication') {
    return {
      note: `${taskLabel}: ${issueType === 'patient_declined' ? 'patient declined' : 'could not complete'}`,
      visitStatus: 'delayed',
      lifecycleStep: 'incident_active',
      eventType: 'medication_delayed',
      alert: {
        id: `local-medication-${Date.now()}`,
        level: 'high',
        title: 'Medication timing issue',
        message: 'Document the delay and seek nurse or supervisor advice if needed.',
        source: 'rules',
      },
    };
  }

  return {
    note: `${taskLabel}: ${issueType === 'patient_declined' ? 'patient declined' : 'could not complete'}`,
    visitStatus: 'follow_up_required',
    lifecycleStep: 'review',
    eventType: 'follow_up_required',
    alert: {
      id: `local-follow-up-${Date.now()}`,
      level: 'moderate',
      title: 'Follow-up required',
      message: 'Schedule a later check and include the reason in the visit summary.',
      source: 'rules',
    },
  };
}

function applyLocalTaskIssue(
  current: ScenarioContext,
  taskId: string,
  issueType: 'cannot_complete' | 'patient_declined' | 'safety_concern',
): ScenarioContext {
  const task = current.tasks.find((item) => item.id === taskId);
  const details = localIssueDetails(task?.label ?? 'Care task', issueType, task?.type);
  return {
    ...current,
    lifecycleStep: details.lifecycleStep,
    visit: {
      ...current.visit,
      status: details.visitStatus,
    },
    tasks: current.tasks.map((item) =>
      item.id === taskId ? { ...item, status: 'issue' } : item,
    ),
    events: [...current.events, createEvent(details.eventType, details.note)],
    alerts: [...current.alerts, details.alert],
  };
}

function applyLocalCompleteVisit(
  current: ScenarioContext,
  checkOut?: LocationSnapshot,
): ScenarioContext {
  const events = checkOut
    ? [...current.events, createEvent(locationEventType(checkOut, false), checkOut.note)]
    : current.events;

  return {
    ...current,
    lifecycleStep: 'closed',
    visit: {
      ...current.visit,
      status: 'completed',
      checkOut: checkOut ?? current.visit.checkOut,
    },
    tasks: current.tasks.map((task) =>
      task.status === 'pending' ? { ...task, status: 'skipped' } : task,
    ),
    events: [...events, createEvent('visit_completed')],
  };
}

function createLocationSnapshot(
  type: LocationSnapshot['type'],
  permissionStatus: LocationPermissionStatus,
  source: LocationSnapshot['source'],
  plannedCoords?: GeoPoint,
  coords?: GeoPoint,
  accuracyMeters?: number,
  thresholdMeters = 150,
  note?: string,
): LocationSnapshot {
  const distanceFromPlannedMeters =
    plannedCoords && coords ? distanceMeters(plannedCoords, coords) : undefined;
  return {
    id: `${type}-${Date.now()}`,
    type,
    timestamp: timestamp(),
    coords,
    accuracyMeters,
    distanceFromPlannedMeters,
    withinExpectedArea:
      distanceFromPlannedMeters === undefined
        ? undefined
        : distanceFromPlannedMeters <= thresholdMeters,
    permissionStatus,
    source,
    note,
  };
}

async function buildLocationSnapshot(
  scenario: ScenarioContext,
  type: LocationSnapshot['type'],
  note?: string,
): Promise<LocationSnapshot> {
  try {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (permission.status !== 'granted') {
      return createLocationSnapshot(
        type,
        'denied',
        'manual_override',
        scenario.visit.plannedCoords,
        undefined,
        undefined,
        scenario.visit.locationThresholdMeters,
        note ?? 'Foreground location permission denied; worker manually confirmed the visit location.',
      );
    }

    const position = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    return createLocationSnapshot(
      type,
      'granted',
      'gps',
      scenario.visit.plannedCoords,
      {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      },
      position.coords.accuracy ?? undefined,
      scenario.visit.locationThresholdMeters,
      note,
    );
  } catch {
    return createLocationSnapshot(
      type,
      'unavailable',
      'manual_override',
      scenario.visit.plannedCoords,
      undefined,
      undefined,
      scenario.visit.locationThresholdMeters,
      note ?? 'GPS unavailable; worker manually confirmed the visit location.',
    );
  }
}

function queueWithScenario(queue: VisitQueueItem[], scenario: ScenarioContext) {
  return queue.map((item) =>
    item.id === scenario.visit.id ? { ...item, status: scenario.visit.status } : item,
  );
}

function selectCurrentTask(scenario: ScenarioContext) {
  return (
    scenario.tasks.find((item) => item.status === 'pending') ??
    scenario.tasks.find((item) => ['issue', 'delayed'].includes(item.status)) ??
    scenario.tasks.find((item) => item.status !== 'completed')
  );
}

export function useScenarioStore() {
  const [activeVisitIndex, setActiveVisitIndex] = useState(0);
  const [scenario, setScenario] = useState<ScenarioContext>(() => createDemoScenario(0));
  const [visitQueue, setVisitQueue] = useState<VisitQueueItem[]>(() => createVisitQueue(0));
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savingRef = useRef(false);
  const backendLiveRef = useRef(false);

  const refreshQueue = useCallback(async (activeId?: string) => {
    const response = await fetchVisitQueue(DEFAULT_WORKER_ID, DEFAULT_SHIFT_DATE);
    backendLiveRef.current = true;
    setVisitQueue(response.visits);
    if (activeId) {
      const index = response.visits.findIndex((visit) => visit.id === activeId);
      if (index >= 0) setActiveVisitIndex(index);
    }
    return response.visits;
  }, []);

  const loadInitialScenario = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchVisitQueue(DEFAULT_WORKER_ID, DEFAULT_SHIFT_DATE);
      backendLiveRef.current = true;
      setVisitQueue(response.visits);
      const firstVisit = response.visits[0];
      if (firstVisit) {
        const nextScenario = await fetchVisitScenario(firstVisit.id);
        setScenario(nextScenario);
        setActiveVisitIndex(0);
      }
    } catch (err) {
      backendLiveRef.current = false;
      setError(err instanceof Error ? err.message : 'Failed to load visits.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInitialScenario();
  }, [loadInitialScenario]);

  const applyScenario = useCallback((nextScenario: ScenarioContext) => {
    setScenario(nextScenario);
    setVisitQueue((currentQueue) => queueWithScenario(currentQueue, nextScenario));
    setActiveVisitIndex((currentIndex) => {
      const nextIndex = visitQueue.findIndex((visit) => visit.id === nextScenario.visit.id);
      return nextIndex >= 0 ? nextIndex : currentIndex;
    });
  }, [visitQueue]);

  const runMutation = useCallback(async (
    operation: () => Promise<ScenarioContext>,
    offlineFallback?: (current: ScenarioContext) => ScenarioContext,
  ) => {
    if (savingRef.current) {
      return scenario;
    }
    savingRef.current = true;
    setIsSaving(true);
    setError(null);
    try {
      if (!backendLiveRef.current && offlineFallback) {
        const nextScenario = offlineFallback(scenario);
        applyScenario(nextScenario);
        setError(OFFLINE_WORKFLOW_MESSAGE);
        return nextScenario;
      }
      const nextScenario = await operation();
      backendLiveRef.current = true;
      applyScenario(nextScenario);
      return nextScenario;
    } catch (err) {
      if (offlineFallback && isTransientNetworkError(err)) {
        backendLiveRef.current = false;
        const nextScenario = offlineFallback(scenario);
        applyScenario(nextScenario);
        setError(OFFLINE_WORKFLOW_MESSAGE);
        return nextScenario;
      }
      setError(err instanceof Error ? err.message : 'Visit update failed.');
      throw err;
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [applyScenario, scenario]);

  const startVisit = useCallback((checkIn?: LocationSnapshot) => {
    return runMutation(() =>
      startVisitApi(scenario.visit.id, scenario.worker.id, checkIn),
      (current) => applyLocalStartVisit(current, checkIn),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const completeCurrentTask = useCallback(() => {
    const task = selectCurrentTask(scenario);
    if (!task) return Promise.resolve(scenario);
    return runMutation(() =>
      completeTask(scenario.visit.id, task.id, scenario.worker.id),
      (current) => applyLocalTaskStatus(current, task.id, 'completed'),
    );
  }, [runMutation, scenario]);

  const reportTaskIssue = useCallback((
    taskId: string,
    type: 'cannot_complete' | 'patient_declined' | 'safety_concern',
  ) => {
    return runMutation(() =>
      reportTaskIssueApi(scenario.visit.id, taskId, type, scenario.worker.id),
      (current) => applyLocalTaskIssue(current, taskId, type),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const completeVisit = useCallback((checkOut?: LocationSnapshot) => {
    return runMutation(() =>
      finishVisit(scenario.visit.id, scenario.worker.id, checkOut),
      (current) => applyLocalCompleteVisit(current, checkOut),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const updateTask = useCallback((id: string, status: CareTaskStatus) => {
    return runMutation(() =>
      updateTaskStatus(scenario.visit.id, id, status, scenario.worker.id),
      (current) => applyLocalTaskStatus(current, id, status),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const updateMedicationSupport = useCallback((
    record: Omit<MedicationSupportRecord, 'id' | 'visitId'>,
  ) => {
    return runMutation(() =>
      updateMedicationSupportApi(scenario.visit.id, record),
      (current) => applyLocalMedicationSupport(current, record),
    );
  }, [runMutation, scenario.visit.id]);

  const requestLocationSnapshot = useCallback(async (
    type: LocationSnapshot['type'],
    note?: string,
  ) => buildLocationSnapshot(scenario, type, note), [scenario]);

  const requestLocationCheckIn = useCallback((note?: string) => (
    requestLocationSnapshot('check_in', note)
  ), [requestLocationSnapshot]);

  const requestLocationCheckOut = useCallback((note?: string) => (
    requestLocationSnapshot('check_out', note)
  ), [requestLocationSnapshot]);

  const manualLocationCheckIn = useCallback(async (note: string) => {
    const snapshot = createLocationSnapshot(
      'check_in',
      'unknown',
      'manual_override',
      scenario.visit.plannedCoords,
      undefined,
      undefined,
      scenario.visit.locationThresholdMeters,
      note || 'Location was manually confirmed at check-in.',
    );
    await startVisit(snapshot);
  }, [scenario.visit.locationThresholdMeters, scenario.visit.plannedCoords, startVisit]);

  const manualLocationCheckOut = useCallback(async (note: string) => {
    const snapshot = createLocationSnapshot(
      'check_out',
      'unknown',
      'manual_override',
      scenario.visit.plannedCoords,
      undefined,
      undefined,
      scenario.visit.locationThresholdMeters,
      note || 'Location was manually confirmed at check-out.',
    );
    await completeVisit(snapshot);
  }, [completeVisit, scenario.visit.locationThresholdMeters, scenario.visit.plannedCoords]);

  const updatePatient = useCallback((patient: PatientInfo) => {
    return runMutation(() => updatePatientProfile(patient));
  }, [runMutation]);

  const selectVisit = useCallback(async (visitId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const nextScenario = await fetchVisitScenario(visitId);
      setScenario(nextScenario);
      const index = visitQueue.findIndex((visit) => visit.id === visitId);
      if (index >= 0) setActiveVisitIndex(index);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load visit.');
    } finally {
      setIsLoading(false);
    }
  }, [visitQueue]);

  const goToNextVisit = useCallback(async () => {
    const nextIndex = Math.min(activeVisitIndex + 1, visitQueue.length - 1);
    const nextVisit = visitQueue[nextIndex];
    if (!nextVisit) return;
    await selectVisit(nextVisit.id);
  }, [activeVisitIndex, selectVisit, visitQueue]);

  const activeAlerts = useMemo(() => {
    const severity = { high: 0, moderate: 1, low: 2 };
    return [...scenario.alerts].sort((a, b) => severity[a.level] - severity[b.level]);
  }, [scenario.alerts]);

  const incidentChecklistComplete = scenario.incidentChecklist.every((item: IncidentChecklistItem) => item.completed);
  const isLastVisit = activeVisitIndex >= visitQueue.length - 1;

  return {
    scenario,
    activeAlerts,
    visitQueue,
    activeVisitIndex,
    isLastVisit,
    incidentChecklistComplete,
    isLoading,
    isSaving,
    error,
    reload: loadInitialScenario,
    recordEvent: undefined,
    startCare: undefined,
    startReview: undefined,
    closeVisit: undefined,
    startVisit,
    completeCurrentTask,
    reportTaskIssue,
    requestLocationCheckIn,
    manualLocationCheckIn,
    requestLocationCheckOut,
    manualLocationCheckOut,
    completeVisit,
    updateTask,
    updateMedicationSupport,
    toggleIncidentCheck: undefined,
    updatePatient,
    selectVisit,
    goToNextVisit,
    resetScenario: loadInitialScenario,
    restoreBaselineAlerts: undefined,
  };
}
