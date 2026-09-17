import React, { useState } from 'react';
import { ActivityIndicator, Linking, Pressable, Text, View } from 'react-native';
import { ChevronDown, ExternalLink, Globe, Library } from 'lucide-react-native';
import type { CareTask, TaskMaterialItem } from '../types';
import { fetchTaskMaterials } from '../services/api';
import tw from './tw';

// Lazily fetches training material for one care task and shows it collapsed
// under the task row. Internal (RAG/training-library) and web results are
// visually tagged so a worker always knows whether a snippet came from the
// project's own guidance or from an internet search.
export function TaskTrainingMaterials({ task, disabled }: { task: CareTask; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<TaskMaterialItem[] | null>(null);
  const [usedWebSearch, setUsedWebSearch] = useState(false);

  const toggle = async () => {
    if (disabled) return;
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (items !== null || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchTaskMaterials(task.label, task.detail, task.type);
      setItems(res.items);
      setUsedWebSearch(res.usedWebSearch);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load training material.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={tw`-mt-1.5 mb-2 ml-2`}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open, disabled }}
        disabled={disabled}
        onPress={() => void toggle()}
        style={tw`flex-row items-center gap-1.5 py-1`}
      >
        <Library size={13} color="#176B58" />
        <Text style={tw`text-xs text-care-primary font-medium`}>Training material</Text>
        <ChevronDown size={13} color="#176B58" style={tw.style(open && 'rotate-180')} />
      </Pressable>

      {open && (
        <View style={tw`bg-care-soft rounded-control p-3 gap-2.5 mb-1`}>
          {loading && (
            <View style={tw`flex-row items-center gap-2 py-1`}>
              <ActivityIndicator size="small" color="#176B58" />
              <Text style={tw`text-xs text-care-muted`}>Searching project guidance and, if needed, the web...</Text>
            </View>
          )}
          {!loading && error && <Text style={tw`text-xs text-care-amber`}>{error}</Text>}
          {!loading && !error && items?.length === 0 && (
            <Text style={tw`text-xs text-care-muted`}>No relevant training material found for this task.</Text>
          )}
          {!loading && !error && !!items?.length && (
            <>
              {usedWebSearch && (
                <Text style={tw`text-[11px] text-care-amber`}>
                  Project guidance was limited for this task, so results were supplemented from the web. Web results are not project-reviewed — verify before relying on them.
                </Text>
              )}
              {items.map((item, index) => <TaskMaterialCard key={`${item.sourceType}-${index}`} item={item} />)}
            </>
          )}
        </View>
      )}
    </View>
  );
}

function TaskMaterialCard({ item }: { item: TaskMaterialItem }) {
  const isWeb = item.sourceType === 'web';
  return (
    <Pressable
      accessibilityRole={isWeb ? 'link' : undefined}
      disabled={!isWeb || !item.url}
      onPress={() => { if (isWeb && item.url) void Linking.openURL(item.url); }}
      style={tw`bg-white rounded-xl p-3 border border-care-line`}
    >
      <View style={tw`flex-row items-center gap-1.5 mb-1.5`}>
        {isWeb ? <Globe size={12} color="#80551C" /> : <Library size={12} color="#176B58" />}
        <Text style={tw.style('text-[10px] font-semibold uppercase tracking-wide', isWeb ? 'text-care-amber' : 'text-care-primary')}>
          {isWeb ? 'Web source' : 'Internal training / guideline'}
        </Text>
      </View>
      <Text style={tw`text-sm font-medium text-care-ink`}>{item.title}</Text>
      {!!item.section && <Text style={tw`text-xs text-care-muted mt-0.5`}>{item.section}{item.pageLabel ? ` · ${item.pageLabel}` : ''}</Text>}
      {!!item.snippet && <Text style={tw`text-xs text-care-muted mt-1.5 leading-5`}>{item.snippet}</Text>}
      {isWeb && !!item.url && (
        <View style={tw`flex-row items-center gap-1 mt-2`}>
          <ExternalLink size={11} color="#80551C" />
          <Text style={tw`text-[11px] text-care-amber`} numberOfLines={1}>{item.url}</Text>
        </View>
      )}
    </Pressable>
  );
}
