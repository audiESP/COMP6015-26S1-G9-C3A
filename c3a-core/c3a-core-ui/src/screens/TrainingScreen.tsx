// src/screens/TrainingScreen.tsx
import React, { useCallback, useEffect, useState } from 'react';
import {
  Linking,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';

import { fetchTrainingMaterials, fetchTrainingTopics, searchTrainingMaterials } from '../services/api';
import { TrainingMaterial, TrainingSearchResult, TrainingTopic } from '../types';

interface Props {
  onClose: () => void;
}

type ViewState =
  | { screen: 'topics' }
  | { screen: 'materials'; topic: TrainingTopic }
  | { screen: 'material'; topic: TrainingTopic; material: TrainingMaterial };

const typeLabels: Record<TrainingMaterial['type'], string> = {
  article: 'Article',
  video: 'Video',
  pdf: 'PDF',
  link: 'Link',
};

export const TrainingScreen: React.FC<Props> = ({ onClose }) => {
  const { t } = useTranslation();
  const [view, setView] = useState<ViewState>({ screen: 'topics' });
  const [topics, setTopics] = useState<TrainingTopic[]>([]);
  const [materials, setMaterials] = useState<TrainingMaterial[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<TrainingSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTrainingTopics()
      .then((result) => {
        if (!cancelled) setTopics(result.topics);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t('error.network'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setSearchResults([]);
      setSearching(false);
      return;
    }

    let cancelled = false;
    setSearching(true);
    const timer = setTimeout(() => {
      searchTrainingMaterials(trimmed)
        .then((result) => {
          if (!cancelled) setSearchResults(result.results);
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof Error ? err.message : t('error.network'));
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [searchQuery, t]);

  const openTopic = useCallback(
    (topic: TrainingTopic) => {
      setView({ screen: 'materials', topic });
      setLoading(true);
      setError(null);
      fetchTrainingMaterials(topic.id)
        .then((result) => {
          setMaterials(result.materials);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : t('error.network'));
        })
        .finally(() => setLoading(false));
    },
    [t],
  );

  const openMaterial = useCallback((topic: TrainingTopic, material: TrainingMaterial) => {
    setView({ screen: 'material', topic, material });
  }, []);

  const openSearchResult = useCallback((result: TrainingSearchResult) => {
    const topic: TrainingTopic = {
      id: result.topicId,
      slug: result.topicSlug,
      title: result.topicTitle,
      materialCount: 0,
    };
    setSearchQuery('');
    setView({ screen: 'material', topic, material: result });
  }, []);

  const openSource = useCallback((material: TrainingMaterial) => {
    const target = material.sourceUrl ?? material.url;
    if (target) Linking.openURL(target).catch(() => undefined);
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" backgroundColor="#F7FAF8" />
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.iconButton}
          onPress={() => {
            if (view.screen === 'topics') {
              if (searchQuery.trim()) {
                setSearchQuery('');
              } else {
                onClose();
              }
            } else if (view.screen === 'materials') {
              setView({ screen: 'topics' });
            } else {
              setView({ screen: 'materials', topic: view.topic });
            }
          }}
          activeOpacity={0.75}
        >
          <Text style={styles.iconButtonText}>{'‹'}</Text>
        </TouchableOpacity>
        <View style={styles.headerCopy}>
          <Text style={styles.kicker}>{t('training.kicker')}</Text>
          <Text style={styles.title}>
            {view.screen === 'topics' ? t('training.title') : view.screen === 'materials' ? view.topic.title : view.material.title}
          </Text>
        </View>
      </View>

      {view.screen === 'topics' && (
        <View style={styles.searchBar}>
          <TextInput
            style={styles.searchInput}
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder={t('training.searchPlaceholder')}
            placeholderTextColor="#8CA39B"
            autoCorrect={false}
            returnKeyType="search"
          />
          {!!searchQuery && (
            <TouchableOpacity onPress={() => setSearchQuery('')} activeOpacity={0.75}>
              <Text style={styles.searchClear}>{'✕'}</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      <ScrollView style={styles.flex} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {error && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
        {(loading || searching) && (
          <Text style={styles.loadingText}>
            {searching ? t('training.searching') : t('training.loading')}
          </Text>
        )}

        {!searching && view.screen === 'topics' && !!searchQuery.trim() && searchResults.map((result) => (
          <TouchableOpacity
            key={result.id}
            style={styles.card}
            onPress={() => openSearchResult(result)}
            activeOpacity={0.8}
          >
            <Text style={styles.cardTitle}>{result.title}</Text>
            {!!result.summary && <Text style={styles.cardSubtitle}>{result.summary}</Text>}
            <Text style={styles.cardMeta}>
              {result.topicTitle} · {typeLabels[result.type]}
            </Text>
          </TouchableOpacity>
        ))}
        {!searching && view.screen === 'topics' && !!searchQuery.trim() && searchResults.length === 0 && (
          <Text style={styles.emptyText}>{t('training.searchEmpty')}</Text>
        )}

        {!loading && view.screen === 'topics' && !searchQuery.trim() && topics.map((topic) => (
          <TouchableOpacity key={topic.id} style={styles.card} onPress={() => openTopic(topic)} activeOpacity={0.8}>
            <Text style={styles.cardTitle}>{topic.title}</Text>
            {!!topic.description && <Text style={styles.cardSubtitle}>{topic.description}</Text>}
            <Text style={styles.cardMeta}>
              {t('training.materialCount', { count: topic.materialCount })}
            </Text>
          </TouchableOpacity>
        ))}
        {!loading && view.screen === 'topics' && !searchQuery.trim() && topics.length === 0 && !error && (
          <Text style={styles.emptyText}>{t('training.empty')}</Text>
        )}

        {!loading && view.screen === 'materials' && materials.map((material) => (
          <TouchableOpacity
            key={material.id}
            style={styles.card}
            onPress={() => openMaterial(view.topic, material)}
            activeOpacity={0.8}
          >
            <Text style={styles.cardTitle}>{material.title}</Text>
            {!!material.summary && <Text style={styles.cardSubtitle}>{material.summary}</Text>}
            <Text style={styles.cardMeta}>
              {typeLabels[material.type]}
              {material.durationMinutes ? ` · ${material.durationMinutes} min` : ''}
            </Text>
          </TouchableOpacity>
        ))}
        {!loading && view.screen === 'materials' && materials.length === 0 && !error && (
          <Text style={styles.emptyText}>{t('training.empty')}</Text>
        )}

        {view.screen === 'material' && (
          <View style={styles.card}>
            {!!view.material.summary && <Text style={styles.cardSubtitle}>{view.material.summary}</Text>}
            {!!view.material.body && <Text style={styles.excerptLabel}>{t('training.excerptLabel')}</Text>}
            <Text style={styles.bodyText}>{view.material.body}</Text>
            {(view.material.sourceName || view.material.sourceUrl) && (
              <View style={styles.sourceBlock}>
                <Text style={styles.sourceLabel}>{t('training.source')}</Text>
                {!!view.material.sourceName && (
                  <Text style={styles.sourceName}>{view.material.sourceName}</Text>
                )}
                {!!(view.material.sourceUrl ?? view.material.url) && (
                  <TouchableOpacity onPress={() => openSource(view.material)} activeOpacity={0.75}>
                    <Text style={styles.sourceLink}>
                      {typeLabels[view.material.type] === 'PDF'
                        ? t('training.openPdf')
                        : t('training.openLink')}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F7FAF8' },
  flex: { flex: 1 },
  content: { padding: 14, paddingBottom: 24 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 14,
    paddingBottom: 0,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D9E2DE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonText: { color: '#2E6F73', fontSize: 22, fontWeight: '800' },
  headerCopy: { flex: 1 },
  kicker: { color: '#60746B', fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  title: { color: '#16231E', fontSize: 22, fontWeight: '800', marginTop: 2 },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: 14,
    marginTop: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
  },
  searchInput: { flex: 1, color: '#16231E', fontSize: 14, padding: 0 },
  searchClear: { color: '#60746B', fontSize: 14, fontWeight: '700', paddingHorizontal: 4 },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D9E2DE',
    padding: 14,
    marginBottom: 10,
  },
  cardTitle: { color: '#16231E', fontSize: 16, fontWeight: '800' },
  cardSubtitle: { color: '#3D4F49', fontSize: 13, marginTop: 4 },
  cardMeta: { color: '#60746B', fontSize: 12, fontWeight: '700', marginTop: 8 },
  excerptLabel: { color: '#60746B', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginTop: 12 },
  bodyText: { color: '#16231E', fontSize: 14, lineHeight: 21, marginTop: 6, fontStyle: 'italic' },
  sourceBlock: {
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#D9E2DE',
  },
  sourceLabel: { color: '#60746B', fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  sourceName: { color: '#3D4F49', fontSize: 13, marginTop: 4 },
  sourceLink: { color: '#2E6F73', fontSize: 14, fontWeight: '700', marginTop: 8 },
  loadingText: { color: '#60746B', fontSize: 13, marginBottom: 10 },
  emptyText: { color: '#60746B', fontSize: 13 },
  errorBanner: {
    backgroundColor: '#FBEAEA',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E3B7B2',
    padding: 12,
    marginBottom: 10,
  },
  errorText: { color: '#A83B32', fontSize: 13, fontWeight: '600' },
});
