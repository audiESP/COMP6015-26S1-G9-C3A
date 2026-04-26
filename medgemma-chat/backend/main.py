# backend/main.py
"""
MedGemma Chat Backend
---------------------
FastAPI server that wraps the MedGemma model (via Hugging Face transformers).

Quick start:
    pip install -r requirements.txt
    python main.py

Endpoints:
    POST /chat    - Send messages, get AI reply
    POST /upload  - Upload file/image (base64)
    GET  /health  - Liveness check
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import base64
import uuid
import os
import logging

from medgemma_service import MedGemmaService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MedGemma Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Initialise model ──────────────────────────────────────────────────────────
service = MedGemmaService()

# ── Request / Response schemas ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # "user" | "assistant"
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
    type: str          # "image" | "file" | "patient"
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

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "model": service.model_name}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint. Builds a prompt from the conversation history,
    optional patient context, and any uploaded images, then calls MedGemma.
    """
    try:
        reply = await service.generate_reply(
            messages=[(m.role, m.content) for m in req.messages],
            patient=req.patientContext,
            attachments=req.attachments or [],
        )
        return ChatResponse(reply=reply)
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=UploadResponse)
async def upload(req: UploadRequest):
    """
    Receive a base64-encoded file, save it temporarily, return a URL.
    In production point this at S3 / GCS / your hospital's storage.
    """
    try:
        file_id = str(uuid.uuid4())
        ext = req.mimeType.split("/")[-1]
        path = f"/tmp/{file_id}.{ext}"
        data = base64.b64decode(req.base64)
        with open(path, "wb") as f:
            f.write(data)
        return UploadResponse(fileId=file_id, url=f"/files/{file_id}.{ext}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
