// src/types/index.ts

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  attachments?: Attachment[];
}

export interface Attachment {
  id: string;
  type: 'image' | 'file' | 'patient';
  name: string;
  uri?: string;
  mimeType?: string;
  base64?: string;
}

export interface PatientInfo {
  id: string;
  name: string;
  age?: number;
  gender?: string;
  medicalRecordNumber?: string;
  diagnosis?: string;
  notes?: string;
  preferredLanguage?: string;
  interpreterRequired?: boolean;
  culturalBackground?: string;
  mobilitySupport?: string;
  cognitiveStatus?: string;
  dietaryNotes?: string;
  communicationNotes?: string;
  careRiskFlags?: string[];
  allergies?: string[];
  medications?: string[];
  pastMedicalHistory?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  patientInfo?: PatientInfo;
}

export type VisitStatus =
  | 'scheduled'
  | 'arrived'
  | 'in_progress'
  | 'delayed'
  | 'incident'
  | 'follow_up_required'
  | 'review_required'
  | 'completed';

export type VisitLifecycleStep =
  | 'pre_visit'
  | 'arrival'
  | 'care_tasks'
  | 'incident_active'
  | 'review'
  | 'closed';

export type CareTaskStatus = 'pending' | 'completed' | 'delayed' | 'skipped' | 'issue';

export type LocationPermissionStatus =
  | 'unknown'
  | 'granted'
  | 'denied'
  | 'unavailable';

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export interface LocationSnapshot {
  id: string;
  type: 'check_in' | 'check_out';
  timestamp: string;
  coords?: GeoPoint;
  accuracyMeters?: number;
  distanceFromPlannedMeters?: number;
  withinExpectedArea?: boolean;
  permissionStatus: LocationPermissionStatus;
  source: 'gps' | 'manual_override';
  note?: string;
}

export type CareTaskType =
  | 'arrival'
  | 'meal'
  | 'medication'
  | 'wellbeing'
  | 'mobility'
  | 'documentation'
  | 'follow_up';

export interface WorkerContext {
  id: string;
  name: string;
  role: 'care_worker' | 'nurse' | 'supervisor';
  shift: string;
}

export interface VisitContext {
  id: string;
  patientId: string;
  scheduledAt: string;
  arrivedAt?: string;
  location: string;
  plannedAddress?: string;
  plannedCoords?: GeoPoint;
  locationThresholdMeters?: number;
  checkIn?: LocationSnapshot;
  checkOut?: LocationSnapshot;
  status: VisitStatus;
}

export interface CareTask {
  id: string;
  label: string;
  type: CareTaskType;
  status: CareTaskStatus;
  dueAt?: string;
  detail?: string;
}

export type MedicationSupportStatus =
  | 'Completed'
  | 'Delayed'
  | 'Declined'
  | 'Unavailable'
  | 'Unable to Confirm';

export type MedicationTakenStatus = 'Taken' | 'Not Taken' | 'Unable to Confirm';

export interface MedicationSupportItem {
  name: string;
  takenStatus?: MedicationTakenStatus;
  takenAt?: string;
}

export interface MedicationSupportRecord {
  id?: string;
  visitId: string;
  taskId?: string;
  status: MedicationSupportStatus;
  notes?: string;
  timestamp: string;
  hcwId: string;
  medicationNames: string[];
  medicationItems?: MedicationSupportItem[];
}

export interface ScenarioEvent {
  id: string;
  type:
    | 'arrived'
    | 'care_started'
    | 'running_late'
    | 'medication_given'
    | 'medication_delayed'
    | 'location_check_in'
    | 'location_check_out'
    | 'location_permission_denied'
    | 'location_out_of_range'
    | 'patient_unsteady'
    | 'fall_found'
    | 'escalation_triggered'
    | 'follow_up_required'
    | 'review_started'
    | 'incident_check_completed'
    | 'visit_completed';
  timestamp: string;
  note?: string;
}

export interface RiskAlert {
  id: string;
  level: 'low' | 'moderate' | 'high';
  title: string;
  message: string;
  source?: 'rules' | 'rag' | 'ai';
}

export interface RiskSuggestion {
  riskType: string;
  level: 'low' | 'moderate' | 'high';
  confidence: number;
  reason: string;
  recommendedActions: string[];
  requiresConfirmation: boolean;
}

export interface ScenarioContext {
  worker: WorkerContext;
  patient: PatientInfo;
  visit: VisitContext;
  lifecycleStep: VisitLifecycleStep;
  tasks: CareTask[];
  medicationSupport?: MedicationSupportRecord | null;
  events: ScenarioEvent[];
  alerts: RiskAlert[];
  incidentChecklist: IncidentChecklistItem[];
}

export interface IncidentChecklistItem {
  id: string;
  label: string;
  completed: boolean;
}

export interface VisitQueueItem {
  id: string;
  scheduledAt: string;
  patientName: string;
  patientMeta: string;
  purpose: string;
  status: VisitStatus;
}

export interface ApiChatRequest {
  messages: { role: string; content: string }[];
  patientContext?: PatientInfo;
  workerContext?: WorkerContext;
  visitContext?: VisitContext;
  currentTaskContext?: CareTask;
  taskContext?: CareTask[];
  medicationSupportContext?: MedicationSupportRecord | null;
  eventContext?: ScenarioEvent[];
  riskContext?: RiskAlert[];
  checklistContext?: IncidentChecklistItem[];
  attachments?: { type: string; base64: string; mimeType: string }[];
  responseWordLimit?: number;
}

export interface ApiChatResponse {
  reply: string;
  sessionId?: string;
}

export interface CareOutcomeFormAnswers {
  overallCondition: string;
  conditionChanged: string;
  conditionChangeNotes: string;
  vitalsRequired: string;
  vitals: Record<string, string>;
  vitalsConcern: string;
  vitalsConcernNotes: string;
  tasksCompleted: string;
  incompleteReasons: string[];
  incompleteOther: string;
  taskNotes: string;
  medicationRequired: string;
  medicationStatus: string;
  medicationConcern: string;
  medicationConcernNotes: string;
  wellbeingConcerns: string[];
  wellbeingOther: string;
  observationNotes: string;
  followUpRequired: string;
  followUpDetails: string;
  overallOutcome: string;
  finalComments: string;
  confirmedAccurate: boolean;
}

export interface VisitReportRequest {
  patientContext: PatientInfo;
  workerContext: WorkerContext;
  visitContext: VisitContext;
  taskContext: CareTask[];
  eventContext?: ScenarioEvent[];
  riskContext?: RiskAlert[];
  medicationSupportContext?: MedicationSupportRecord | null;
  careOutcomeForm: CareOutcomeFormAnswers;
}

export interface RiskAnalysisRequest {
  note: string;
  patientContext?: PatientInfo;
  workerContext?: WorkerContext;
  visitContext?: VisitContext;
  currentTaskContext?: CareTask;
  taskContext?: CareTask[];
  eventContext?: ScenarioEvent[];
  riskContext?: RiskAlert[];
}

export interface RiskAnalysisResponse {
  suggestions: RiskSuggestion[];
  safetyBoundary: {
    diagnosisMade: boolean;
    medicationChangeSuggested: boolean;
  };
}

export interface VisitReportResponse {
  report: string;
}

export interface TranslationRequest {
  text: string;
  sourceLanguage?: string;
  targetLanguage: string;
}

export interface TranslationResponse {
  sourceLanguage: string;
  targetLanguage: string;
  translatedText: string;
}
