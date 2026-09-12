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

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  sidebar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: SIDEBAR_W,
    backgroundColor: '#F5FAFA',
    shadowColor: '#000',
    shadowOffset: { width: 4, height: 0 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 56,
    paddingBottom: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#D5E8E8',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0D7377',
  },
  closeBtn: {
    width: 30,
    height: 30,
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeIcon: { fontSize: 16, color: '#6A9999' },
  newChatBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#0D7377',
    borderRadius: 10,
  },
  newChatIcon: { color: '#fff', fontSize: 18, marginRight: 8 },
  newChatText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 },
  emptyIcon: { fontSize: 40 },
  emptyText: { color: '#9BB5B5', fontSize: 14 },
  sessionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 12,
    marginTop: 4,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    overflow: 'hidden',
  },
  activeSession: {
    backgroundColor: '#E6F4F4',
    borderWidth: 1,
    borderColor: '#0D7377',
  },
  sessionMain: { flex: 1, padding: 14 },
  patientBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#D1F0F0',
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginBottom: 4,
  },
  patientBadgeText: { fontSize: 10, color: '#0D7377', fontWeight: '600' },
  sessionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1A2B2B',
    marginBottom: 4,
  },
  sessionDate: { fontSize: 11, color: '#9BB5B5' },
  deleteBtn: {
    padding: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deleteIcon: { fontSize: 16 },
});
