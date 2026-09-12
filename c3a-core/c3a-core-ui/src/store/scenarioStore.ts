import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as Location from 'expo-location';
import type { AlertAction, CareTaskStatus, LocationSnapshot, MedicationSupportRecord, PatientInfo, ScenarioContext, VisitQueueItem } from '../types';
import { distanceMeters } from '../utils/location';
import * as api from '../services/api';

export type TaskIssueType = 'cannot_complete' | 'patient_declined' | 'safety_concern' | 'medication_delayed' | 'medication_unavailable' | 'medication_unable_to_confirm';
export function localDate(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
const workerId = process.env.EXPO_PUBLIC_WORKER_ID || 'cw-001';

/** Server responses are authoritative. Failed writes never become local successes. */
export function useScenarioStore() {
  const [date, setDate] = useState(process.env.EXPO_PUBLIC_SHIFT_DATE || localDate());
  const [scenario, setScenario] = useState<ScenarioContext | null>(null);
  const [visitQueue, setVisitQueue] = useState<VisitQueueItem[]>([]);
  const [isLoading, setLoading] = useState(true);
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saving = useRef(false);
  const request = useRef(0);
  const current = useRef(scenario); current.current = scenario;
  const apply = useCallback((next: ScenarioContext) => {
    current.current = next;
    setScenario(next);
    setVisitQueue(queue => queue.map(item => item.id === next.visit.id ? { ...item, status: next.visit.status } : item));
  }, []);
  const reload = useCallback(async () => {
    if (saving.current) return;
    const seq = ++request.current;
    setLoading(true); setError(null);
    try {
      const response = await api.fetchVisitQueue(workerId, date);
      if (seq !== request.current) return;
      setVisitQueue(response.visits);
      const first = response.visits.find(v => v.id === current.current?.visit.id) ?? response.visits.find(v => v.status !== 'completed') ?? response.visits[0];
      if (!first) { current.current = null; setScenario(null); return; }
      const next = await api.fetchVisitScenario(first.id, workerId, 'care_worker');
      if (seq === request.current) apply(next);
    } catch (err) { if (seq === request.current) { current.current = null; setScenario(null); setError(err instanceof Error ? err.message : 'Could not load visits.'); } }
    finally { if (seq === request.current) setLoading(false); }
  }, [date, apply]);
  useEffect(() => { void reload(); return () => { request.current++; }; }, [reload]);
  const selectVisit = useCallback(async (id: string) => {
    if (saving.current) return false;
    const seq = ++request.current; setLoading(true); setError(null);
    try { const next = await api.fetchVisitScenario(id, workerId, 'care_worker'); if (seq !== request.current) return false; apply(next); return true; }
    catch (err) { if (seq === request.current) setError(err instanceof Error ? err.message : 'Could not open this visit.'); return false; }
    finally { if (seq === request.current) setLoading(false); }
  }, [apply]);
  const mutate = useCallback(async (operation: (context: ScenarioContext) => Promise<ScenarioContext>) => {
    if (saving.current) throw new Error('Another save is in progress.');
    const context = current.current;
    if (!context) throw new Error('Open a visit before recording care.');
    if (context.visit.status === 'completed') throw new Error('This visit is closed.');
    saving.current = true; setSaving(true); setError(null);
    try { const next = await operation(context); apply(next); return next; }
    catch (err) { setError(err instanceof Error ? err.message : 'The record was not saved. Please retry.'); throw err; }
    finally { saving.current = false; setSaving(false); }
  }, [apply]);
  const startVisit = (snapshot?: LocationSnapshot) => mutate(s => api.startVisit(s.visit.id, s.worker.id, snapshot));
  const completeVisit = (snapshot?: LocationSnapshot, report?: string) => mutate(s => api.finishVisit(s.visit.id, s.worker.id, snapshot, report));
  const updateTask = (id: string, status: CareTaskStatus, note?: string) => mutate(s => api.updateTaskStatus(s.visit.id, id, status, s.worker.id, note));
  const reportTaskIssue = (id: string, type: TaskIssueType, note?: string) => mutate(s => api.reportTaskIssue(s.visit.id, id, type, s.worker.id, note));
  const updateMedicationSupport = (record: Omit<MedicationSupportRecord, 'id' | 'visitId'>) => mutate(s => api.updateMedicationSupport(s.visit.id, record));
  const updateAlert = (id: string, action: AlertAction, note?: string) => mutate(s => api.transitionVisitAlert(s.visit.id, id, s.worker.id, s.worker.role, action, note));
  const updatePatient = (patient: PatientInfo) => mutate(s => api.updatePatientProfile(patient, s.visit.id, s.worker.id, s.worker.role));
  const locationSnapshot = async (type: LocationSnapshot['type'], manualNote?: string): Promise<LocationSnapshot> => {
    const s = current.current;
    if (!s) throw new Error('No active visit.');
    const base = { id: `${type}-${Date.now()}`, type, timestamp: new Date().toISOString() };
    if (manualNote?.trim()) return { ...base, source: 'manual_override', permissionStatus: 'unknown', note: manualNote.trim() };
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted) throw new Error('Location permission is unavailable. Enter a reason to confirm your location manually.');
    let position: Location.LocationObject;
    try { position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }); }
    catch { throw new Error('GPS is unavailable. Enter a reason to confirm your location manually.'); }
    const coords = { latitude: position.coords.latitude, longitude: position.coords.longitude };
    const distance = s.visit.plannedCoords ? distanceMeters(s.visit.plannedCoords, coords) : undefined;
    return { ...base, source: 'gps', permissionStatus: 'granted', coords, accuracyMeters: position.coords.accuracy ?? undefined, distanceFromPlannedMeters: distance, withinExpectedArea: distance === undefined ? undefined : distance <= (s.visit.locationThresholdMeters ?? 150) };
  };
  const activeAlerts = useMemo(() => (scenario?.alerts ?? []).filter(a => !a.status || ['active', 'acknowledged'].includes(a.status)).sort((a, b) => ({ high: 0, moderate: 1, low: 2 }[a.level] - { high: 0, moderate: 1, low: 2 }[b.level])), [scenario]);
  return { scenario, visitQueue, date, setDate, isLoading, isSaving, error, reload, selectVisit, activeAlerts, startVisit, completeVisit, updateTask, reportTaskIssue, updateMedicationSupport, updateAlert, updatePatient, locationSnapshot };
}
