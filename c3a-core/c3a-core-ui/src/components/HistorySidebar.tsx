import tw from '../ui/tw';
// src/components/HistorySidebar.tsx
import React, { useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  FlatList,
  StyleSheet,
  Animated,
  Alert,
  Dimensions,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { ChatSession } from '../types';

const { width: SCREEN_W } = Dimensions.get('window');
const SIDEBAR_W = Math.min(SCREEN_W * 0.78, 320);

interface Props {
  visible: boolean;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onNewChat: () => void;
  onClose: () => void;
}

export const HistorySidebar: React.FC<Props> = ({
  visible,
  sessions,
  activeSessionId,
  onSelect,
  onDelete,
  onNewChat,
  onClose,
}) => {
  const { t } = useTranslation();
  const slideAnim = useRef(new Animated.Value(-SIDEBAR_W)).current;

  React.useEffect(() => {
    Animated.timing(slideAnim, {
      toValue: visible ? 0 : -SIDEBAR_W,
      duration: 280,
      useNativeDriver: true,
    }).start();
  }, [visible]);

  const confirmDelete = (session: ChatSession) => {
    Alert.alert(t('history.deleteConfirm'), session.title, [
      { text: t('history.cancel'), style: 'cancel' },
      {
        text: t('history.delete'),
        style: 'destructive',
        onPress: () => onDelete(session.id),
      },
    ]);
  };

  const formatDate = (date: Date) => {
    const d = new Date(date);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  if (!visible) return null;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      {/* Backdrop */}
      <TouchableOpacity
        style={styles.backdrop}
        activeOpacity={1}
        onPress={onClose}
      />

      {/* Sidebar panel */}
      <Animated.View
        style={[styles.sidebar, { transform: [{ translateX: slideAnim }] }]}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{t('history.title')}</Text>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Text style={styles.closeIcon}>✕</Text>
          </TouchableOpacity>
        </View>

        {/* New chat button */}
        <TouchableOpacity
          style={styles.newChatBtn}
          onPress={() => {
            onNewChat();
            onClose();
          }}
          activeOpacity={0.8}
        >
          <Text style={styles.newChatIcon}>＋</Text>
          <Text style={styles.newChatText}>New Chat</Text>
        </TouchableOpacity>

        {/* Session list */}
        {sessions.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>💬</Text>
            <Text style={styles.emptyText}>{t('history.empty')}</Text>
          </View>
        ) : (
          <FlatList
            data={sessions}
            keyExtractor={(item) => item.id}
            showsVerticalScrollIndicator={false}
            contentContainerStyle={{ paddingBottom: 24 }}
            renderItem={({ item }) => (
              <View
                style={[
                  styles.sessionItem,
                  item.id === activeSessionId && styles.activeSession,
                ]}
              >
                <TouchableOpacity
                  style={styles.sessionMain}
                  onPress={() => {
                    onSelect(item.id);
                    onClose();
                  }}
                  activeOpacity={0.7}
                >
                  {item.patientInfo && (
                    <View style={styles.patientBadge}>
                      <Text style={styles.patientBadgeText}>
                        👤 {item.patientInfo.name}
                      </Text>
                    </View>
                  )}
                  <Text style={styles.sessionTitle} numberOfLines={2}>
                    {item.title}
                  </Text>
                  <Text style={styles.sessionDate}>
                    {formatDate(item.updatedAt)} · {item.messages.length} msgs
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.deleteBtn}
                  onPress={() => confirmDelete(item)}
                  activeOpacity={0.7}
                >
                  <Text style={styles.deleteIcon}>🗑</Text>
                </TouchableOpacity>
              </View>
            )}
          />
        )}
      </Animated.View>
    </View>
  );
};

const styles = {
  backdrop: tw.style('', {"backgroundColor":"rgba(0,0,0,0.3)"}),
  sidebar: tw.style('absolute left-[0px] top-[0px] bottom-[0px] w-[320px] bg-care-canvas', {"shadowColor":"#000","shadowOffset":{"width":4,"height":0},"shadowOpacity":0.12,"shadowRadius":16,"elevation":12}),
  header: tw.style('flex-row items-center justify-between px-[20px] pt-[56px] pb-[16px] border-b-[0.5px] border-b-care-line'),
  headerTitle: tw.style('text-[18px] font-semibold text-care-primary'),
  closeBtn: tw.style('w-[30px] h-[30px] items-center justify-center'),
  closeIcon: tw.style('text-[16px] text-[#6A9999]'),
  newChatBtn: tw.style('flex-row items-center mx-[16px] mt-[12px] mb-[8px] px-[14px] py-[10px] bg-care-primary rounded-[10px]'),
  newChatIcon: tw.style('text-[#fff] text-[18px] mr-[8px]'),
  newChatText: tw.style('text-[#fff] font-semibold text-[14px]'),
  empty: tw.style('flex-1 items-center justify-center gap-[10px]'),
  emptyIcon: tw.style('text-[40px]'),
  emptyText: tw.style('text-[#9BB5B5] text-[14px]'),
  sessionItem: tw.style('flex-row items-center mx-[12px] mt-[4px] rounded-[12px] bg-white overflow-hidden'),
  activeSession: tw.style('bg-[#E6F4F4] border-[1px] border-care-primary'),
  sessionMain: tw.style('flex-1 p-[14px]'),
  patientBadge: tw.style('self-start bg-[#D1F0F0] rounded-[6px] px-[6px] py-[2px] mb-[4px]'),
  patientBadgeText: tw.style('text-[12px] text-care-primary font-semibold'),
  sessionTitle: tw.style('text-[14px] font-semibold text-care-ink mb-[4px]'),
  sessionDate: tw.style('text-[12px] text-[#9BB5B5]'),
  deleteBtn: tw.style('p-[14px] items-center justify-center'),
  deleteIcon: tw.style('text-[16px]'),
};
