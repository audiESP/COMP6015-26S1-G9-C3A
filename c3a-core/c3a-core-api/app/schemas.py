"""Shared request and response schemas for the API gateway."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


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
    level: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = None


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
    workerId: Optional[str] = None
    checkIn: Optional[LocationSnapshotRequest] = None


class CompleteVisitRequest(BaseModel):
    workerId: Optional[str] = None
    checkOut: Optional[LocationSnapshotRequest] = None


class TaskStatusRequest(BaseModel):
    status: str
    workerId: Optional[str] = None


class TaskIssueRequest(BaseModel):
    type: str
    workerId: Optional[str] = None


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


class ChatResponse(BaseModel):
    reply: str
    sessionId: Optional[str] = None


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


class UploadRequest(BaseModel):
    base64: str
    mimeType: str
    filename: str


class UploadResponse(BaseModel):
    fileId: str
    url: str


class AiChatResponse(BaseModel):
    reply: str
    sources: list[str] = []
    rag: dict[str, Any] = {}
    model: dict[str, Any] = {}


class AiTranslationResponse(BaseModel):
    sourceLanguage: str
    targetLanguage: str
    translatedText: str
