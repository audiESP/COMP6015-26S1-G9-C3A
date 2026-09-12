import React, { useRef, useState } from 'react';
import { Animated, PanResponder, Pressable, Text, View } from 'react-native';
import { Check, CircleAlert, Ellipsis, SquarePen } from 'lucide-react-native';
import type { CareTask } from '../types';
import { IconButton, useReducedMotion } from './primitives';
import tw from './tw';

// A swipe only reveals explicit actions. It never commits clinical data.
export function SwipeTask({ task, index, onRecord, onIssue, disabled }: { task: CareTask; index: number; onRecord: () => void; onIssue: () => void; disabled: boolean }) {
  const x = useRef(new Animated.Value(0)).current;
  const [open, setOpen] = useState(false);
  const start = useRef(0); const blocked = useRef(disabled); blocked.current = disabled;
  const reduced = useReducedMotion(); const reducedRef = useRef(reduced); reducedRef.current = reduced;
  const reveal = (value: boolean) => { setOpen(value); start.current = value ? -144 : 0; Animated.timing(x, { toValue: start.current, duration: reducedRef.current ? 0 : 220, useNativeDriver: true }).start(); };
  const pan = useRef(PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => !blocked.current && Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) * 1.4,
    onPanResponderMove: (_, g) => x.setValue(Math.max(-144, Math.min(0, start.current + g.dx))),
    onPanResponderRelease: (_, g) => reveal(start.current + g.dx < -65),
    onPanResponderTerminate: () => reveal(false),
  })).current;
  return <View style={tw`rounded-[18px] overflow-hidden mb-2 bg-care-soft`}>
    <View accessibilityElementsHidden={!open} importantForAccessibility={open ? 'auto' : 'no-hide-descendants'} style={tw`absolute right-0 top-0 bottom-0 w-36 flex-row`}>
      <Pressable disabled={!open || disabled} onPress={() => { reveal(false); onRecord(); }} accessibilityRole="button" accessibilityLabel={`Record ${task.label}`} style={tw`flex-1 items-center justify-center gap-1`}><SquarePen size={20} color="#176B58" /><Text style={tw`text-xs text-care-primary`}>Record</Text></Pressable>
      <Pressable disabled={!open || disabled} onPress={() => { reveal(false); onIssue(); }} accessibilityRole="button" accessibilityLabel={`Report issue for ${task.label}`} style={tw`flex-1 bg-care-warning items-center justify-center gap-1`}><CircleAlert size={20} color="#80551C" /><Text style={tw`text-xs text-care-amber`}>Issue</Text></Pressable>
    </View>
    <Animated.View {...pan.panHandlers} style={[tw`bg-white flex-row items-center p-3 gap-2 min-h-[78px]`, { transform: [{ translateX: x }] }]}>
      <Pressable accessibilityRole="button" disabled={disabled} onPress={() => open ? reveal(false) : onRecord()} style={tw`flex-1 flex-row items-center gap-3 min-h-[48px]`}>
        <View style={tw`w-7 h-7 border border-care-line rounded-full items-center justify-center`}>{task.status === 'completed' ? <Check size={15} color="#176B58" /> : <Text style={tw`text-xs text-care-muted`}>{index + 1}</Text>}</View>
        <View style={tw`flex-1`}><Text style={tw`text-sm text-care-ink font-medium`}>{task.label}</Text><Text style={tw.style('text-xs mt-1', ['issue', 'delayed', 'skipped'].includes(task.status) ? 'text-care-amber' : 'text-care-muted')}>{task.dueAt ? `${task.dueAt} · ` : ''}{task.status.replace('_', ' ')}</Text></View>
      </Pressable>
      <IconButton icon={Ellipsis} label={`More actions for ${task.label}`} disabled={disabled} onPress={() => reveal(!open)} />
    </Animated.View>
  </View>;
}
