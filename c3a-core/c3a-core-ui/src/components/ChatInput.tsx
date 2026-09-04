// src/components/ChatInput.tsx
import React, { useState, useRef } from 'react';
import {
  View,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Text,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { Attachment } from '../types';

interface Props {
  onSend: (text: string, attachments: Attachment[]) => void;
  onPressPlus: () => void;
  isLoading: boolean;
  pendingAttachments: Attachment[];
  onRemoveAttachment: (id: string) => void;
}

export const ChatInput: React.FC<Props> = ({
  onSend,
  onPressPlus,
  isLoading,
  pendingAttachments,
  onRemoveAttachment,
}) => {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const inputRef = useRef<TextInput>(null);

  const handleSend = () => {
    if ((!text.trim() && pendingAttachments.length === 0) || isLoading) return;
    onSend(text.trim(), pendingAttachments);
    setText('');
  };

  const canSend = (text.trim().length > 0 || pendingAttachments.length > 0) && !isLoading;

  return (
    <View style={styles.wrapper}>
      {/* Pending attachments preview */}
      {pendingAttachments.length > 0 && (
        <View style={styles.attachmentsRow}>
          {pendingAttachments.map((att) => (
            <View key={att.id} style={styles.attChip}>
              <Text style={styles.attChipIcon}>
                {att.type === 'image' ? '🖼' : att.type === 'patient' ? '👤' : '📎'}
              </Text>
              <Text style={styles.attChipLabel} numberOfLines={1}>
                {att.name}
              </Text>
              <TouchableOpacity
                onPress={() => onRemoveAttachment(att.id)}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Text style={styles.attChipRemove}>✕</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      {/* Input row */}
      <View style={styles.row}>
        <TouchableOpacity
          style={styles.plusBtn}
          onPress={onPressPlus}
          activeOpacity={0.7}
          disabled={isLoading}
        >
          <Text style={styles.plusIcon}>＋</Text>
        </TouchableOpacity>

        <TextInput
          ref={inputRef}
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={t('chat.placeholder')}
          placeholderTextColor="#A8C0C0"
          multiline
          onSubmitEditing={handleSend}
          returnKeyType="send"
          blurOnSubmit={false}
        />

        <TouchableOpacity
          style={[styles.sendBtn, canSend && styles.sendBtnActive]}
          onPress={handleSend}
          disabled={!canSend}
          activeOpacity={0.8}
        >
          {isLoading ? (
            <ActivityIndicator size="small" color="#FFFFFF" />
          ) : (
            <Text style={styles.sendIcon}>▶</Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: '#F0F7F7',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#D5E8E8',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 12,
  },
  attachmentsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  attChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderWidth: 1,
    borderColor: '#C5DEDE',
    maxWidth: 160,
  },
  attChipIcon: { fontSize: 12, marginRight: 4 },
  attChipLabel: { fontSize: 12, color: '#0D7377', flex: 1 },
  attChipRemove: { fontSize: 10, color: '#9BB5B5', marginLeft: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: '#FFFFFF',
    borderRadius: 26,
    borderWidth: 1,
    borderColor: '#D5E8E8',
    paddingHorizontal: 4,
    paddingVertical: 4,
    shadowColor: '#0D7377',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  plusBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#E8F4F4',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 4,
  },
  plusIcon: { fontSize: 20, color: '#0D7377', lineHeight: 22 },
  input: {
    flex: 1,
    fontSize: 15,
    color: '#1A2B2B',
    maxHeight: 120,
    paddingHorizontal: 4,
    paddingVertical: 6,
  },
  sendBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#C5DEDE',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 4,
  },
  sendBtnActive: { backgroundColor: '#0D7377' },
  sendIcon: { color: '#FFFFFF', fontSize: 14, marginLeft: 2 },
});
