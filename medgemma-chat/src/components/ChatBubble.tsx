// src/components/ChatBubble.tsx
import React from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { Message } from '../types';

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
});
