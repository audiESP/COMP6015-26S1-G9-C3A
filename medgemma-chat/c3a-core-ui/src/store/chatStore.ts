// src/store/chatStore.ts
import { useState, useCallback } from 'react';
import { ChatSession, Message, PatientInfo, Attachment } from '../types';

let _sessionCounter = 1;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function generateSessionTitle(firstMessage: string): string {
  return firstMessage.length > 40
    ? firstMessage.slice(0, 40) + '…'
    : firstMessage;
}

/**
 * Simple in-memory store hook. Replace with AsyncStorage / Redux / Zustand
 * for persistence across app restarts.
 */
export function useChatStore() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  const createSession = useCallback((): ChatSession => {
    const session: ChatSession = {
      id: generateId(),
      title: `Conversation ${_sessionCounter++}`,
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(session.id);
    return session;
  }, []);

  const ensureActiveSession = useCallback((): string => {
    if (activeSessionId) return activeSessionId;
    const session = {
      id: generateId(),
      title: `Conversation ${_sessionCounter++}`,
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(session.id);
    return session.id;
  }, [activeSessionId]);

  const addMessage = useCallback(
    (sessionId: string, message: Omit<Message, 'id' | 'timestamp'>) => {
      const msg: Message = {
        ...message,
        id: generateId(),
        timestamp: new Date(),
      };
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== sessionId) return s;
          const messages = [...s.messages, msg];
          return {
            ...s,
            messages,
            updatedAt: new Date(),
            title:
              s.messages.length === 0 && message.role === 'user'
                ? generateSessionTitle(message.content)
                : s.title,
          };
        }),
      );
      return msg;
    },
    [],
  );

  const deleteSession = useCallback(
    (sessionId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
    },
    [activeSessionId],
  );

  const linkPatient = useCallback(
    (sessionId: string, patient: PatientInfo) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId ? { ...s, patientInfo: patient } : s,
        ),
      );
    },
    [],
  );

  const selectSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  const startNewChat = useCallback(() => {
    setActiveSessionId(null);
  }, []);

  return {
    sessions,
    activeSession,
    activeSessionId,
    createSession,
    ensureActiveSession,
    addMessage,
    deleteSession,
    linkPatient,
    selectSession,
    startNewChat,
  };
}
