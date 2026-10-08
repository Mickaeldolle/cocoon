import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { reportButtonPress } from '@/src/services/ui-audit';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { personalApi, type PersonalMemory } from '@/src/services/api';
import {
  formatMemoryDate,
  memoryOriginLabel,
  memorySourceLabel,
  memoryTypeLabel,
} from '@/src/features/memory/presentation';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';

export default function MemoryScreen() {
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const assistantName = useSessionStore((state) => state.user?.assistant_name ?? 'Cocoon');
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const client = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const memories = useInfiniteQuery({
    queryKey: ['personal', 'memories', userId],
    enabled: Boolean(token && userId),
    initialPageParam: 0,
    queryFn: ({ pageParam }) => personalApi.listMemories(token!, 50, pageParam),
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    retry: false,
  });
  const memoryItems = memories.data?.pages.flatMap((page) => page.memories) ?? [];
  const update = useMutation({
    mutationFn: ({
      id,
      summary,
      confidence,
    }: {
      id: string;
      summary: string;
      confidence: number;
    }) => personalApi.updateMemory(token!, id, { summary, confidence }),
    onSuccess: () => {
      setEditing(null);
      setNotice('Mémoire corrigée.');
      void client.invalidateQueries({ queryKey: ['personal', 'memories', userId] });
    },
    onError: () => setNotice('Cette mémoire ne peut pas être corrigée pour le moment.'),
  });
  const forget = useMutation({
    mutationFn: (id: string) => personalApi.forgetMemory(token!, id),
    onSuccess: () => {
      setNotice('Mémoire oubliée.');
      void client.invalidateQueries({ queryKey: ['personal', 'memories', userId] });
    },
    onError: () => setNotice('Cette mémoire ne peut pas être oubliée pour le moment.'),
  });
  const beginEdit = (memory: PersonalMemory) => {
    setEditing(memory.id);
    setDraft(memory.summary);
    setNotice(null);
  };
  const askForget = (memory: PersonalMemory) => {
    const confirmForget = () => {
      reportButtonPress('memory.forget.confirm');
      forget.mutate(memory.id);
    };
    if (Platform.OS === 'web') {
      if (
        window.confirm(
          'Oublier cette mémoire ? Elle ne sera plus utilisée dans les prochains contextes.',
        )
      ) {
        confirmForget();
      } else {
        reportButtonPress('memory.forget.cancel');
      }
      return;
    }
    Alert.alert(
      'Oublier cette mémoire ?',
      'Elle ne sera plus utilisée dans les prochains contextes.',
      [
        {
          text: 'Annuler',
          style: 'cancel',
          onPress: () => reportButtonPress('memory.forget.cancel'),
        },
        {
          text: 'Oublier',
          style: 'destructive',
          onPress: confirmForget,
        },
      ],
    );
  };
  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable
          auditAction="memory.back"
          accessibilityRole="button"
          onPress={() => router.replace('/profile')}
          style={styles.back}
        >
          <Text style={styles.backText}>‹ Profil</Text>
        </Pressable>
        <Text style={styles.kicker}>MÉMOIRE PERSONNELLE</Text>
        <Text style={styles.title}>Ce que {assistantName} retient</Text>
        <Text style={styles.intro}>
          Ces informations sont propres à votre compte. Vous pouvez les corriger ou les oublier à
          tout moment.
        </Text>
        {notice ? (
          <Text accessibilityRole="alert" style={styles.notice}>
            {notice}
          </Text>
        ) : null}
        {memories.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {memories.isError && !memories.data ? (
          <View style={styles.alert}>
            <Text style={styles.alertTitle}>La mémoire ne peut pas être chargée.</Text>
            <Pressable
              auditAction="memory.retry"
              onPress={() => void memories.refetch()}
              style={styles.retry}
            >
              <Text style={styles.retryText}>Réessayer</Text>
            </Pressable>
          </View>
        ) : null}
        {!memories.isPending && !memories.isError && memoryItems.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Aucune mémoire personnelle.</Text>
            <Text style={styles.emptyText}>
              Confirmez une pensée depuis l’assistant pour commencer.
            </Text>
          </View>
        ) : null}
        {memoryItems.map((memory) => {
          const isEditing = editing === memory.id;
          return (
            <View key={memory.id} style={styles.card}>
              <Text style={styles.kind}>
                {memoryTypeLabel(memory.memory_type)} · confiance {memory.confidence}%
              </Text>
              {isEditing ? (
                <TextInput
                  accessibilityLabel="Résumé de la mémoire"
                  multiline
                  value={draft}
                  onChangeText={setDraft}
                  style={styles.input}
                />
              ) : (
                <Text style={styles.summary}>{memory.summary}</Text>
              )}
              <Text style={styles.reason}>{memory.reason}</Text>
              <Text style={styles.source}>Origine : {memoryOriginLabel(memory.origin)}</Text>
              <Text style={styles.source}>
                Source : {memorySourceLabel(memory.source_type, memory.source_run_id)}
              </Text>
              <Text style={styles.source}>
                Portée : {memory.scope_type === 'project' ? 'projet personnel' : 'personnelle'} ·
                État : {memory.state === 'active' ? 'active' : 'inactive'}
              </Text>
              <Text style={styles.source}>
                {memory.observed_at ? 'Observée' : 'Ajoutée'} le{' '}
                {formatMemoryDate(memory.observed_at ?? memory.created_at)}
              </Text>
              <View style={styles.actions}>
                {isEditing ? (
                  <Pressable
                    auditAction="memory.edit.save"
                    accessibilityRole="button"
                    disabled={!draft.trim() || update.isPending}
                    onPress={() =>
                      update.mutate({
                        id: memory.id,
                        summary: draft.trim(),
                        confidence: memory.confidence,
                      })
                    }
                    style={[styles.primary, (!draft.trim() || update.isPending) && styles.disabled]}
                  >
                    <Text style={styles.primaryText}>Enregistrer</Text>
                  </Pressable>
                ) : (
                  <Pressable
                    auditAction="memory.edit.open"
                    accessibilityRole="button"
                    onPress={() => beginEdit(memory)}
                    style={styles.secondary}
                  >
                    <Text style={styles.secondaryText}>Corriger</Text>
                  </Pressable>
                )}
                <Pressable
                  auditAction="memory.forget.prompt"
                  accessibilityRole="button"
                  disabled={forget.isPending}
                  onPress={() => askForget(memory)}
                  style={[styles.forget, forget.isPending && styles.disabled]}
                >
                  <Text style={styles.forgetText}>Oublier</Text>
                </Pressable>
              </View>
            </View>
          );
        })}
        {memories.isFetchNextPageError ? (
          <View style={styles.alert}>
            <Text style={styles.alertTitle}>La suite des mémoires ne peut pas être chargée.</Text>
            <Pressable
              auditAction="memory.more.retry"
              accessibilityRole="button"
              onPress={() => void memories.fetchNextPage()}
              style={styles.retry}
            >
              <Text style={styles.retryText}>Réessayer</Text>
            </Pressable>
          </View>
        ) : null}
        {memories.hasNextPage && !memories.isFetchNextPageError ? (
          <Pressable
            auditAction="memory.more"
            accessibilityRole="button"
            disabled={memories.isFetchingNextPage}
            onPress={() => void memories.fetchNextPage()}
            style={[styles.more, memories.isFetchingNextPage && styles.disabled]}
          >
            <Text style={styles.moreText}>
              {memories.isFetchingNextPage ? 'Chargement…' : 'Voir plus de mémoires'}
            </Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    content: { padding: 24, paddingBottom: 44 },
    back: { minHeight: 44, justifyContent: 'center' },
    backText: { color: colors.spruce, fontWeight: '800' },
    kicker: {
      color: colors.clay,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.4,
      marginTop: 14,
    },
    title: { color: colors.ink, fontSize: 30, fontWeight: '700', marginTop: 7 },
    intro: { color: colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
    notice: { color: colors.clay, lineHeight: 20, marginTop: 14 },
    loader: { marginVertical: 34 },
    alert: {
      backgroundColor: colors.berrySoft,
      borderColor: colors.berry,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 16,
    },
    alertTitle: { color: colors.ink, fontWeight: '800' },
    retry: { marginTop: 8, minHeight: 40, justifyContent: 'center' },
    retryText: { color: colors.spruce, fontWeight: '800' },
    empty: {
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 18,
    },
    emptyTitle: { color: colors.ink, fontWeight: '800' },
    emptyText: { color: colors.muted, lineHeight: 20, marginTop: 6 },
    card: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 14,
      padding: 16,
    },
    kind: { color: colors.clay, fontSize: 12, fontWeight: '800', letterSpacing: 0.4 },
    summary: { color: colors.ink, fontSize: 17, fontWeight: '700', lineHeight: 23, marginTop: 8 },
    input: {
      backgroundColor: colors.linen,
      borderColor: colors.spruce,
      borderRadius: 10,
      borderWidth: 1,
      color: colors.ink,
      lineHeight: 21,
      marginTop: 8,
      minHeight: 70,
      padding: 10,
    },
    reason: { color: colors.muted, lineHeight: 20, marginTop: 8 },
    source: { color: colors.clay, fontSize: 12, marginTop: 10 },
    more: {
      alignItems: 'center',
      borderColor: colors.spruce,
      borderRadius: 12,
      borderWidth: 1,
      justifyContent: 'center',
      minHeight: 44,
      marginTop: 18,
      paddingHorizontal: 14,
    },
    moreText: { color: colors.spruce, fontWeight: '800' },
    actions: { alignItems: 'center', flexDirection: 'row', gap: 10, marginTop: 14 },
    primary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 12,
      justifyContent: 'center',
      minHeight: 42,
      paddingHorizontal: 14,
    },
    primaryText: { color: colors.white, fontWeight: '800' },
    secondary: {
      borderColor: colors.spruce,
      borderRadius: 12,
      borderWidth: 1,
      minHeight: 42,
      justifyContent: 'center',
      paddingHorizontal: 14,
    },
    secondaryText: { color: colors.spruce, fontWeight: '800' },
    forget: { minHeight: 42, justifyContent: 'center', paddingHorizontal: 10 },
    forgetText: { color: colors.berry, fontWeight: '800' },
    disabled: { opacity: 0.55 },
  });
}
