// src/services/api.ts
import { ApiChatRequest, ApiChatResponse, PatientInfo } from '../types';

// ── Configure this to match your deployment ──────────────────────────────────
const BASE_URL = 'https://vast-bushes-take.loca.lt'; // change in production

// ─────────────────────────────────────────────────────────────────────────────

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

/**
 * Send a chat message to the MedGemma backend.
 */
export async function sendChatMessage(
  request: ApiChatRequest,
): Promise<ApiChatResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'bypass-tunnel-reminder': 'true',
      'ngrok-skip-browser-warning': 'true',
      'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new MedGemmaApiError(res.status, text || 'API error');
  }

  return res.json();
}

/**
 * Upload a file/image and get back a reference ID.
 */
export async function uploadFile(
  base64: string,
  mimeType: string,
  filename: string,
): Promise<{ fileId: string; url: string }> {
  const res = await fetchWithTimeout(`${BASE_URL}/upload`, {
    method: 'POST',
    headers: {
        'bypass-tunnel-reminder': 'true','ngrok-skip-browser-warning': 'true', 'Content-Type': 'application/json' },
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
      `${BASE_URL}/health`,
      { method: 'GET' },
      5000,
    );
    return res.ok;
  } catch {
    return false;
  }
}
