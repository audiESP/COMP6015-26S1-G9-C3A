import tw from '../ui/tw';
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
  onFocus?: () => void;
  isLoading: boolean;
  pendingAttachments: Attachment[];
  onRemoveAttachment: (id: string) => void;
}

export const ChatInput: React.FC<Props> = ({
  onSend,
  onPressPlus,
  onFocus,
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
          onFocus={onFocus}
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

const styles = {
  wrapper: tw.style('bg-care-canvas border-t-[0.5px] border-t-care-line px-[12px] pt-[8px] pb-[12px]'),
  attachmentsRow: tw.style('flex-row flex-wrap gap-[6px] mb-[8px]'),
  attChip: tw.style('flex-row items-center bg-white rounded-[20px] px-[10px] py-[5px] border-[1px] border-[#C5DEDE] max-w-[160px]'),
  attChipIcon: tw.style('text-[12px] mr-[4px]'),
  attChipLabel: tw.style('text-[12px] text-care-primary flex-1'),
  attChipRemove: tw.style('text-[12px] text-[#9BB5B5] ml-[4px]'),
  row: tw.style('flex-row items-end bg-white rounded-[26px] border-[1px] border-care-line px-[4px] py-[4px]', {"shadowColor":"#0D7377","shadowOffset":{"width":0,"height":2},"shadowOpacity":0.06,"shadowRadius":6,"elevation":2}),
  plusBtn: tw.style('w-[38px] h-[38px] rounded-[19px] bg-care-soft items-center justify-center mr-[4px]'),
  plusIcon: tw.style('text-[20px] text-care-primary leading-[22px]'),
  input: tw.style('flex-1 text-[15px] text-care-ink max-h-[120px] px-[4px] py-[6px]'),
  sendBtn: tw.style('w-[38px] h-[38px] rounded-[19px] bg-[#C5DEDE] items-center justify-center ml-[4px]'),
  sendBtnActive: tw.style('bg-care-primary'),
  sendIcon: tw.style('text-white text-[14px] ml-[2px]'),
};
