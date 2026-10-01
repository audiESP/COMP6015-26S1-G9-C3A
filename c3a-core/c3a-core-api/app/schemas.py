"""Shared request and response schemas for the API gateway."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class PatientContext(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    medicalRecordNumber: Optional[str] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    preferredLanguage: Optional[str] = None
    interpreterRequired: Optional[bool] = None
    culturalBackground: Optional[str] = None
    mobilitySupport: Optional[str] = None
    cognitiveStatus: Optional[str] = None
    dietaryNotes: Optional[str] = None
    communicationNotes: Optional[str] = None
    careRiskFlags: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    medications: Optional[list[str]] = None
    pastMedicalHistory: Optional[str] = None


class WorkerContext(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    shift: Optional[str] = None


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class LocationSnapshot(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    timestamp: Optional[str] = None
    coords: Optional[GeoPoint] = None
    accuracyMeters: Optional[float] = None
    distanceFromPlannedMeters: Optional[float] = None
    withinExpectedArea: Optional[bool] = None
    permissionStatus: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None


class VisitContext(BaseModel):
    id: Optional[str] = None
    patientId: Optional[str] = None
    scheduledAt: Optional[str] = None
    arrivedAt: Optional[str] = None
    location: Optional[str] = None
    plannedAddress: Optional[str] = None
    plannedCoords: Optional[GeoPoint] = None
    locationThresholdMeters: Optional[float] = None
    checkIn: Optional[LocationSnapshot] = None
    checkOut: Optional[LocationSnapshot] = None
    status: Optional[str] = None


class CareTaskContext(BaseModel):
    note: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    dueAt: Optional[str] = None
    detail: Optional[str] = None


class MedicationSupportContext(BaseModel):
    id: Optional[str] = None
    visitId: str
    taskId: Optional[str] = None
    status: str
    notes: Optional[str] = None
    timestamp: str
    hcwId: str
    medicationNames: list[str] = []
    medicationItems: list[dict[str, Any]] = []


class ScenarioEventContext(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    timestamp: Optional[str] = None
    note: Optional[str] = None


class RiskContext(BaseModel):
    id: Optional[str] = None
    alertKey: Optional[str] = None
    riskType: Optional[str] = None
    level: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    visitId: Optional[str] = None
    assignedWorkerId: Optional[str] = None
    generatedFromEventId: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    acknowledgedAt: Optional[str] = None
    acknowledgedByWorkerId: Optional[str] = None
    resolvedAt: Optional[str] = None
    resolvedByWorkerId: Optional[str] = None
    dismissedAt: Optional[str] = None
    dismissedByWorkerId: Optional[str] = None
    reviewNote: Optional[str] = None


class IncidentChecklistItem(BaseModel):
    id: str
    label: str
    completed: bool


class VisitQueueItem(BaseModel):
    id: str
    scheduledAt: str
    patientName: str
    patientMeta: str
    purpose: str
    status: str


class VisitQueueResponse(BaseModel):
    visits: list[VisitQueueItem]


class VisitDatesResponse(BaseModel):
    dates: list[str]


class ScenarioResponse(BaseModel):
    worker: WorkerContext
    patient: PatientContext
    visit: VisitContext
    lifecycleStep: str
    tasks: list[CareTaskContext]
    medicationSupport: Optional[MedicationSupportContext] = None
    events: list[ScenarioEventContext]
    alerts: list[RiskContext]
    incidentChecklist: list[IncidentChecklistItem]


class UpdatePatientProfileRequest(BaseModel):
    visitId: str
    workerId: str
    role: Literal['care_worker', 'nurse', 'supervisor']
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    medicalRecordNumber: Optional[str] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    preferredLanguage: Optional[str] = None
    interpreterRequired: Optional[bool] = None
    culturalBackground: Optional[str] = None
    mobilitySupport: Optional[str] = None
    cognitiveStatus: Optional[str] = None
    dietaryNotes: Optional[str] = None
    communicationNotes: Optional[str] = None
    careRiskFlags: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    medications: Optional[list[str]] = None


class LocationSnapshotRequest(BaseModel):
    id: Optional[str] = None
    type: str
    timestamp: str
    coords: Optional[GeoPoint] = None
    accuracyMeters: Optional[float] = None
    distanceFromPlannedMeters: Optional[float] = None
    withinExpectedArea: Optional[bool] = None
    permissionStatus: str
    source: str
    note: Optional[str] = None


class StartVisitRequest(BaseModel):
    workerId: str
    checkIn: Optional[LocationSnapshotRequest] = None


class CompleteVisitRequest(BaseModel):
    report: Optional[str] = Field(default=None, max_length=100000)
    workerId: str
    checkOut: Optional[LocationSnapshotRequest] = None


class TaskStatusRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=5000)
    status: Literal["pending", "completed", "delayed", "skipped", "issue"]
    workerId: str


class TaskIssueRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=5000)
    type: Literal["cannot_complete", "patient_declined", "safety_concern", "medication_delayed", "medication_unavailable", "medication_unable_to_confirm"]
    workerId: str


class AlertActionRequest(BaseModel):
    workerId: str
    role: Literal['care_worker', 'nurse', 'supervisor']
    action: Literal['acknowledge', 'resolve', 'dismiss']
    note: Optional[str] = None


class MedicationSupportRequest(BaseModel):
    taskId: Optional[str] = None
    status: str
    notes: Optional[str] = None
    timestamp: Optional[str] = None
    hcwId: str
    medicationNames: list[str] = []
    medicationItems: list[dict[str, Any]] = []


class ShiftSummaryResponse(BaseModel):
    total: int
    completed: int
    followUps: int


class AttachmentData(BaseModel):
    type: str
    base64: str
    mimeType: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    currentTaskContext: Optional[CareTaskContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    medicationSupportContext: Optional[MedicationSupportContext] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None
    checklistContext: Optional[list[IncidentChecklistItem]] = None
    attachments: Optional[list[AttachmentData]] = None
    responseWordLimit: Optional[int] = None


class SourceReference(BaseModel):
    id: str
    kind: Literal["guideline", "patient_record", "visit_context", "general_knowledge"]
    label: str
    reason: str
    documentTitle: Optional[str] = None
    filename: Optional[str] = None
    pageStart: Optional[int] = None
    pageEnd: Optional[int] = None
    section: Optional[str] = None
    recordTypes: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    sessionId: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    sourceReferences: list[SourceReference] = Field(default_factory=list)


class GenerateVisitReportRequest(BaseModel):
    patientContext: PatientContext
    workerContext: WorkerContext
    visitContext: VisitContext
    taskContext: list[CareTaskContext]
    medicationSupportContext: Optional[MedicationSupportContext] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None
    careOutcomeForm: dict[str, Any]


class GenerateVisitReportResponse(BaseModel):
    report: str


class TranslationRequest(BaseModel):
    text: str
    sourceLanguage: Optional[str] = None
    targetLanguage: str


class TranslationResponse(BaseModel):
    sourceLanguage: str
    targetLanguage: str
    translatedText: str


class SpeechTranscriptionResponse(BaseModel):
    transcript: str
    sourceLanguage: str
    speakerRole: Literal['care_worker', 'patient']
    model: str
    requiresHumanReview: bool = True
    audioRetained: bool = False


class PatientSummaryRecord(BaseModel):
    category: str
    table: str
    label: str
    detail: Optional[str] = None


class PatientSummaryResponse(BaseModel):
    summary: str
    patientId: str
    records: list[PatientSummaryRecord] = []


class UploadRequest(BaseModel):
    base64: str
    mimeType: str
    filename: str


class UploadResponse(BaseModel):
    fileId: str
    url: str


class AiChatResponse(BaseModel):
    reply: str
    sources: list[str] = Field(default_factory=list)
    sourceReferences: list[SourceReference] = Field(default_factory=list)
    rag: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)


class AiTranslationResponse(BaseModel):
    sourceLanguage: str
    targetLanguage: str
    translatedText: str


class RiskAnalysisRequest(BaseModel):
    note: str
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    currentTaskContext: Optional[CareTaskContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None


class RiskSuggestion(BaseModel):
    riskType: str
    level: Literal["low", "moderate", "high"]
    confidence: float
    reason: str
    recommendedActions: list[str]
    requiresConfirmation: bool = True


class RiskAnalysisResponse(BaseModel):
    suggestions: list[RiskSuggestion] = []
    safetyBoundary: dict[str, bool] = {
        "diagnosisMade": False,
        "medicationChangeSuggested": False,
    }


class TrainingTopic(BaseModel):
    id: str
    slug: str
    title: str
    description: Optional[str] = None
    materialCount: int = 0


class TrainingResourceLink(BaseModel):
    title: str
    url: str
    language: str
    type: Literal["pdf", "link"]


class TrainingMaterial(BaseModel):
    id: str
    topicId: str
    title: str
    type: Literal["article", "video", "pdf", "link"]
    summary: Optional[str] = None
    body: Optional[str] = None
    url: Optional[str] = None
    sourceName: Optional[str] = None
    sourceUrl: Optional[str] = None
    durationMinutes: Optional[int] = None
    resourceLinks: list[TrainingResourceLink] = Field(default_factory=list)


class TrainingTopicsResponse(BaseModel):
    topics: list[TrainingTopic]


class TrainingMaterialsResponse(BaseModel):
    topic: TrainingTopic
    materials: list[TrainingMaterial]


class TrainingSearchResult(TrainingMaterial):
    topicTitle: str
    topicSlug: str


class TrainingSearchResponse(BaseModel):
    results: list[TrainingSearchResult]


class TaskMaterialsRequest(BaseModel):
    taskLabel: str
    taskDetail: Optional[str] = None
    taskType: Optional[str] = None


class TaskMaterialItem(BaseModel):
    sourceType: Literal["internal", "web"]
    title: str
    snippet: str
    url: Optional[str] = None
    documentTitle: Optional[str] = None
    section: Optional[str] = None
    pageLabel: Optional[str] = None
    score: Optional[float] = None


class TaskMaterialsResponse(BaseModel):
    query: str
    items: list[TaskMaterialItem] = Field(default_factory=list)
    usedWebSearch: bool = False
    internalCount: int = 0
    webCount: int = 0
