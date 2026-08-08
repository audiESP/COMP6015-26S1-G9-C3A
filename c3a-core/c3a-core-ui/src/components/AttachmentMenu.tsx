// src/components/AttachmentMenu.tsx
import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  StyleSheet,
} from 'react-native';
import { useTranslation } from 'react-i18next';

interface Props {
  visible: boolean;
  onClose: () => void;
  onLinkPatient: () => void;
}

export const AttachmentMenu: React.FC<Props> = ({
  visible,
  onClose,
  onLinkPatient,
}) => {
  const { t } = useTranslation();

  const handleLinkPatient = () => {
    onClose();
    onLinkPatient();
  };

  const menuItems = [
    {
      icon: '👤',
      label: t('attachment.linkPatient'),
      onPress: handleLinkPatient,
    },
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
