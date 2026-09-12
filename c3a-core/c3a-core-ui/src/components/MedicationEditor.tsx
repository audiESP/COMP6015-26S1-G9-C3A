import React, { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Check, ChevronDown, ChevronUp, Pill } from 'lucide-react-native';
import type { MedicationSupportItem, MedicationSupportRecord, MedicationSupportStatus, ScenarioContext } from '../types';
import { Badge, Button, Copy, Field, Heading, Notice, Options, Sheet } from '../ui/primitives';
import tw from '../ui/tw';

const takenOptions = ['Taken', 'Not Taken', 'Unable to Confirm'] as const;
const supportOptions: MedicationSupportStatus[] = ['Completed', 'Delayed', 'Declined', 'Unavailable', 'Unable to Confirm'];
export function MedicationEditor({ scenario, disabled, onSave, onSaved }: { scenario: ScenarioContext; disabled: boolean; onSave: (record: Omit<MedicationSupportRecord, 'id' | 'visitId'>) => Promise<unknown>; onSaved: () => void }) {
  const existing = scenario.medicationSupport;
  const [items, setItems] = useState<MedicationSupportItem[]>(() => (scenario.patient.medications ?? []).map(name => existing?.medicationItems?.find(i => i.name === name) ?? { name }));
  const [status, setStatus] = useState<MedicationSupportStatus | ''>(existing?.status ?? '');
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [open, setOpen] = useState(0);
  const [review, setReview] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setItems(old => (scenario.patient.medications ?? []).map(name => old.find(i => i.name === name) ?? { name })); }, [scenario.patient.medications]);
  const valid = items.length > 0 && items.every(i => i.takenStatus) && !!status && (status === 'Completed' || !!notes.trim());
  const save = async () => {
    if (!valid || !confirmed || !status || disabled) return;
    setError(null);
    try { await onSave({ taskId: scenario.tasks.find(t => t.type === 'medication')?.id, status, notes: notes.trim(), timestamp: new Date().toISOString(), hcwId: scenario.worker.id, medicationNames: items.map(i => i.name), medicationItems: items }); setReview(false); onSaved(); }
    catch (err) { setError(err instanceof Error ? err.message : 'The medication record was not saved.'); }
  };
  return <>
    <View style={tw`flex-row justify-between mb-3`}><Heading>Current medicines</Heading><Copy muted small>{items.filter(i => i.takenStatus).length} / {items.length}</Copy></View>
    {items.length === 0 && <Notice text="No medication list is available. Check the patient record before recording support." error />}
    {items.map((item, index) => <View key={item.name} style={tw.style('bg-white rounded-card mb-3 border overflow-hidden', open === index ? 'border-care-primary' : 'border-care-line')}>
      <Pressable disabled={disabled} accessibilityRole="button" accessibilityState={{ expanded: open === index }} onPress={() => setOpen(open === index ? -1 : index)} style={tw`flex-row items-center gap-3 p-4 min-h-[76px]`}>
        {item.takenStatus ? <Check size={20} color="#176B58" /> : <Pill size={20} color="#697C75" />}
        <View style={tw`flex-1`}><Text style={tw`text-sm font-semibold text-care-ink`}>{item.name}</Text><Copy muted small>{item.takenStatus ?? 'Choose the observed status'}</Copy></View>{open === index ? <ChevronUp size={18} color="#697C75" /> : <ChevronDown size={18} color="#697C75" />}
      </Pressable>
      {open === index && <View style={tw`px-4 pb-1`}><Options label="Was this medicine taken?" values={takenOptions} selected={item.takenStatus ?? ''} disabled={disabled} onChange={takenStatus => { setItems(old => old.map((i, n) => n === index ? { ...i, takenStatus, takenAt: takenStatus === 'Taken' ? i.takenAt ?? new Date().toISOString() : undefined } : i)); setConfirmed(false); }} />{item.takenAt && <Copy muted small>Taken at {new Date(item.takenAt).toLocaleTimeString('en-AU')}</Copy>}</View>}
    </View>)}
    <Options label="Support outcome *" values={supportOptions} selected={status} disabled={disabled} onChange={value => { setStatus(value); setConfirmed(false); }} />
    <Field label={status && status !== 'Completed' ? 'Reason / notes *' : 'Additional notes'} value={notes} onChangeText={value => { setNotes(value); setConfirmed(false); }} editable={!disabled} multiline placeholder="Record what happened during medication support." />
    <Notice text={error} error />
    <Button label={disabled && scenario.visit.status === 'completed' ? 'Visit closed' : 'Review and save'} disabled={!valid || disabled} onPress={() => { setConfirmed(false); setReview(true); }} />
    <View style={tw`mt-3`}><Copy small muted>Recorded by {scenario.worker.name}. Your draft stays available during this visit.</Copy></View>
    <Sheet visible={review} title="Check medication record" onClose={() => setReview(false)} busy={disabled} footer={<Button label="Confirm and save" busy={disabled} disabled={!confirmed} onPress={() => void save()} />}>
      <Copy muted>{scenario.patient.name}</Copy>
      {items.map(item => <View key={item.name} style={tw`py-3 border-b border-care-line gap-1`}><Text style={tw`text-sm text-care-ink`}>{item.name}</Text><Badge>{item.takenStatus}</Badge></View>)}
      <View style={tw`my-3`}><Copy>Support outcome: {status}</Copy>{!!notes && <Copy muted>{notes}</Copy>}</View>
      <Pressable disabled={disabled} accessibilityRole="checkbox" accessibilityState={{ checked: confirmed }} onPress={() => setConfirmed(!confirmed)} style={tw`flex-row items-center gap-3 py-3 min-h-[48px]`}><View style={tw.style('w-6 h-6 rounded-md border items-center justify-center', confirmed ? 'bg-care-primary border-care-primary' : 'border-care-line')}>{confirmed && <Check size={17} color="white" />}</View><View style={tw`flex-1`}><Copy>I have checked each medicine and the support outcome.</Copy></View></Pressable>
      <Notice text={error} error />
    </Sheet>
  </>;
}
