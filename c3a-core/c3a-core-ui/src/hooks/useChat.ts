// src/hooks/useChat.ts
import { useState, useCallback } from 'react';
import { sendChatMessage, MedGemmaApiError } from '../services/api';
import { Attachment, PatientInfo } from '../types';

interface UseChatOptions {
  ensureActiveSession: () => string;
  addMessage: (
    sessionId: string,
    msg: { role: 'user' | 'assistant'; content: string; attachments?: Attachment[] },
  ) => void;
  activeSession: { messages: any[]; patientInfo?: PatientInfo } | null;
}

export function useChat({
  ensureActiveSession,
  addMessage,
  activeSession,
}: UseChatOptions) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (text: string, attachments: Attachment[] = []) => {
      if (!text.trim() && attachments.length === 0) return;
      setError(null);

      const sessionId = ensureActiveSession();

      // Add user message immediately (optimistic)
      addMessage(sessionId, {
        role: 'user',
        content: text.trim(),
        attachments,
      });

      setIsLoading(true);
      try {
        const history = (activeSession?.messages ?? []).map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const apiAttachments = attachments
          .filter((a) => a.base64 && a.mimeType)
          .map((a) => ({
            type: a.type,
            base64: a.base64!,
            mimeType: a.mimeType!,
          }));

        const response = await sendChatMessage({
          messages: [{ role: 'user', content: text.trim() }],
          patientContext: activeSession?.patientInfo,
          attachments: apiAttachments,
        });

        addMessage(sessionId, {
          role: 'assistant',
          content: response.reply,
        });
      } catch (err) {
        const msg =
          err instanceof MedGemmaApiError
            ? err.message
            : 'Network error. Please try again.';
        setError(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [ensureActiveSession, addMessage, activeSession],
  );

  return { sendMessage, isLoading, error, clearError: () => setError(null) };
}
