import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as Location from 'expo-location';
import {
  CareTaskStatus,
  GeoPoint,
  IncidentChecklistItem,
  LocationPermissionStatus,
  LocationSnapshot,
  PatientInfo,
  ScenarioContext,
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
  updatePatientProfile,
  updateTaskStatus,
} from '../services/api';

const DEFAULT_WORKER_ID = 'cw-001';
const DEFAULT_SHIFT_DATE = '2026-05-12';

function timestamp() {
  return new Date().toISOString();
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

  const refreshQueue = useCallback(async (activeId?: string) => {
    const response = await fetchVisitQueue(DEFAULT_WORKER_ID, DEFAULT_SHIFT_DATE);
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
      setVisitQueue(response.visits);
      const firstVisit = response.visits[0];
      if (firstVisit) {
        const nextScenario = await fetchVisitScenario(firstVisit.id);
        setScenario(nextScenario);
        setActiveVisitIndex(0);
      }
    } catch (err) {
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

  const runMutation = useCallback(async (operation: () => Promise<ScenarioContext>) => {
    if (savingRef.current) {
      return scenario;
    }
    savingRef.current = true;
    setIsSaving(true);
    setError(null);
    try {
      const nextScenario = await operation();
      applyScenario(nextScenario);
      return nextScenario;
    } catch (err) {
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
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const completeCurrentTask = useCallback(() => {
    const task = selectCurrentTask(scenario);
    if (!task) return Promise.resolve(scenario);
    return runMutation(() =>
      completeTask(scenario.visit.id, task.id, scenario.worker.id),
    );
  }, [runMutation, scenario]);

  const reportTaskIssue = useCallback((
    taskId: string,
    type: 'cannot_complete' | 'patient_declined' | 'safety_concern',
  ) => {
    return runMutation(() =>
      reportTaskIssueApi(scenario.visit.id, taskId, type, scenario.worker.id),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const completeVisit = useCallback((checkOut?: LocationSnapshot) => {
    return runMutation(() =>
      finishVisit(scenario.visit.id, scenario.worker.id, checkOut),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

  const updateTask = useCallback((id: string, status: CareTaskStatus) => {
    return runMutation(() =>
      updateTaskStatus(scenario.visit.id, id, status, scenario.worker.id),
    );
  }, [runMutation, scenario.visit.id, scenario.worker.id]);

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
    toggleIncidentCheck: undefined,
    updatePatient,
    selectVisit,
    goToNextVisit,
    resetScenario: loadInitialScenario,
    restoreBaselineAlerts: undefined,
  };
}
