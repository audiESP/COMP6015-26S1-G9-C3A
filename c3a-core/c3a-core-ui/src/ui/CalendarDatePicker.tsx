import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react-native';
import { IconButton } from './primitives';
import tw from './tw';

const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function parseDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return new Date();
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
  return Number.isFinite(date.getTime()) ? date : new Date();
}

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function CalendarDatePicker({ value, onChange, markedDates = [], onVisibleMonthChange, markersLoading = false }: { value: string; onChange: (date: string) => void; markedDates?: readonly string[]; onVisibleMonthChange?: (month: string) => void; markersLoading?: boolean }) {
  const selected = useMemo(() => parseDate(value), [value]);
  const marked = useMemo(() => new Set(markedDates), [markedDates]);
  const [visibleMonth, setVisibleMonth] = useState(() => new Date(selected.getFullYear(), selected.getMonth(), 1, 12));

  useEffect(() => {
    setVisibleMonth(new Date(selected.getFullYear(), selected.getMonth(), 1, 12));
  }, [value]);

  const year = visibleMonth.getFullYear();
  const month = visibleMonth.getMonth();
  const visibleMonthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
  useEffect(() => { onVisibleMonthChange?.(visibleMonthKey); }, [visibleMonthKey, onVisibleMonthChange]);
  const leadingDays = (new Date(year, month, 1, 12).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0, 12).getDate();
  const cells = Array.from({ length: 42 }, (_, index) => {
    const day = index - leadingDays + 1;
    return day > 0 && day <= daysInMonth ? day : null;
  });
  const today = dateKey(new Date());
  const monthLabel = visibleMonth.toLocaleDateString('en-AU', { month: 'long', year: 'numeric' });
  const selectedLabel = selected.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' });
  const moveMonth = (offset: number) => setVisibleMonth(current => new Date(current.getFullYear(), current.getMonth() + offset, 1, 12));

  return <View style={tw`mb-5`}>
    <Text style={tw`text-sm font-medium text-care-ink mb-2`}>Visit date</Text>
    <View testID="visit-date-calendar" style={tw`border border-care-line rounded-control bg-white p-3`}>
      <View style={tw`flex-row items-center gap-3 px-1 pb-3 mb-2 border-b border-care-line`}>
        <CalendarDays size={19} color="#176B58" />
        <Text style={tw`flex-1 text-sm font-semibold text-care-ink`}>{selectedLabel}</Text>
      </View>
      <View style={tw`flex-row items-center justify-between mb-2`}>
        <IconButton icon={ChevronLeft} label="Previous month" onPress={() => moveMonth(-1)} />
        <View style={tw`flex-row items-center gap-2`}><Text accessibilityRole="header" style={tw`text-base font-semibold text-care-ink`}>{monthLabel}</Text>{markersLoading && <ActivityIndicator size="small" color="#176B58" />}</View>
        <IconButton icon={ChevronRight} label="Next month" onPress={() => moveMonth(1)} />
      </View>
      <View style={tw`flex-row`}>
        {weekdays.map(day => <View key={day} style={{ width: `${100 / 7}%`, alignItems: 'center' }}><Text style={tw`text-[11px] font-medium text-care-muted py-2`}>{day}</Text></View>)}
      </View>
      <View style={tw`flex-row flex-wrap`}>
        {cells.map((day, index) => {
          if (!day) return <View key={`empty-${index}`} style={{ width: `${100 / 7}%`, height: 44 }} />;
          const date = new Date(year, month, day, 12);
          const key = dateKey(date);
          const isSelected = key === value;
          const isToday = key === today;
          const hasVisits = marked.has(key);
          return <View key={key} style={{ width: `${100 / 7}%`, height: 44, alignItems: 'center', justifyContent: 'center' }}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${date.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}${hasVisits ? ', visits scheduled' : ''}`}
              accessibilityState={{ selected: isSelected }}
              onPress={() => onChange(key)}
              style={({ pressed }) => tw.style('w-10 h-10 rounded-full items-center justify-center', isSelected && 'bg-care-primary', !isSelected && isToday && 'border border-care-primary', pressed && 'opacity-70')}
            >
              <Text style={tw.style('text-sm font-medium', isSelected ? 'text-white' : 'text-care-ink')}>{day}</Text>
              {hasVisits && <View testID={`visit-date-marker-${key}`} style={tw.style('absolute bottom-1 w-1 h-1 rounded-full', isSelected ? 'bg-white' : 'bg-care-primary')} />}
            </Pressable>
          </View>;
        })}
      </View>
    </View>
  </View>;
}
