import tw from '../ui/tw';
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

const styles = {
  container: tw.style('flex-row my-[6px] px-[12px] items-end'),
  userContainer: tw.style('justify-end'),
  assistantContainer: tw.style('justify-start'),
  bubble: tw.style('max-w-[72%] px-[14px] py-[10px] rounded-[18px]', {"elevation":1,"shadowColor":"#000","shadowOffset":{"width":0,"height":1},"shadowOpacity":0.06,"shadowRadius":2}),
  userBubble: tw.style('bg-care-primary rounded-br-[4px]'),
  assistantBubble: tw.style('bg-white rounded-bl-[4px] max-w-[88%]'),
  text: tw.style('text-[15px] leading-[21px]'),
  userText: tw.style('text-white'),
  assistantText: tw.style('text-care-ink'),
  attachmentImage: tw.style('w-[180px] h-[120px] rounded-[10px] mt-[8px]'),
  patientTag: tw.style('mt-[6px] rounded-[20px] px-[8px] py-[4px]', {"backgroundColor":"rgba(255,255,255,0.2)"}),
  patientTagText: tw.style('text-[#fff] text-[12px]'),
  fileTag: tw.style('mt-[6px] bg-care-canvas rounded-[20px] px-[8px] py-[4px]'),
  fileTagText: tw.style('text-care-primary text-[12px]'),
  sourcesSection: tw.style('border-t-[0.5px] border-t-[#C9D7D5] mt-[12px] pt-[10px]'),
  sourcesHeading: tw.style('text-[#284443] text-[12px] font-semibold mb-[2px]'),
  sourceRow: tw.style('flex-row items-start py-[7px]'),
  sourceKind: tw.style('rounded-[4px] mr-[8px] mt-[1px] min-w-[62px] px-[6px] py-[3px]'),
  sourceKindText: tw.style('text-[#263332] text-[12px] font-semibold text-center'),
  sourceContent: tw.style('flex-1 min-w-[0px]'),
  sourceLabel: tw.style('text-[#183837] text-[12px] font-semibold leading-[17px]'),
  sourceDetails: tw.style('text-[#526563] text-[12px] leading-[16px] mt-[1px]'),
  sourceReason: tw.style('text-[#526563] text-[12px] leading-[16px] mt-[2px]'),
};

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
