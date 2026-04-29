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
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  patientInfo?: PatientInfo;
}

export interface ApiChatRequest {
  messages: { role: string; content: string }[];
  patientContext?: PatientInfo;
  attachments?: { type: string; base64: string; mimeType: string }[];
}

export interface ApiChatResponse {
  reply: string;
  sessionId?: string;
}
