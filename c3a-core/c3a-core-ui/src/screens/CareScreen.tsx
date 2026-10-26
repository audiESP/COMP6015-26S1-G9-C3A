import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ArrowLeftRight, ArrowRight, BookOpen, CalendarDays, Camera, Check, ChevronDown, ChevronLeft, ChevronRight, FileText, History, Image, Languages, MapPin, Paperclip, ShieldAlert, Sparkles, UserRound } from 'lucide-react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { File } from 'expo-file-system';
import { useScenarioStore, localDate, type TaskIssueType } from '../store/scenarioStore';
import { useChatStore } from '../store/chatStore';
import { useChat } from '../hooks/useChat';
import { analyseRiskNote, fetchPatientSummary, generateVisitReport, type PatientSummaryRecord } from '../services/api';
import type { Attachment, CareOutcomeFormAnswers, CareTask, CareTaskStatus, RiskAlert, RiskSuggestion } from '../types';
import { ChatBubble } from '../components/ChatBubble';
import { ChatInput } from '../components/ChatInput';
import { MedicationEditor } from '../components/MedicationEditor';
import { PatientModal } from '../components/PatientModal';
import { FinishVisitFormModal, TranslationTab, PatientDetailsPanel, VisitSummaryPanel, createEmptyCareOutcomeForm, isCareOutcomeFormComplete } from './CarePanels';
import { TrainingScreen } from './TrainingScreen';
import { Badge, Button, Copy, Field, Header, Heading, IconButton, Notice, Options, Section, Sheet, Surface, useReducedMotion } from '../ui/primitives';
import { SwipeTask } from '../ui/SwipeTask';
import { TaskTrainingMaterials } from '../ui/TaskTrainingMaterials';
import { CalendarDatePicker } from '../ui/CalendarDatePicker';
import tw from '../ui/tw';
import '../i18n';

type Page = 'today' | 'visit' | 'patient' | 'medication' | 'translate' | 'assistant' | 'summary' | 'training' | 'risks';
type Panel = 'patient' | 'task' | 'issue' | 'arrival' | 'finish' | 'history' | 'attachments' | 'analysis' | 'risk' | 'shift' | 'date' | null;
const navItems = [{ id: 'today', label: 'Visits', icon: CalendarDays }, { id: 'translate', label: 'Translate', icon: Languages }, { id: 'assistant', label: 'Assistant', icon: Sparkles }, { id: 'training', label: 'Learn', icon: BookOpen }] as const;
const time = (s: string) => new Date(s).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false });
const outcomeOptions: CareTaskStatus[] = ['completed', 'delayed', 'skipped', 'issue'];
const issueOptions: TaskIssueType[] = ['cannot_complete', 'patient_declined', 'safety_concern', 'medication_delayed', 'medication_unavailable', 'medication_unable_to_confirm'];

