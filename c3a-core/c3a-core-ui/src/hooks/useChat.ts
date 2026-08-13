// src/hooks/useChat.ts
import { useState, useCallback } from 'react';
import { ApiError, streamChatMessage } from '../services/api';
import { Attachment, PatientInfo, ScenarioContext } from '../types';

interface UseChatOptions {
  ensureActiveSession: () => string;
  addMessage: (
    sessionId: string,
    msg: { role: 'user' | 'assistant'; content: string; attachments?: Attachment[] },
  ) => { id: string };
  updateMessage: (sessionId: string, messageId: string, content: string) => void;
  activeSession: { messages: any[]; patientInfo?: PatientInfo } | null;
  scenarioContext?: ScenarioContext;
}

export function useChat({
  ensureActiveSession,
  addMessage,
  updateMessage,
  activeSession,
  scenarioContext,
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
        const history = (activeSession?.messages ?? [])
          .slice(-12)
          .map((m) => ({
            role: m.role,
            content: m.content,
          }));
        const currentTask = scenarioContext
          ? scenarioContext.tasks.find((task) => ['issue', 'delayed', 'pending'].includes(task.status))
            ?? scenarioContext.tasks[scenarioContext.tasks.length - 1]
          : undefined;

        const apiAttachments = attachments
          .filter((a) => a.base64 && a.mimeType)
          .map((a) => ({
            type: a.type,
            base64: a.base64!,
            mimeType: a.mimeType!,
          }));

        let streamedReply = '';
        let assistantMessageId: string | null = null;
        await streamChatMessage({
          messages: [...history, { role: 'user', content: text.trim() }],
          patientContext: scenarioContext?.patient ?? activeSession?.patientInfo,
          workerContext: scenarioContext?.worker,
          visitContext: scenarioContext?.visit,
          currentTaskContext: currentTask,
          taskContext: scenarioContext?.tasks,
          eventContext: scenarioContext?.events,
          riskContext: scenarioContext?.alerts,
          attachments: apiAttachments,
        }, (event) => {
          if (event.type === 'token') {
            streamedReply += event.content;
            if (assistantMessageId) {
              updateMessage(sessionId, assistantMessageId, streamedReply);
            } else {
              assistantMessageId = addMessage(sessionId, {
                role: 'assistant',
                content: streamedReply,
              }).id;
            }
          } else if (event.type === 'done' && event.appendSources && event.sources?.length) {
            const sources = event.sources
              .map((source, index) => `${index + 1}. ${source}`)
              .join('\n');
            streamedReply = `${streamedReply.trimEnd()}\n\nSources:\n${sources}`;
            if (assistantMessageId) {
              updateMessage(sessionId, assistantMessageId, streamedReply);
            }
          }
        });
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.message
            : 'Network error. Please try again.';
        setError(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [ensureActiveSession, addMessage, updateMessage, activeSession, scenarioContext],
  );

  return { sendMessage, isLoading, error, clearError: () => setError(null) };
}
