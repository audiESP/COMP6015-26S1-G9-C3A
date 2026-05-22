// src/services/api.ts
import { NativeModules, Platform } from 'react-native';
import {
  ApiChatRequest,
  ApiChatResponse,
  CareTaskStatus,
  LocationSnapshot,
  PatientInfo,
  ScenarioContext,
  VisitQueueItem,
} from '../types';

const DEFAULT_API_PORT = '8000';

type ProcessWithEnv = {
  process?: {
    env?: Record<string, string | undefined>;
  };
};

function normalizeBaseUrl(url?: string | null): string | null {
  const trimmed = url?.trim();
  if (!trimmed) return null;
  return trimmed.replace(/\/+$/, '');
}

function getEnvBaseUrl(): string | null {
  const env = (globalThis as ProcessWithEnv).process?.env;
  return normalizeBaseUrl(
    env?.EXPO_PUBLIC_API_BASE_URL ?? env?.EXPO_PUBLIC_MEDGEMMA_API_URL,
  );
}

function getBrowserBaseUrl(): string | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return null;
  }

  const { protocol, hostname } = window.location;
  if (!hostname) return null;

  const apiProtocol = protocol === 'https:' ? 'https:' : 'http:';
  return `${apiProtocol}//${hostname}:${DEFAULT_API_PORT}`;
}

function getMetroHostBaseUrl(): string | null {
  const scriptURL: string | undefined = NativeModules.SourceCode?.scriptURL;
  if (!scriptURL) return null;

  try {
    const parsed = new URL(scriptURL);
    if (!/^https?:$/.test(parsed.protocol)) {
      return null;
    }

    return `${parsed.protocol}//${parsed.hostname}:${DEFAULT_API_PORT}`;
  } catch {
    return null;
  }
}

function getPlatformFallbackBaseUrl(): string {
  if (Platform.OS === 'android') {
    return `http://10.0.2.2:${DEFAULT_API_PORT}`;
  }

  return `http://127.0.0.1:${DEFAULT_API_PORT}`;
}

function resolveBaseUrl(override?: string | null): string {
  return (
    normalizeBaseUrl(override) ??
    getEnvBaseUrl() ??
    getBrowserBaseUrl() ??
    getMetroHostBaseUrl() ??
    getPlatformFallbackBaseUrl()
  );
}

let runtimeBaseUrl = resolveBaseUrl();

export function setApiBaseUrl(baseUrl?: string | null) {
  runtimeBaseUrl = resolveBaseUrl(baseUrl);
}

export function getApiBaseUrl(): string {
  return runtimeBaseUrl;
}

export class MedGemmaApiError extends Error {
  constructor(
    public statusCode: number,
    message: string,
  ) {
    super(message);
    this.name = 'MedGemmaApiError';
  }
}

async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs = 60000,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(id);
  }
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 60000,
): Promise<T> {
  const res = await fetchWithTimeout(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: {
      'bypass-tunnel-reminder': 'true',
      'ngrok-skip-browser-warning': 'true',
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  }, timeoutMs);

  if (!res.ok) {
    const text = await res.text();
    throw new MedGemmaApiError(res.status, text || 'API error');
  }

  return res.json();
}

/**
 * Send a chat message to the MedGemma backend.
 */
export async function sendChatMessage(
  request: ApiChatRequest,
): Promise<ApiChatResponse> {
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/chat`, {
    method: 'POST',
    headers: {
      'bypass-tunnel-reminder': 'true',
      'ngrok-skip-browser-warning': 'true',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    const isTunnelError =
      res.status === 503 && /tunnel unavailable/i.test(text);
    const message = isTunnelError
      ? 'Backend tunnel is unavailable. Start the local backend on port 8000 or set EXPO_PUBLIC_API_BASE_URL / apiBaseUrl to a reachable server.'
      : text || 'API error';
    throw new MedGemmaApiError(res.status, message);
  }

  return res.json();
}

export async function fetchVisitQueue(
  workerId: string,
  date: string,
): Promise<{ visits: VisitQueueItem[] }> {
  return requestJson(`/workers/${encodeURIComponent(workerId)}/visits?date=${encodeURIComponent(date)}`, {
    method: 'GET',
  });
}

export async function fetchVisitScenario(visitId: string): Promise<ScenarioContext> {
  return requestJson(`/visits/${encodeURIComponent(visitId)}`, {
    method: 'GET',
  });
}

export async function updatePatientProfile(patient: PatientInfo): Promise<ScenarioContext> {
  return requestJson(`/patients/${encodeURIComponent(patient.id)}/profile`, {
    method: 'PATCH',
    body: JSON.stringify(patient),
  });
}

export async function startVisit(
  visitId: string,
  workerId: string,
  checkIn?: LocationSnapshot,
): Promise<ScenarioContext> {
  return requestJson(`/visits/${encodeURIComponent(visitId)}/start`, {
    method: 'POST',
    body: JSON.stringify({ workerId, checkIn }),
  });
}

export async function completeTask(
  visitId: string,
  taskId: string,
  workerId: string,
): Promise<ScenarioContext> {
  return requestJson(`/visits/${encodeURIComponent(visitId)}/tasks/${encodeURIComponent(taskId)}/complete`, {
    method: 'POST',
    body: JSON.stringify({ workerId, status: 'completed' }),
  });
}

export async function updateTaskStatus(
  visitId: string,
  taskId: string,
  status: CareTaskStatus,
  workerId: string,
): Promise<ScenarioContext> {
  return requestJson(`/visits/${encodeURIComponent(visitId)}/tasks/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status, workerId }),
  });
}

export async function reportTaskIssue(
  visitId: string,
  taskId: string,
  type: 'cannot_complete' | 'patient_declined' | 'safety_concern',
  workerId: string,
): Promise<ScenarioContext> {
  return requestJson(`/visits/${encodeURIComponent(visitId)}/tasks/${encodeURIComponent(taskId)}/issue`, {
    method: 'POST',
    body: JSON.stringify({ type, workerId }),
  });
}

export async function finishVisit(
  visitId: string,
  workerId: string,
  checkOut?: LocationSnapshot,
): Promise<ScenarioContext> {
  return requestJson(`/visits/${encodeURIComponent(visitId)}/complete`, {
    method: 'POST',
    body: JSON.stringify({ workerId, checkOut }),
  });
}

/**
 * Upload a file/image and get back a reference ID.
 */
export async function uploadFile(
  base64: string,
  mimeType: string,
  filename: string,
): Promise<{ fileId: string; url: string }> {
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/upload`, {
    method: 'POST',
    headers: {
      'bypass-tunnel-reminder': 'true',
      'ngrok-skip-browser-warning': 'true',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ base64, mimeType, filename }),
  });

  if (!res.ok) {
    throw new MedGemmaApiError(res.status, 'Upload failed');
  }

  return res.json();
}

/**
 * Health check — use to verify the backend is reachable.
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetchWithTimeout(
      `${getApiBaseUrl()}/health`,
      { method: 'GET' },
      5000,
    );
    return res.ok;
  } catch {
    return false;
  }
}
