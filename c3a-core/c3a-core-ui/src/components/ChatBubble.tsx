// src/components/ChatBubble.tsx
import React from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { ChatSourceKind, Message } from '../types';

interface Props {
  message: Message;
  isTyping?: boolean;
}

export const ChatBubble: React.FC<Props> = ({ message, isTyping }) => {
  const isUser = message.role === 'user';

  return (
    <View
      style={[
        styles.container,
        isUser ? styles.userContainer : styles.assistantContainer,
      ]}
    >
      <View
        style={[
          styles.bubble,
          isUser ? styles.userBubble : styles.assistantBubble,
        ]}
      >
        {isTyping ? (
          <ActivityIndicator size="small" color="#0D7377" />
        ) : (
          <>
            <Text
              style={[
                styles.text,
                isUser ? styles.userText : styles.assistantText,
              ]}
            >
              {message.content}
            </Text>
            {message.attachments?.map((att) =>
              att.type === 'image' && att.uri ? (
                <Image
                  key={att.id}
                  source={{ uri: att.uri }}
                  style={styles.attachmentImage}
                  resizeMode="cover"
                />
              ) : att.type === 'patient' ? (
                <View key={att.id} style={styles.patientTag}>
                  <Text style={styles.patientTagText}>👤 {att.name}</Text>
                </View>
              ) : att.type === 'file' ? (
                <View key={att.id} style={styles.fileTag}>
                  <Text style={styles.fileTagText}>📎 {att.name}</Text>
                </View>
              ) : null,
            )}
            {!isUser && message.sources && message.sources.length > 0 ? (
              <View style={styles.sourcesSection}>
                <Text style={styles.sourcesHeading}>Sources used</Text>
                {message.sources.map((source) => {
                  const page = formatPage(source.pageStart, source.pageEnd);
                  const details = [source.section, page, ...(source.recordTypes ?? [])]
                    .filter(Boolean)
                    .join(' · ');
                  return (
                    <View key={source.id} style={styles.sourceRow}>
                      <View style={[styles.sourceKind, sourceKindStyles[source.kind]]}>
                        <Text style={styles.sourceKindText}>{sourceKindLabels[source.kind]}</Text>
                      </View>
                      <View style={styles.sourceContent}>
                        <Text style={styles.sourceLabel}>{source.label}</Text>
                        {details ? <Text style={styles.sourceDetails}>{details}</Text> : null}
                        <Text style={styles.sourceReason}>{source.reason}</Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : null}
          </>
        )}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    marginVertical: 6,
    paddingHorizontal: 12,
    alignItems: 'flex-end',
  },
  userContainer: { justifyContent: 'flex-end' },
  assistantContainer: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '72%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    elevation: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 2,
  },
  userBubble: {
    backgroundColor: '#0D7377',
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: '#FFFFFF',
    borderBottomLeftRadius: 4,
    maxWidth: '88%',
  },
  text: { fontSize: 15, lineHeight: 21 },
  userText: { color: '#FFFFFF' },
  assistantText: { color: '#1A2B2B' },
  attachmentImage: {
    width: 180,
    height: 120,
    borderRadius: 10,
    marginTop: 8,
  },
  patientTag: {
    marginTop: 6,
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  patientTagText: { color: '#fff', fontSize: 12 },
  fileTag: {
    marginTop: 6,
    backgroundColor: '#F0F7F7',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  fileTagText: { color: '#0D7377', fontSize: 12 },
  sourcesSection: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#C9D7D5',
    marginTop: 12,
    paddingTop: 10,
  },
  sourcesHeading: {
    color: '#284443',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 2,
  },
  sourceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 7,
  },
  sourceKind: {
    borderRadius: 4,
    marginRight: 8,
    marginTop: 1,
    minWidth: 62,
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  sourceKindText: {
    color: '#263332',
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
  },
  sourceContent: {
    flex: 1,
    minWidth: 0,
  },
  sourceLabel: {
    color: '#183837',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
  },
  sourceDetails: {
    color: '#526563',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 1,
  },
  sourceReason: {
    color: '#526563',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 2,
  },
});

const sourceKindLabels: Record<ChatSourceKind, string> = {
  guideline: 'Guideline',
  patient_record: 'Patient',
  visit_context: 'Visit',
  general_knowledge: 'General',
};

const sourceKindStyles: Record<ChatSourceKind, { backgroundColor: string }> = {
  guideline: { backgroundColor: '#DCEDEA' },
  patient_record: { backgroundColor: '#E8E3F0' },
  visit_context: { backgroundColor: '#F2E8CF' },
  general_knowledge: { backgroundColor: '#E6EAED' },
};

function formatPage(pageStart?: number, pageEnd?: number): string | null {
  if (pageStart == null) return null;
  if (pageEnd == null || pageStart === pageEnd) return `p. ${pageStart}`;
  return `pp. ${pageStart}-${pageEnd}`;
}
