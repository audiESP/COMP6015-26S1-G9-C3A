import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, Text, View } from 'react-native';
import { BookOpen, ChevronRight, ExternalLink, FileText, Languages, Search } from 'lucide-react-native';
import { fetchTrainingMaterials, fetchTrainingTopics, searchTrainingMaterials } from '../services/api';
import type { TrainingMaterial, TrainingSearchResult, TrainingTopic } from '../types';
import { Badge, Button, Copy, Field, Header, Heading, Notice, Section, Surface } from '../ui/primitives';
import tw from '../ui/tw';

type TrainingView = { kind: 'topics' } | { kind: 'materials'; topic: TrainingTopic } | { kind: 'detail'; material: TrainingMaterial; topic: TrainingTopic };
export function TrainingScreen({ onClose, embedded = false }: { onClose: () => void; embedded?: boolean }) {
  const [view, setView] = useState<TrainingView>({ kind: 'topics' });
  const [topics, setTopics] = useState<TrainingTopic[]>([]);
  const [materials, setMaterials] = useState<TrainingMaterial[]>([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<TrainingSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const topicId = view.kind === 'materials' ? view.topic.id : undefined;
  const scroll = useRef<ScrollView>(null);
  useEffect(() => {
    let cancelled = false; setLoading(true); setError(null);
    const load = topicId ? fetchTrainingMaterials(topicId).then(r => { if (!cancelled) setMaterials(r.materials); }) : fetchTrainingTopics().then(r => { if (!cancelled) setTopics(r.topics); });
    load.catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load learning resources.'); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [topicId, retry]);
  useEffect(() => {
    let cancelled = false;
    if (!query.trim()) { setResults([]); setSearching(false); return; }
    setSearching(true); setError(null);
    const timer = setTimeout(() => searchTrainingMaterials(query.trim()).then(r => { if (!cancelled) setResults(r.results); }).catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Search failed.'); }).finally(() => { if (!cancelled) setSearching(false); }), 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, retry]);
  const move = (next: TrainingView) => { setView(next); setError(null); scroll.current?.scrollTo({ y: 0, animated: false }); };
  const openResource = async (url: string) => { try { if (!/^https?:\/\//i.test(url)) throw new Error('This resource does not have a valid web address.'); await Linking.openURL(url); } catch (err) { setError(err instanceof Error ? err.message : 'Could not open this resource.'); } };
  const back = () => view.kind === 'topics' ? onClose() : view.kind === 'materials' ? move({ kind: 'topics' }) : move({ kind: 'materials', topic: view.topic });
  const materialRow = (material: TrainingMaterial, topic: TrainingTopic) => <Pressable accessibilityRole="button" key={material.id} onPress={() => move({ kind: 'detail', material, topic })} style={tw`bg-white rounded-card p-4 mb-3 flex-row items-start gap-3`}><FileText size={21} color="#176B58" /><View style={tw`flex-1`}><Text style={tw`text-base font-semibold text-care-ink`}>{material.title}</Text><Copy small muted>{material.summary}</Copy><Text style={tw`text-xs text-care-muted mt-2`}>{material.type.toUpperCase()}{material.durationMinutes ? ` · ${material.durationMinutes} min` : ''}</Text></View><ChevronRight size={17} color="#697C75" /></Pressable>;
  return <View style={tw.style('flex-1 bg-care-canvas', !embedded && 'pt-5')}>
    <Header title={view.kind === 'topics' ? 'Learn as you care' : view.kind === 'materials' ? view.topic.title : 'Resource details'} eyebrow="CARE LIBRARY" onBack={back} />
    <ScrollView ref={scroll} keyboardShouldPersistTaps="handled" contentContainerStyle={tw`px-5 pb-6`}>
      <Notice error text={error} />{error && <Button label="Retry" onPress={() => setRetry(v => v + 1)} />}
      {view.kind === 'topics' && <><Copy muted>Trusted resources, ready when you need them.</Copy><View style={tw`mt-5`}><Field label="Search resources" value={query} onChangeText={setQuery} placeholder="Topic, title or language" /></View></>}
      {(loading || searching) && <ActivityIndicator style={tw`my-6`} color="#176B58" />}
      {view.kind === 'topics' && !query.trim() && <><Section title="Care topics" />{topics.map(topic => <Pressable key={topic.id} accessibilityRole="button" onPress={() => { setMaterials([]); move({ kind: 'materials', topic }); }} style={tw`flex-row gap-3 items-center py-4 border-b border-care-line`}><View style={tw`w-11 h-11 rounded-xl bg-care-soft items-center justify-center`}><BookOpen size={21} color="#176B58" /></View><View style={tw`flex-1`}><Text style={tw`text-base font-semibold text-care-ink`}>{topic.title}</Text><Copy muted small>{topic.description}</Copy><Copy small muted>{topic.materialCount} resources</Copy></View><ChevronRight size={18} color="#697C75" /></Pressable>)}</>}
      {view.kind === 'topics' && !!query.trim() && !searching && <>{results.map(result => materialRow(result, { id: result.topicId, title: result.topicTitle, slug: result.topicSlug, materialCount: 0 }))}{results.length === 0 && !error && <Copy muted>No resources match your search.</Copy>}</>}
      {view.kind === 'materials' && !loading && <>{materials.map(m => materialRow(m, view.topic))}{materials.length === 0 && !error && <Copy muted>No resources are available in this topic yet.</Copy>}</>}
      {view.kind === 'detail' && <>
        <Badge>{view.material.type.toUpperCase()}</Badge><View style={tw`my-4`}><Heading>{view.material.title}</Heading></View><Copy muted>{view.material.summary}</Copy>
        {!!view.material.body && <><Section title="Source excerpt" /><Surface><Text selectable style={tw`text-sm leading-7 text-care-ink`}>{view.material.body}</Text></Surface></>}
        {!!view.material.sourceName && <><Section title="Publisher" /><Copy>{view.material.sourceName}</Copy></>}
        <View style={tw`gap-3 mt-4`}>{[...new Set([view.material.url, view.material.sourceUrl].filter((url): url is string => !!url))].filter(url => !view.material.resourceLinks?.some(r => r.url === url)).map((url, i) => <Button key={url} label={i === 0 ? 'Open original resource' : 'Visit publisher'} icon={ExternalLink} secondary onPress={() => void openResource(url)} />)}</View>
        {!!view.material.resourceLinks?.length && <><Section title="Resources and language editions" />{view.material.resourceLinks.map((resource, i) => <Pressable key={`${resource.url}-${i}`} accessibilityRole="link" onPress={() => void openResource(resource.url)} style={tw`p-4 rounded-control bg-white mb-2 flex-row gap-3 items-center`}><Languages size={20} color="#176B58" /><View style={tw`flex-1`}><Text style={tw`text-sm text-care-ink font-medium`}>{resource.title}</Text><Copy muted small>{resource.language} · {resource.type.toUpperCase()}</Copy></View><ExternalLink size={17} color="#697C75" /></Pressable>)}</>}
      </>}
    </ScrollView>
  </View>;
}
