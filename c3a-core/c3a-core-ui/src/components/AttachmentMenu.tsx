import tw from '../ui/tw';
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

const styles = {
  overlay: tw.style('flex-1 justify-end pb-[100px] px-[16px]', {"backgroundColor":"rgba(0,0,0,0.35)"}),
  menu: tw.style('bg-white rounded-[16px] overflow-hidden', {"elevation":8,"shadowColor":"#000","shadowOffset":{"width":0,"height":4},"shadowOpacity":0.15,"shadowRadius":12}),
  menuTitle: tw.style('text-[13px] font-semibold text-[#9BB5B5] px-[20px] pt-[14px] pb-[8px] tracking-[0.5px] uppercase'),
  menuItem: tw.style('flex-row items-center px-[20px] py-[16px]'),
  menuItemBorder: tw.style('border-b-[0.5px] border-b-[#EDF2F2]'),
  menuIcon: tw.style('text-[22px] mr-[14px]'),
  menuLabel: tw.style('text-[16px] text-care-ink font-medium'),
};
