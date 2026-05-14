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


class WorkerContext(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    shift: Optional[str] = None


class VisitContext(BaseModel):
    id: Optional[str] = None
    patientId: Optional[str] = None
    scheduledAt: Optional[str] = None
    arrivedAt: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None


class CareTaskContext(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    dueAt: Optional[str] = None
    detail: Optional[str] = None


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


class AttachmentData(BaseModel):
    type: str
    base64: str
    mimeType: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None
    attachments: Optional[list[AttachmentData]] = None


class ChatResponse(BaseModel):
    reply: str
    sessionId: Optional[str] = None


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
