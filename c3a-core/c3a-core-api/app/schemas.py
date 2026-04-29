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


class AttachmentData(BaseModel):
    type: str
    base64: str
    mimeType: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    patientContext: Optional[PatientContext] = None
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
