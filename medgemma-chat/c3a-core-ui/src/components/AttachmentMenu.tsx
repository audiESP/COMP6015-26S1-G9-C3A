// src/components/AttachmentMenu.tsx
import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  StyleSheet,
  Platform,
  Alert,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { Attachment } from '../types';

interface Props {
  visible: boolean;
  onClose: () => void;
  onAttachment: (attachment: Attachment) => void;
  onLinkPatient: () => void;
}

export const AttachmentMenu: React.FC<Props> = ({
  visible,
  onClose,
  onAttachment,
  onLinkPatient,
}) => {
  const { t } = useTranslation();

  const handleUploadFile = async () => {
    onClose();
    // In production: use expo-document-picker or react-native-document-picker
    // Example placeholder:
    Alert.alert(
      t('attachment.uploadFile'),
      'Connect expo-document-picker for real file picking.',
      [
        {
          text: 'Simulate',
          onPress: () =>
            onAttachment({
              id: `${Date.now()}`,
              type: 'file',
              name: 'lab_report.pdf',
              mimeType: 'application/pdf',
            }),
        },
        { text: 'Cancel', style: 'cancel' },
      ],
    );
  };

  const handleTakePhoto = async () => {
    onClose();
    // In production: use expo-image-picker
    Alert.alert(t('attachment.takePhoto'), 'Connect expo-image-picker.', [
      {
        text: 'Simulate',
        onPress: () =>
          onAttachment({
            id: `${Date.now()}`,
            type: 'image',
            name: 'photo.jpg',
            mimeType: 'image/jpeg',
          }),
      },
      { text: 'Cancel', style: 'cancel' },
    ]);
  };

  const handleLinkPatient = () => {
    onClose();
    onLinkPatient();
  };

  const menuItems = [
    {
      icon: '📁',
      label: t('attachment.uploadFile'),
      onPress: handleUploadFile,
    },
    {
      icon: '👤',
      label: t('attachment.linkPatient'),
      onPress: handleLinkPatient,
    },
    { icon: '📷', label: t('attachment.takePhoto'), onPress: handleTakePhoto },
  ];

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <TouchableOpacity
        style={styles.overlay}
        activeOpacity={1}
        onPress={onClose}
      >
        <View style={styles.menu}>
          <Text style={styles.menuTitle}>{t('attachment.title')}</Text>
          {menuItems.map((item, idx) => (
            <TouchableOpacity
              key={idx}
              style={[
                styles.menuItem,
                idx < menuItems.length - 1 && styles.menuItemBorder,
              ]}
              onPress={item.onPress}
              activeOpacity={0.7}
            >
              <Text style={styles.menuIcon}>{item.icon}</Text>
              <Text style={styles.menuLabel}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </TouchableOpacity>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'flex-end',
    paddingBottom: 100,
    paddingHorizontal: 16,
  },
  menu: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    overflow: 'hidden',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
  },
  menuTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#9BB5B5',
    paddingHorizontal: 20,
    paddingTop: 14,
    paddingBottom: 8,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  menuItemBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#EDF2F2',
  },
  menuIcon: { fontSize: 22, marginRight: 14 },
  menuLabel: { fontSize: 16, color: '#1A2B2B', fontWeight: '500' },
});
