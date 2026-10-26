// src/screens/ChatScreen.tsx
//
// ── Drop-in usage ────────────────────────────────────────────────────────────
//   import { ChatScreen } from './c3a-core-ui/src/screens/ChatScreen';
//   // Use as a full screen or inside a Stack/Tab navigator.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  StatusBar,
  Keyboard,
  Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { useTranslation } from 'react-i18next';

import { ChatBubble } from '../components/ChatBubble';
import { ChatInput } from '../components/ChatInput';
import { AttachmentMenu } from '../components/AttachmentMenu';
import { HistorySidebar } from '../components/HistorySidebar';
import { PatientModal } from '../components/PatientModal';

import { useChatStore } from '../store/chatStore';
import { useChat } from '../hooks/useChat';
import { setApiBaseUrl } from '../services/api';
import { Attachment, Message, PatientInfo } from '../types';

// ── Optional: initialise i18n if not done by the host app ───────────────────
import '../i18n';

interface Props {
  /** Override the API base URL at runtime */
  apiBaseUrl?: string;
  /** Called when the user presses ✕ (close) — omit to hide the button */
  onClose?: () => void;
}

export const ChatScreen: React.FC<Props> = ({ apiBaseUrl, onClose }) => {
  const { t } = useTranslation();
  const flatListRef = useRef<FlatList>(null);

  // ── Store ──────────────────────────────────────────────────────────────────
  const {
    sessions,
    activeSession,
    activeSessionId,
    ensureActiveSession,
    addMessage,
    updateMessage,
    deleteSession,
    linkPatient,
    selectSession,
    startNewChat,
  } = useChatStore();

  // ── Chat logic ─────────────────────────────────────────────────────────────
  const { sendMessage, isLoading, error } = useChat({
    ensureActiveSession,
    addMessage,
    updateMessage,
    activeSession,
  });

  // ── Local UI state ─────────────────────────────────────────────────────────
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [patientModalOpen, setPatientModalOpen] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);

  useEffect(() => {
    setApiBaseUrl(apiBaseUrl);
  }, [apiBaseUrl]);

  // Scroll to bottom as streamed assistant content grows.
  useEffect(() => {
    if (activeSession && activeSession.messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [activeSession?.messages.length, activeSession?.messages[activeSession.messages.length - 1]?.content]);

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleSend = useCallback(
    (text: string, attachments: Attachment[]) => {
      Keyboard.dismiss();
      sendMessage(text, attachments);
      setPendingAttachments([]);
    },
    [sendMessage],
  );

  const handleAttachment = useCallback((att: Attachment) => {
    setPendingAttachments((prev) => [...prev, att]);
  }, []);

  const handlePatientSave = useCallback(
    (patient: PatientInfo) => {
      const sessionId = ensureActiveSession();
      linkPatient(sessionId, patient);
      // Also add as attachment chip
      handleAttachment({
        id: patient.id,
        type: 'patient',
        name: patient.name,
      });
    },
    [ensureActiveSession, linkPatient, handleAttachment],
  );

  // ── Render helpers ─────────────────────────────────────────────────────────
  const messages: Message[] = activeSession?.messages ?? [];

  const renderEmpty = () => (
    <View style={styles.emptyState}>
      <View style={styles.botAvatarWrap}>
        <Text style={styles.botAvatarEmoji}>🤖</Text>
      </View>
      <Text style={styles.greetingText}>{t('chat.greeting')}</Text>
    </View>
  );

  const renderTypingIndicator = () =>
    isLoading ? (
      <ChatBubble
        message={{
          id: '__typing__',
          role: 'assistant',
          content: '',
          timestamp: new Date(),
        }}
        isTyping
      />
    ) : null;

  // ── UI ─────────────────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" backgroundColor="#F5FAFA" />

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        {/* ── Header ── */}
        <View style={styles.header}>
          <TouchableOpacity
            style={styles.headerBtn}
            onPress={() => setSidebarOpen(true)}
            activeOpacity={0.7}
          >
            <Text style={styles.hamburger}>☰</Text>
          </TouchableOpacity>

          <View style={styles.headerCenter}>
            <Text style={styles.headerTitle}>{t('chat.title')}</Text>
            {activeSession?.patientInfo && (
              <View style={styles.patientPill}>
                <Text style={styles.patientPillText}>
                  👤 {activeSession.patientInfo.name}
                </Text>
              </View>
            )}
          </View>

          {onClose && (
            <TouchableOpacity
              style={styles.headerBtn}
              onPress={onClose}
              activeOpacity={0.7}
            >
              <Text style={styles.closeIcon}>✕</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* ── Error banner ── */}
        {error && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* ── Message list ── */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          keyExtractor={(m) => m.id}
          ListEmptyComponent={renderEmpty}
          ListFooterComponent={renderTypingIndicator}
          contentContainerStyle={[
            styles.listContent,
            messages.length === 0 && styles.listContentEmpty,
          ]}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => <ChatBubble message={item} />}
        />

        {/* ── Input ── */}
        <ChatInput
          onSend={handleSend}
          onPressPlus={() => setAttachMenuOpen(true)}
          isLoading={isLoading}
          pendingAttachments={pendingAttachments}
          onRemoveAttachment={(id) =>
            setPendingAttachments((prev) => prev.filter((a) => a.id !== id))
          }
        />
      </KeyboardAvoidingView>

      {/* ── History Sidebar ── */}
      <HistorySidebar
        visible={sidebarOpen}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={selectSession}
        onDelete={deleteSession}
        onNewChat={startNewChat}
        onClose={() => setSidebarOpen(false)}
      />

      {/* ── Attachment Menu ── */}
      <AttachmentMenu
        visible={attachMenuOpen}
        onClose={() => setAttachMenuOpen(false)}
        onLinkPatient={() => setPatientModalOpen(true)}
      />

      {/* ── Patient Modal ── */}
      <PatientModal
        visible={patientModalOpen}
        initial={activeSession?.patientInfo}
        onSave={handlePatientSave}
        onClose={() => setPatientModalOpen(false)}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F5FAFA' },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#F5FAFA',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#D5E8E8',
  },
  headerBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hamburger: { fontSize: 20, color: '#0D7377' },
  closeIcon: { fontSize: 16, color: '#6A9999' },
  headerCenter: { flex: 1, alignItems: 'center' },
  headerTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#0D7377',
    letterSpacing: 0.2,
  },
  patientPill: {
    marginTop: 3,
    backgroundColor: '#D1F0F0',
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  patientPillText: { fontSize: 11, color: '#0D7377', fontWeight: '600' },
  errorBanner: {
    backgroundColor: '#FFF0F0',
    borderLeftWidth: 3,
    borderLeftColor: '#E05C5C',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  errorText: { color: '#C0404040', fontSize: 13 },
  listContent: { paddingTop: 12, paddingBottom: 8 },
  listContentEmpty: { flexGrow: 1 },
  emptyState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
    gap: 20,
  },
  botAvatarWrap: {
    width: 90,
    height: 90,
    borderRadius: 22,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#0D7377',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 5,
  },
  botAvatarEmoji: { fontSize: 42 },
  greetingText: {
    fontSize: 22,
    fontWeight: '700',
    color: '#1A2B2B',
    textAlign: 'center',
  },
});