export function CareScreen() {
  const workflow = useScenarioStore();
  const { scenario: s, visitQueue, activeAlerts, isLoading, isSaving } = workflow;
  const [page, setPage] = useState<Page>('today');
  const [panel, setPanel] = useState<Panel>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const actionLock = useRef(false);
  const [expandedDone, setExpandedDone] = useState(false);
  const [task, setTask] = useState<CareTask | null>(null);
  const [taskDrafts, setTaskDrafts] = useState<Record<string, { status: CareTaskStatus | ''; note: string; issue: TaskIssueType | '' }>>({});
  const [locationNote, setLocationNote] = useState('');
  const [identityChecked, setIdentityChecked] = useState(false);
  const [dateInput, setDateInput] = useState(workflow.date);
  const [patientEditing, setPatientEditing] = useState(false);
  const [summary, setSummary] = useState('');
  const [summaryRecords, setSummaryRecords] = useState<PatientSummaryRecord[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [finishOpen, setFinishOpen] = useState(false);
  const [form, setForm] = useState<CareOutcomeFormAnswers>(createEmptyCareOutcomeForm);
  const [report, setReport] = useState('');
  const [generating, setGenerating] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [risk, setRisk] = useState<RiskAlert | null>(null);
  const [riskAction, setRiskAction] = useState<'acknowledge' | 'resolve' | 'dismiss'>('acknowledge');
  const [riskNote, setRiskNote] = useState('');
  const [analysisNote, setAnalysisNote] = useState('');
  const [suggestions, setSuggestions] = useState<RiskSuggestion[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const scroll = useRef<ScrollView>(null);
  const reducedMotion = useReducedMotion();
  const fade = useRef(new Animated.Value(1)).current;
  const chat = useChatStore();
  const { sendMessage, isLoading: chatLoading, error: chatError } = useChat({ ...chat, scenarioContext: s ?? undefined });
  const visitId = s?.visit.id;
  const patientId = s?.patient.id;
  const sessionVisit = useRef<string | null>(null);
  const navigate = (next: Page) => { setPage(next); setPanel(null); setOperationError(null); scroll.current?.scrollTo({ y: 0, animated: false }); };
  const open = (next: Panel) => { setOperationError(null); setPanel(next); };
  const openDatePicker = () => { setDateInput(workflow.date); open('date'); };
  const run = async (operation: () => Promise<unknown>, success?: () => void) => {
    if (actionLock.current) return;
    actionLock.current = true; setBusy(true); setOperationError(null); setNotice(null);
    try { await operation(); success?.(); }
    catch (err) { setOperationError(err instanceof Error ? err.message : 'The operation did not complete. Please retry.'); }
    finally { actionLock.current = false; setBusy(false); }
  };
  useEffect(() => {
    if (!s || sessionVisit.current === s.visit.id) return;
    sessionVisit.current = s.visit.id;
    const session = chat.createSession(); chat.linkPatient(session.id, s.patient);
    setAttachments([]); setForm(createEmptyCareOutcomeForm()); setReport(''); setReportError(null); setFinishOpen(false); setPanel(null); setTask(null); setLocationNote(''); setIdentityChecked(false); setSuggestions([]); setAnalysisNote('');
  }, [visitId, s, chat.createSession, chat.linkPatient]);
  useEffect(() => {
    let cancelled = false;
    setSummary(''); setSummaryRecords([]); setSummaryError(null);
    if (!patientId) return;
    setSummaryLoading(true);
    fetchPatientSummary(patientId).then(result => { if (!cancelled) { setSummary(result.summary); setSummaryRecords(result.records); } }).catch(err => { if (!cancelled) setSummaryError(err instanceof Error ? err.message : 'Summary unavailable.'); }).finally(() => { if (!cancelled) setSummaryLoading(false); });
    return () => { cancelled = true; };
  }, [patientId]);
  useEffect(() => { fade.setValue(reducedMotion ? 1 : 0); Animated.timing(fade, { toValue: 1, duration: reducedMotion ? 0 : 200, useNativeDriver: true }).start(); }, [page, fade, reducedMotion]);
  const send = (text: string, files: Attachment[]) => { if (!s || chatLoading) return; void sendMessage(text, files); setAttachments([]); };
  const revealChatInput = () => {
    // Wait until the keyboard has resized the viewport before revealing the
    // newest message and composer at the bottom of the conversation.
    setTimeout(() => scroll.current?.scrollToEnd({ animated: true }), 250);
  };
  const locked = busy || isSaving || isLoading || chatLoading || generating;
  const closed = s?.visit.status === 'completed';
  const started = !!s && s.visit.status !== 'scheduled';
  const completed = s?.tasks.filter(t => t.status === 'completed') ?? [];
  const outstanding = s?.tasks.filter(t => t.status !== 'completed') ?? [];
  const currentTask = outstanding[0];
  const taskKey = `${visitId}:${task?.id}`;
  const taskDraft = taskDrafts[taskKey] ?? { status: task?.status ?? '', note: task?.note ?? '', issue: '' };
  const changeTaskDraft = (patch: Partial<typeof taskDraft>) => setTaskDrafts(old => ({ ...old, [taskKey]: { ...taskDraft, ...patch } }));
  const selectTask = (t: CareTask, issue = false) => {
    if (!started) { open('arrival'); return; }
    if (closed) return;
    if (!issue && t.type === 'medication') { navigate('medication'); return; }
    setTask(t); open(issue ? 'issue' : 'task');
  };
  const selectVisit = async (id: string) => { if (locked) return; if (await workflow.selectVisit(id)) navigate('visit'); };
  const generate = async () => {
    if (!s || generating || !isCareOutcomeFormComplete(form)) return;
    setGenerating(true); setReportError(null);
    try { const response = await generateVisitReport(s.visit.id, { patientContext: s.patient, workerContext: s.worker, visitContext: s.visit, taskContext: s.tasks, eventContext: s.events, riskContext: activeAlerts, medicationSupportContext: s.medicationSupport, careOutcomeForm: form }); setReport(response.report); }
    catch (err) { setReportError(err instanceof Error ? err.message : 'Could not generate the report.'); }
    finally { setGenerating(false); }
  };
  const pickAttachment = (kind: 'camera' | 'image' | 'file') => void run(async () => {
    let attachment: Attachment | null = null;
    if (kind === 'file') {
      const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true });
      if (result.canceled) return;
      const item = result.assets[0]; if (item.size && item.size > 10 * 1024 * 1024) throw new Error('Choose a file smaller than 10 MB.');
      attachment = { id: `${Date.now()}`, type: 'file', name: item.name, uri: item.uri, mimeType: item.mimeType ?? 'application/octet-stream', base64: await new File(item.uri).base64() };
    } else {
      if (kind === 'camera' && !(await ImagePicker.requestCameraPermissionsAsync()).granted) throw new Error('Camera permission is required.');
      const result = await (kind === 'camera' ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync)({ base64: true, quality: 0.7, mediaTypes: ['images'] });
      if (result.canceled) return;
      const item = result.assets[0]; if (item.fileSize && item.fileSize > 10 * 1024 * 1024) throw new Error('Choose an image smaller than 10 MB.');
      attachment = { id: `${Date.now()}`, type: 'image', name: item.fileName ?? 'Care image', uri: item.uri, mimeType: item.mimeType ?? 'image/jpeg', base64: item.base64 ?? undefined };
    }
    if (attachment) setAttachments(old => [...old, attachment!]); setPanel(null);
  });
  const context = s ? <Pressable accessibilityRole="button" accessibilityLabel="Patient quick view" onPress={() => open('patient')} style={tw`bg-white rounded-[18px] p-3 flex-row items-center gap-3 mb-3`}><View style={tw`w-10 h-10 bg-care-soft rounded-full items-center justify-center`}><Text style={tw`text-care-primary font-semibold`}>{s.patient.name.split(' ').map(n => n[0]).slice(0, 2).join('')}</Text></View><View style={tw`flex-1`}><Text style={tw`text-sm font-semibold text-care-ink`}>{s.patient.name}</Text><Copy muted small>{s.patient.age ?? '--'} years · {s.patient.preferredLanguage ?? 'Language not recorded'}</Copy></View><ChevronDown size={18} color="#697C75" /></Pressable> : null;
  const routeTitles: Record<Page, string> = { today: 'Care, at your pace.', visit: 'Focus on this visit', patient: 'Patient details', medication: 'Medication support', translate: 'Make yourself understood', assistant: 'Care assistant', summary: 'Visit record', training: 'Learn as you care', risks: 'Care alerts' };
  const visitPages = !['today', 'training'].includes(page);
  const pageHasBack = !['today', 'training', 'translate', 'assistant'].includes(page);
  return <SafeAreaView style={tw`flex-1 bg-care-canvas`} edges={['top', 'left', 'right', 'bottom']}>
    <KeyboardAvoidingView
      style={tw`flex-1`}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={0}
    >
      <View style={tw`flex-1 w-full max-w-[600px] self-center`}>
        {page !== 'training' && <Header title={routeTitles[page]} eyebrow={page === 'today' ? 'C3A / CARE COMPANION' : s ? `${time(s.visit.scheduledAt)} · ${s.visit.status.replace(/_/g, ' ')}` : 'C3A'} onBack={pageHasBack ? () => navigate(page === 'visit' ? 'today' : 'visit') : undefined} right={page === 'today' ? <IconButton icon={CalendarDays} label="Choose visit date" onPress={openDatePicker} disabled={locked} /> : page === 'assistant' ? <IconButton icon={History} label="Conversation history" onPress={() => open('history')} /> : <IconButton icon={FileText} label="Visit record" onPress={() => navigate('summary')} />} />}
        <View style={tw`flex-1`}>
          <View style={tw.style('flex-1', page !== 'training' && 'hidden')}><TrainingScreen embedded onClose={() => navigate('today')} /></View>
          <ScrollView ref={scroll} style={tw.style('flex-1', page === 'training' && 'hidden')} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag" contentContainerStyle={tw`px-5 pb-6`} refreshControl={page === 'today' ? <RefreshControl refreshing={isLoading} onRefresh={() => void workflow.reload()} tintColor="#176B58" /> : undefined}>
            <Notice text={workflow.error} error /><Notice text={!panel ? operationError : null} error /><Notice text={notice} />
            {isLoading && <View style={tw`py-8 items-center`}><ActivityIndicator color="#176B58" /><Copy muted>Loading visits...</Copy></View>}
            {!s && !isLoading && <Surface><Heading>{workflow.error ? 'Unable to load visits' : 'No visits on this date'}</Heading><Copy muted>{workflow.date} · Choose another day or refresh your schedule.</Copy><View style={tw`mt-4 gap-3`}><Button label="Choose a date" secondary onPress={openDatePicker} /><Button label="Retry connection" onPress={() => void workflow.reload()} /></View></Surface>}
            {s && <Animated.View style={{ opacity: fade }}>
              {page === 'today' && <>
                <View style={tw`flex-row items-center gap-3 mb-5`}><Text style={tw`text-[40px] text-care-ink tracking-[-2px] font-medium`}>{workflow.date.slice(-2)}</Text><View><Copy muted small>{new Date(`${workflow.date}T12:00:00`).toLocaleDateString('en-AU', { month: 'long', weekday: 'long' })}</Copy><Copy small muted>{s.worker.name} · {s.worker.shift}</Copy></View></View>
                <View style={tw`bg-care-deep rounded-hero p-6`}>
                  <View style={tw`flex-row justify-between items-center`}><Text style={tw`text-xs text-care-onhero bg-white/10 px-3 py-1.5 rounded-lg`}>{closed ? 'Visit completed' : started ? 'In your care' : 'Up next'}</Text><Text style={tw`text-xs text-care-subtle`}>{time(s.visit.scheduledAt)}</Text></View>
                  <Text style={tw`text-[29px] tracking-[-0.6px] font-semibold text-care-onhero mt-4 mb-1`}>{s.patient.name}</Text><Text style={tw`text-sm text-care-subtle leading-5`}>{visitQueue.find(v => v.id === visitId)?.purpose ?? s.visit.location}</Text>
                  <View style={tw`flex-row gap-2 items-center mt-5`}><MapPin size={16} color="#C3D8CA" /><Text style={tw`text-xs text-care-subtle flex-1`}>{s.visit.plannedAddress ?? s.visit.location}</Text></View>
                  <View style={tw`h-1 bg-white/20 rounded-full mt-5 mb-2`}><View style={[tw`h-1 bg-care-lime rounded-full`, { width: `${s.tasks.length ? completed.length / s.tasks.length * 100 : 0}%` }]} /></View><Text style={tw`text-xs text-care-subtle`}>{completed.length} / {s.tasks.length} care tasks completed</Text>
                  <Pressable accessibilityRole="button" onPress={() => navigate(closed ? 'summary' : 'visit')} disabled={locked} style={tw`bg-care-lime rounded-control py-4 px-5 mt-5 flex-row items-center justify-center gap-3`}><Text style={tw`text-care-deep font-semibold`}>{closed ? 'View visit record' : started ? 'Continue care' : 'Prepare for visit'}</Text><ArrowRight size={18} color="#183F34" /></Pressable>
                </View>
                <Section title="Your schedule" detail={`${visitQueue.length} visits`} />
                {visitQueue.filter(v => v.id !== visitId).map(v => <Pressable key={v.id} disabled={locked} onPress={() => void selectVisit(v.id)} accessibilityRole="button" style={tw`bg-white rounded-card p-4 mb-2 flex-row items-center gap-3`}><Text style={tw`text-lg font-medium text-care-ink`}>{time(v.scheduledAt)}</Text><View style={tw`flex-1`}><Text style={tw`font-semibold text-sm text-care-ink`}>{v.patientName}</Text><Copy small muted>{v.purpose}</Copy><Copy small muted>{v.status.replace(/_/g, ' ')}</Copy></View><ChevronRight size={17} color="#697C75" /></Pressable>)}
                <View style={tw`mt-3`}><Button label="Shift overview" secondary onPress={() => open('shift')} /></View>
              </>}
              {visitPages && context}
              {page === 'visit' && <>
                {activeAlerts.length > 0 && <Pressable accessibilityRole="button" onPress={() => navigate('risks')} style={tw`bg-care-warning rounded-control p-3 flex-row gap-2 items-center`}><ShieldAlert size={20} color="#80551C" /><Text style={tw`text-xs text-care-amber flex-1`}>{activeAlerts[0].title}{activeAlerts.length > 1 ? ` · ${activeAlerts.length} open alerts` : ''}</Text><ChevronRight size={16} color="#80551C" /></Pressable>}
                <Section title={closed ? 'Visit complete' : !started ? 'Before you begin' : 'Your next step'} detail={`${completed.length} / ${s.tasks.length}`} />
                <Surface><Badge>{closed ? 'Closed' : started ? 'Current task' : 'Arrival'}</Badge><View style={tw`mt-3 mb-2`}><Heading>{closed ? 'Care recorded for this visit' : !started ? 'Start when you arrive' : currentTask?.label ?? 'Review and finish'}</Heading></View><Copy muted>{closed ? 'Your visit and location records are available below.' : !started ? 'Confirm identity and record your arrival location.' : currentTask?.detail ?? 'Check the care outcomes and follow-up arrangements.'}</Copy><View style={tw`mt-4`}><Button label={closed ? 'View record' : !started ? 'Start visit' : currentTask ? currentTask.type === 'medication' ? 'Record medication support' : 'Record this task' : 'Review and finish'} disabled={locked} onPress={() => closed ? navigate('summary') : !started ? open('arrival') : currentTask ? selectTask(currentTask) : setFinishOpen(true)} /></View></Surface>
                <Section title="Care checklist" detail="Swipe left for actions" />
                {outstanding.map(t => <View key={t.id}><SwipeTask task={t} index={s.tasks.indexOf(t)} disabled={locked || !!closed} onRecord={() => selectTask(t)} onIssue={() => selectTask(t, true)} /><TaskTrainingMaterials task={t} disabled={locked || !!closed} /></View>)}
                <Pressable accessibilityRole="button" accessibilityState={{ expanded: expandedDone }} onPress={() => setExpandedDone(!expandedDone)} style={tw`py-4 flex-row items-center gap-2`}><ChevronDown size={16} color="#697C75" /><Copy muted small>{completed.length} completed tasks</Copy></Pressable>
                {expandedDone && completed.map(t => <View key={t.id} style={tw`mb-2 p-4 bg-care-soft rounded-control`}><Copy>{t.label}</Copy>{!!t.note && <Copy small muted>{t.note}</Copy>}</View>)}
                {started && !closed && <Button label="Care outcomes and report" secondary disabled={locked || outstanding.some(t => t.status === 'pending' && t.type !== 'documentation')} onPress={() => setFinishOpen(true)} />}
              </>}
              <View style={tw.style(page !== 'medication' && 'hidden')}><MedicationEditor key={visitId} scenario={s} disabled={locked || !!closed || !started} onSave={workflow.updateMedicationSupport} onSaved={() => { navigate('visit'); setNotice('Medication record saved to the server.'); }} /></View>
              <View style={tw.style(page !== 'translate' && 'hidden')}><TranslationTab key={`${visitId}-translation`} active={page === 'translate'} patientLanguage={s.patient.preferredLanguage ?? 'English'} workerLanguage="English" visitId={visitId} /></View>
              {page === 'patient' && <><Button label="Edit care preferences" secondary disabled={locked || !!closed} onPress={() => setPatientEditing(true)} /><PatientDetailsPanel patient={s.patient} worker={s.worker.name} location={s.visit.location} alerts={s.alerts} summary={summary} summaryRecords={summaryRecords} summaryLoading={summaryLoading} summaryError={summaryError} disabled={locked || !!closed} onAlertAction={async (id, action, note) => { try { return await workflow.updateAlert(id, action, note); } catch (err) { setOperationError(err instanceof Error ? err.message : 'Alert update failed.'); return s; } }} /></>}
              {page === 'assistant' && <>
                <Badge>Linked to this visit and its care tasks</Badge>
                {chat.activeSession?.messages.length ? chat.activeSession.messages.map(m => <ChatBubble key={m.id} message={m} />) : <View style={tw`py-10`}><Sparkles size={30} color="#176B58" /><View style={tw`my-4`}><Heading>How can I help with this visit?</Heading></View><Copy muted>Ask about the patient record, the current task or care guidance.</Copy><View style={tw`gap-3 mt-5`}><Button secondary label="What are this patient's care preferences?" onPress={() => send('What are this patient\'s care and communication preferences?', [])} disabled={chatLoading} /><Button secondary label="Explain the current care task" onPress={() => send('Explain the current care task using the available context.', [])} disabled={chatLoading} /></View></View>}
                {chatLoading && <ChatBubble isTyping message={{ id: 'pending', role: 'assistant', content: '', timestamp: new Date() }} />}<Notice text={chatError} error />
                <View style={tw`my-4`}><Button label="Review an observation with AI" secondary onPress={() => open('analysis')} /></View>
              </>}
              {page === 'risks' && <>{[false, true].map(history => <View key={String(history)}><Section title={history ? 'Resolved and dismissed' : 'Needs attention'} />{s.alerts.filter(a => history === ['resolved', 'dismissed'].includes(a.status ?? '')).map(a => <Surface key={a.id}><Badge warning={a.level !== 'low' && !history}>{a.level.toUpperCase()} · {(a.status ?? 'active').replace('_', ' ')}</Badge><View style={tw`my-3`}><Heading>{a.title}</Heading></View><Copy muted>{a.message}</Copy>{a.reviewNote && <Copy>Review: {a.reviewNote}</Copy>}{!history && <View style={tw`mt-4`}><Button label="Review and record action" secondary disabled={locked || !!closed} onPress={() => { setRisk(a); setRiskNote(a.reviewNote ?? ''); setRiskAction(a.status === 'acknowledged' ? 'resolve' : 'acknowledge'); open('risk'); }} /></View>}</Surface>)}</View>)}</>}
              {page === 'summary' && <><VisitSummaryPanel status={s.visit.status.replace(/_/g, ' ')} lifecycle={s.lifecycleStep.replace(/_/g, ' ')} completed={`${completed.length}/${s.tasks.length}`} followUp={activeAlerts.length ? `${activeAlerts.length} open alerts` : 'No open alerts'} visit={s.visit} shiftSummaryOpen={false} totalVisits={visitQueue.length} completedVisits={visitQueue.filter(v => v.status === 'completed').length} followUpCount={visitQueue.filter(v => ['incident', 'follow_up_required'].includes(v.status)).length} /><Section title="Visit timeline" />{s.events.map(event => <View key={event.id} style={tw`border-l border-care-line ml-2 pl-5 py-3`}><Copy muted small>{time(event.timestamp)}</Copy><Copy>{event.type.replace(/_/g, ' ')}</Copy>{event.note && <Text selectable style={tw`text-sm leading-6 text-care-muted mt-2`}>{event.note}</Text>}</View>)}</>}
            </Animated.View>}
          </ScrollView>
        </View>
        {page === 'assistant' && s && <ChatInput key={visitId} onSend={send} onPressPlus={() => open('attachments')} onFocus={revealChatInput} isLoading={chatLoading || locked} pendingAttachments={attachments} onRemoveAttachment={id => setAttachments(old => old.filter(a => a.id !== id))} />}
        <View style={tw`bg-white border border-care-line rounded-[23px] mx-4 mt-2 mb-2 p-1.5 flex-row`}>
          {navItems.map(({ id, label, icon: Icon }) => { const active = page === id || (id === 'today' && !['training', 'translate', 'assistant'].includes(page)); return <Pressable key={id} accessibilityRole="tab" accessibilityState={{ selected: active, disabled: locked }} disabled={locked} onPress={() => navigate(id)} style={tw.style('flex-1 py-2.5 min-h-[56px] items-center justify-center gap-1 rounded-control', active && 'bg-care-soft')}><Icon size={20} strokeWidth={1.7} color={active ? '#176B58' : '#697C75'} /><Text style={tw.style('text-[11px] font-medium', active ? 'text-care-primary' : 'text-care-muted')}>{label}</Text></Pressable>; })}
        </View>
      </View>
    </KeyboardAvoidingView>
    <Sheet visible={panel !== null} busy={busy || isSaving} title={panel ? ({ patient: 'Patient quick view', task: 'Record care task', issue: 'Report a task issue', arrival: 'Start this visit', finish: 'Finish this visit', history: 'Conversation history', attachments: 'Add an attachment', analysis: 'Review a care observation', risk: 'Record alert action', shift: 'Shift overview', date: 'Choose visit date' }[panel]) : ''} onClose={() => setPanel(null)}>
      <Notice text={operationError} error />
      {panel === 'date' && <><CalendarDatePicker value={dateInput} onChange={setDateInput} markedDates={workflow.visitDates} onVisibleMonthChange={workflow.loadVisitDates} markersLoading={workflow.isCalendarLoading} /><Button label="Load schedule" onPress={() => { workflow.setDate(dateInput); navigate('today'); }} /><View style={tw`mt-3`}><Button secondary label="Today" onPress={() => { workflow.setDate(localDate()); navigate('today'); }} /></View></>}
      {s && <>
        {panel === 'patient' && <><Heading>{s.patient.name}</Heading>{[['Language', s.patient.preferredLanguage], ['Mobility', s.patient.mobilitySupport], ['Diet', s.patient.dietaryNotes], ['Allergies', s.patient.allergies?.join(', ')], ['Communication', s.patient.communicationNotes]].map(([label, value]) => <View key={label} style={tw`border-b border-care-line py-3`}><Copy muted small>{label}</Copy><Copy>{value || 'Not recorded'}</Copy></View>)}<View style={tw`mt-4`}><Button label="Full patient details" onPress={() => navigate('patient')} /></View></>}
        {(panel === 'task' || panel === 'issue') && task && <><Copy muted>{task.label}</Copy><View style={tw`mt-4`}>{panel === 'task' ? <Options label="Task outcome *" values={outcomeOptions} selected={taskDraft.status} onChange={status => changeTaskDraft({ status })} /> : <Options label="Issue type *" values={issueOptions.filter(i => task.type === 'medication' || !i.startsWith('medication_'))} selected={taskDraft.issue} onChange={issue => changeTaskDraft({ issue })} />}<Field multiline label="Observation / reason" value={taskDraft.note} onChangeText={note => changeTaskDraft({ note })} placeholder="Record what happened and any follow-up needed." /><Button label="Save task record" busy={busy || isSaving} onPress={() => { if (panel === 'issue' ? !taskDraft.issue : !taskDraft.status) { setOperationError('Choose an outcome.'); return; } if ((panel === 'issue' || taskDraft.status !== 'completed') && !taskDraft.note.trim()) { setOperationError('Record a reason for an incomplete task or issue.'); return; } void run(() => panel === 'issue' ? workflow.reportTaskIssue(task.id, taskDraft.issue as TaskIssueType, taskDraft.note) : workflow.updateTask(task.id, taskDraft.status as CareTaskStatus, taskDraft.note), () => { setPanel(null); setNotice('Task record saved to the server.'); setReport(''); }); }} /></View></>}
        {(panel === 'arrival' || panel === 'finish') && <><Heading>{s.patient.name}</Heading><Copy muted>{s.visit.plannedAddress ?? s.visit.location}</Copy><View style={tw`my-4`}><Copy>{panel === 'arrival' ? 'Confirm identity before starting. GPS records your arrival.' : 'Check the report before finishing. GPS records your departure.'}</Copy></View>{panel === 'arrival' && <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: identityChecked }} onPress={() => setIdentityChecked(!identityChecked)} style={tw`flex-row items-center gap-3 py-4`}><View style={tw.style('w-6 h-6 border rounded-md items-center justify-center', identityChecked ? 'bg-care-primary border-care-primary' : 'border-care-line')}>{identityChecked && <Check size={16} color="white" />}</View><View style={tw`flex-1`}><Copy>I have confirmed the patient's identity.</Copy></View></Pressable>}<Field multiline label="Manual location reason (only if GPS is unavailable)" value={locationNote} onChangeText={setLocationNote} placeholder="Leave blank to use GPS." /><Button label={panel === 'arrival' ? 'Start visit and check in' : 'Confirm report and finish'} busy={busy || isSaving} disabled={panel === 'arrival' && !identityChecked} onPress={() => void run(async () => { const snapshot = await workflow.locationSnapshot(panel === 'arrival' ? 'check_in' : 'check_out', locationNote); if (panel === 'arrival') await workflow.startVisit(snapshot); else { if (!report || !isCareOutcomeFormComplete(form)) throw new Error('Complete the care outcome form and generate a report first.'); await workflow.completeVisit(snapshot, report); } }, () => { const next = panel === 'arrival' ? 'visit' : 'summary'; setLocationNote(''); navigate(next); setNotice('Visit record saved to the server.'); })} /></>}
        {panel === 'history' && <>{chat.sessions.filter(c => c.patientInfo?.id === patientId).map(c => <Pressable key={c.id} accessibilityRole="button" onPress={() => { chat.selectSession(c.id); setPanel(null); }} style={tw`py-4 border-b border-care-line`}><Copy>{c.title}</Copy><Copy small muted>{c.messages.length} messages</Copy></Pressable>)}<View style={tw`mt-4`}><Button label="New conversation" onPress={() => { const c = chat.createSession(); chat.linkPatient(c.id, s.patient); setPanel(null); }} /></View></>}
        {panel === 'attachments' && <View style={tw`gap-3`}><Button secondary label="Take a photo" icon={Camera} onPress={() => pickAttachment('camera')} /><Button secondary label="Choose an image" icon={Image} onPress={() => pickAttachment('image')} /><Button secondary label="Choose a document" icon={Paperclip} onPress={() => pickAttachment('file')} /><Copy small muted>Attachments are sent with your next question. Model support varies.</Copy></View>}
        {panel === 'analysis' && <><Notice text="AI suggestions require review. They do not automatically create official alerts." /><Field label="Care observation" value={analysisNote} onChangeText={setAnalysisNote} multiline placeholder="Describe what you observed." /><Button label="Analyse observation" busy={busy} disabled={!analysisNote.trim()} onPress={() => void run(async () => { const response = await analyseRiskNote({ note: analysisNote, patientContext: s.patient, workerContext: s.worker, visitContext: s.visit, currentTaskContext: currentTask, taskContext: s.tasks, eventContext: s.events, riskContext: activeAlerts }); setSuggestions(response.suggestions); })} />{suggestions.map((suggestion, i) => <View key={i} style={tw`bg-care-soft rounded-control p-4 mt-3`}><Badge warning>{suggestion.level}</Badge><Heading>{suggestion.riskType}</Heading><Copy>{suggestion.reason}</Copy>{suggestion.recommendedActions.map((action, n) => <Copy key={n}>• {action}</Copy>)}<Copy small muted>Worker confirmation required</Copy></View>)}</>}
        {panel === 'risk' && risk && <><Heading>{risk.title}</Heading><Copy muted>{risk.message}</Copy><View style={tw`mt-4`}><Options label="Action" values={['acknowledge', 'resolve', 'dismiss'] as const} selected={riskAction} onChange={setRiskAction} /><Field label="Review note" multiline value={riskNote} onChangeText={setRiskNote} /><Button label="Confirm alert action" busy={busy || isSaving} onPress={() => { if (riskAction !== 'acknowledge' && !riskNote.trim()) { setOperationError('Add the reason for resolving or dismissing this alert.'); return; } void run(() => workflow.updateAlert(risk.id, riskAction, riskNote), () => { setPanel(null); setNotice('Alert action saved.'); setReport(''); }); }} /></View></>}
        {panel === 'shift' && <><Copy muted>{workflow.date} · {s.worker.name}</Copy><Section title="Planned visits" detail={String(visitQueue.length)} /><Section title="Completed visits" detail={String(visitQueue.filter(v => v.status === 'completed').length)} /><Section title="Needs follow-up" detail={String(visitQueue.filter(v => ['incident', 'follow_up_required', 'delayed'].includes(v.status)).length)} /></>}
      </>}
    </Sheet>
    {s && <FinishVisitFormModal visible={finishOpen} form={form} report={report} reportError={reportError} isGenerating={generating} isSaving={busy || isSaving} canGenerate={isCareOutcomeFormComplete(form)} onChange={next => { setForm(next); setReport(''); setReportError(null); }} onGenerate={() => void generate()} onFinish={() => { setFinishOpen(false); open('finish'); }} onClose={() => !generating && setFinishOpen(false)} />}
    {s && <PatientModal visible={patientEditing} initial={s.patient} onClose={() => setPatientEditing(false)} onSave={patient => { void run(() => workflow.updatePatient(patient), () => { setPatientEditing(false); setNotice('Patient preferences saved.'); }); }} />}
  </SafeAreaView>;
}
