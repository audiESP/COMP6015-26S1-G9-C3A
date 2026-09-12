import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, ActivityIndicator, Animated, Modal, PanResponder, Platform, Pressable, ScrollView, Text, TextInput, View, KeyboardAvoidingView, type TextInputProps } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ArrowLeft, X, type LucideIcon } from 'lucide-react-native';
import tw from './tw';

export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    void AccessibilityInfo.isReduceMotionEnabled().then(setReduced);
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced);
    return () => sub.remove();
  }, []);
  return reduced;
}
export function Copy({ children, muted = false, small = false }: { children: React.ReactNode; muted?: boolean; small?: boolean }) {
  return <Text style={tw.style(small ? 'text-xs leading-5' : 'text-sm leading-6', muted ? 'text-care-muted' : 'text-care-ink')}>{children}</Text>;
}
export function Heading({ children }: { children: React.ReactNode }) { return <Text style={tw`text-xl font-semibold text-care-ink leading-7`}>{children}</Text>; }
export function Surface({ children }: { children: React.ReactNode }) { return <View style={tw`bg-care-surface rounded-card p-5 mb-3`}>{children}</View>; }
export function Badge({ children, warning = false }: { children: React.ReactNode; warning?: boolean }) { return <View style={tw.style('self-start px-2.5 py-1 rounded-lg', warning ? 'bg-care-warning' : 'bg-care-soft')}><Text style={tw.style('text-xs font-medium', warning ? 'text-care-amber' : 'text-care-primary')}>{children}</Text></View>; }
export function IconButton({ icon: Icon, label, onPress, disabled = false }: { icon: LucideIcon; label: string; onPress: () => void; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled} onPress={onPress} style={({ pressed }) => tw.style('w-11 h-11 items-center justify-center rounded-control', pressed && 'bg-care-soft', disabled && 'opacity-40')}><Icon size={21} strokeWidth={1.7} color="#176B58" /></Pressable>;
}
export function Button({ label, onPress, secondary, disabled, busy, icon: Icon }: { label: string; onPress: () => void; secondary?: boolean; disabled?: boolean; busy?: boolean; icon?: LucideIcon }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled: !!disabled || !!busy, busy: !!busy }} disabled={disabled || busy} onPress={onPress} style={({ pressed }) => tw.style('min-h-[52px] rounded-control px-4 py-3 flex-row gap-2 items-center justify-center', secondary ? 'bg-care-soft' : 'bg-care-primary', pressed && 'opacity-80', (disabled || busy) && 'opacity-45')}>
    {busy ? <ActivityIndicator color={secondary ? '#176B58' : '#FFFFFF'} /> : Icon ? <Icon size={19} color={secondary ? '#176B58' : '#FFFFFF'} /> : null}
    <Text style={tw.style('text-sm font-semibold text-center', secondary ? 'text-care-primary' : 'text-white')}>{label}</Text>
  </Pressable>;
}
export function Header({ title, eyebrow, onBack, right }: { title: string; eyebrow?: string; onBack?: () => void; right?: React.ReactNode }) {
  return <View style={tw`flex-row items-center gap-2 px-5 pt-4 pb-5`}>
    {onBack && <IconButton icon={ArrowLeft} label="Back" onPress={onBack} />}
    <View style={tw`flex-1`}>{eyebrow && <Text style={tw`text-[10px] uppercase tracking-[1.5px] text-care-muted mb-1`}>{eyebrow}</Text>}<Text style={tw`text-[25px] font-semibold tracking-[-0.7px] text-care-ink`}>{title}</Text></View>{right}
  </View>;
}
export function Section({ title, detail }: { title: string; detail?: string }) { return <View style={tw`flex-row justify-between items-center mt-5 mb-3 gap-3`}><Text style={tw`text-sm font-semibold text-care-ink`}>{title}</Text>{detail && <Text style={tw`text-xs text-care-muted shrink`}>{detail}</Text>}</View>; }
export function Field({ label, ...props }: TextInputProps & { label: string }) { return <View style={tw`mb-4`}><Text style={tw`text-sm font-medium text-care-ink mb-2`}>{label}</Text><TextInput accessibilityLabel={label} placeholderTextColor="#697C75" {...props} style={[tw.style('border border-care-line rounded-control bg-white text-care-ink text-base p-3', props.multiline && 'min-h-[96px]'), props.multiline && { textAlignVertical: 'top' }, props.style]} /></View>; }
export function Options<T extends string>({ label, values, selected, onChange, disabled }: { label: string; values: readonly T[]; selected: T | ''; onChange: (value: T) => void; disabled?: boolean }) {
  return <View style={tw`mb-4`}><Text style={tw`text-sm font-medium text-care-ink mb-2`}>{label}</Text><View style={tw`flex-row flex-wrap gap-2`}>{values.map(value => <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: selected === value, disabled }} disabled={disabled} onPress={() => onChange(value)} style={tw.style('min-h-[44px] px-3 py-3 border rounded-xl justify-center', selected === value ? 'bg-care-primary border-care-primary' : 'bg-white border-care-line')}><Text style={tw.style('text-xs font-medium', selected === value ? 'text-white' : 'text-care-ink')}>{value}</Text></Pressable>)}</View></View>;
}
export function Notice({ text, error = false }: { text?: string | null; error?: boolean }) { return text ? <View accessibilityLiveRegion="polite" style={tw.style('rounded-control p-3 mb-3', error ? 'bg-care-blush' : 'bg-care-soft')}><Text style={tw.style('text-sm leading-5', error ? 'text-care-danger' : 'text-care-primary')}>{text}</Text></View> : null; }
export function Sheet({ visible, title, onClose, children, footer, busy = false }: { visible: boolean; title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode; busy?: boolean }) {
  const inset = useSafeAreaInsets();
  const reduced = useReducedMotion();
  const offset = useRef(new Animated.Value(0)).current;
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const busyRef = useRef(busy); busyRef.current = busy;
  const pan = useRef(PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => !busyRef.current && g.dy > 8 && Math.abs(g.dy) > Math.abs(g.dx),
    onPanResponderMove: (_, g) => offset.setValue(Math.max(0, g.dy)),
    onPanResponderRelease: (_, g) => { if (g.dy > 80) closeRef.current(); Animated.spring(offset, { toValue: 0, useNativeDriver: true }).start(); },
    onPanResponderTerminate: () => offset.setValue(0),
  })).current;
  useEffect(() => { if (visible) offset.setValue(0); }, [visible, offset]);
  return <Modal visible={visible} transparent animationType={reduced ? 'none' : 'slide'} onRequestClose={() => !busy && onClose()} statusBarTranslucent>
    <KeyboardAvoidingView style={tw`flex-1 justify-end bg-black/35`} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Pressable accessibilityLabel="Close panel" accessibilityRole="button" disabled={busy} onPress={onClose} style={tw`absolute inset-0`} />
      <Animated.View accessibilityViewIsModal style={[tw`w-full max-w-[600px] self-center max-h-[92%] bg-white rounded-t-[28px] overflow-hidden`, { transform: [{ translateY: offset }], paddingBottom: Math.max(inset.bottom, 16) }]}>
        <View {...pan.panHandlers} style={tw`h-8 items-center justify-center`}><View style={tw`w-10 h-1 rounded-full bg-care-line`} /></View>
        <View style={tw`flex-row items-center px-5 pb-3`}><View style={tw`flex-1`}><Heading>{title}</Heading></View><IconButton icon={X} label="Close panel" onPress={onClose} disabled={busy} /></View>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={tw`px-5 pb-3`} style={tw`shrink`} showsVerticalScrollIndicator={false}>{children}</ScrollView>
        {footer && <View style={tw`px-5 pt-3`}>{footer}</View>}
      </Animated.View>
    </KeyboardAvoidingView>
  </Modal>;
}
