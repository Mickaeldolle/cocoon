import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { neuralApi, secretApi } from '@/src/services/api';
import {
  clearPendingCapture,
  loadPendingCapture,
  savePendingCapture,
  updatePendingCaptureRunId,
  type PendingCapture,
} from '@/src/services/pending-capture';
import { VoiceCapture } from '@/features/assistant/voice-capture';
import { useSecretGesture } from '@/src/hooks/use-secret-gesture';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';

const labels = { now: 'Maintenant', review: 'À vérifier', confirm: 'À confirmer' } as const;

export default function HomeScreen() {
  const token = useSessionStore((state) => state.accessToken);
  const user = useSessionStore((state) => state.user);
  const secretToken = useSecretAccessStore((state) => state.token);
  const clearSecretAccess = useSecretAccessStore((state) => state.clear);
  const client = useQueryClient();
  const secretGestureHandlers = useSecretGesture(() => {
    if (!token) return;
    if (secretToken) void secretApi.lock(token, secretToken).catch(() => undefined);
    clearSecretAccess();
    client.removeQueries({ queryKey: ['secret'] });
    router.push('/secret/unlock');
  });
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'dark' ? darkTheme : lightTheme).colors;
  const styles = makeStyles(colors);
  const [text, setText] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const input = useRef<TextInput>(null);
  const recoveryKey = useRef<string | null>(null);
  const requestController = useRef<AbortController | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const capture = useMutation({
    mutationFn: async (value: string) => {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris';
      const idempotencyKey = `mobile-home-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      if (!user?.id) throw new Error('La session utilisateur n’est pas prête.');
      const pending: PendingCapture = {
        ownerId: user.id,
        text: value,
        timezone,
        idempotencyKey,
        runId: null,
        createdAt: new Date().toISOString(),
      };
      await savePendingCapture(pending);
      const controller = new AbortController();
      requestController.current = controller;
      try {
        return await neuralApi.streamCapture(
          token!,
          value,
          timezone,
          {
            onRunId: (runId) => {
              activeRunIdRef.current = runId;
              void updatePendingCaptureRunId(user.id, idempotencyKey, runId);
            },
            onProgress: ({ text: progressText }) => setNotice(progressText),
          },
          controller.signal,
          { idempotencyKey },
        );
      } catch (error) {
        if (controller.signal.aborted) throw new Error('Capture annulée.');
        const status =
          typeof error === 'object' &&
          error &&
          'status' in error &&
          typeof error.status === 'number'
            ? error.status
            : null;
        if (status !== null && status >= 400 && status < 500) throw error;
        const queued = await neuralApi.queueCapture(token!, value, timezone, idempotencyKey);
        return queued;
      }
    },
    onSuccess: (result) => {
      setText('');
      if (user?.id) void clearPendingCapture(user.id);
      if ('summary' in result) {
        setNotice(result.clarification ?? result.summary);
      } else {
        setNotice('Capture mise en file. Elle reprendra automatiquement dès que possible.');
      }
      void client.invalidateQueries({ queryKey: ['neural-home', user?.id] });
    },
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : 'La capture ne peut pas être traitée.'),
    onSettled: () => {
      requestController.current = null;
      activeRunIdRef.current = null;
    },
  });
  const cancelCapture = async () => {
    const runId = activeRunIdRef.current;
    requestController.current?.abort();
    if (!runId || !token || !user?.id) {
      setNotice('La demande est arrêtée localement ; la capture reste conservée.');
      return;
    }
    try {
      await neuralApi.cancelRun(token, runId);
      await clearPendingCapture(user.id);
      setText('');
      setNotice('Capture annulée. Le texte brut reste conservé côté serveur.');
    } catch {
      setNotice('Le serveur n’a pas confirmé l’annulation. La capture reste conservée.');
    }
  };
  useEffect(() => {
    if (!token || !user?.id || recoveryKey.current === user.id) return;
    recoveryKey.current = user.id;
    let cancelled = false;
    const recover = async () => {
      const pending = await loadPendingCapture(user.id);
      if (!pending || cancelled) return;
      setText((current) => current || pending.text);
      setNotice('Une capture interrompue est conservée. Reprise en cours…');
      let runId = pending.runId;
      if (!runId) {
        try {
          const queued = await neuralApi.queueCapture(
            token,
            pending.text,
            pending.timezone,
            pending.idempotencyKey,
          );
          runId = queued.id;
          await updatePendingCaptureRunId(user.id, pending.idempotencyKey, runId);
        } catch {
          if (!cancelled)
            setNotice('Capture conservée. Elle sera reprise lors d’une nouvelle tentative.');
          return;
        }
      }
      try {
        let run = await neuralApi.getRun(token, runId);
        // After a force-close the worker may still be processing the durable
        // run. Poll briefly so the screen can reconcile the existing run
        // instead of asking the user to submit the same capture again.
        for (let attempt = 0; attempt < 4 && !cancelled; attempt += 1) {
          if (run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') {
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
          if (cancelled) return;
          run = await neuralApi.getRun(token, runId);
        }
        if (cancelled) return;
        if (run.status === 'completed') {
          await clearPendingCapture(user.id, pending.idempotencyKey);
          setText('');
          setNotice('La capture interrompue a été traitée.');
          void client.invalidateQueries({ queryKey: ['neural-home', user.id] });
        } else if (run.status === 'failed' || run.status === 'cancelled') {
          setNotice('La capture conservée doit être relancée depuis le champ ci-dessus.');
        } else {
          setNotice(
            'Capture conservée et toujours en cours. Son état sera vérifié au prochain passage.',
          );
        }
      } catch {
        if (!cancelled) setNotice('Capture conservée. Son état sera vérifié au prochain passage.');
      }
    };
    void recover();
    return () => {
      cancelled = true;
    };
  }, [client, token, user?.id]);
  const home = useQuery({
    queryKey: ['neural-home', user?.id],
    enabled: Boolean(token),
    queryFn: () => neuralApi.home(token!),
    retry: false,
  });
  const confirm = useMutation({
    mutationFn: ({ id, version }: { id: string; version: number | null }) =>
      neuralApi.confirm(token!, id, version ?? undefined),
    onSuccess: () => {
      setNotice('Proposition confirmée.');
      void client.invalidateQueries({ queryKey: ['neural-home', user?.id] });
    },
    onError: () => setNotice('Cette proposition ne peut pas être confirmée pour le moment.'),
  });
  const cancelProposal = useMutation({
    mutationFn: (proposalId: string) => neuralApi.cancel(token!, proposalId),
    onSuccess: () => {
      setNotice('Proposition écartée.');
      void client.invalidateQueries({ queryKey: ['neural-home', user?.id] });
    },
    onError: () => setNotice('Cette proposition ne peut pas être écartée pour le moment.'),
  });
  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.gestureArea} {...secretGestureHandlers}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.top}>
            <View style={styles.heading}>
              <Text style={styles.kicker}>COCOON</Text>
              <Text style={styles.title}>L’essentiel, maintenant.</Text>
            </View>
            <View style={styles.topActions}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Ouvrir mes rappels"
                onPress={() => router.push('/notifications' as never)}
                style={styles.profile}
              >
                <Text style={styles.profileText}>◷</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Ouvrir mon profil"
                onPress={() => router.push('/profile')}
                style={styles.profile}
              >
                <Text style={styles.profileText}>☰</Text>
              </Pressable>
            </View>
          </View>
          <Text style={styles.intro}>
            Déposez ce qui compte. Cocoon garde le contexte et vous aide au bon moment.
          </Text>
          <View style={styles.capture}>
            <TextInput
              ref={input}
              accessibilityLabel="Déposer une pensée"
              multiline
              value={text}
              onChangeText={(value) => {
                setText(value);
                setNotice(null);
              }}
              placeholder="Ex. mardi, Paul vient dîner ; acheter du lait avant"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <VoiceCapture
              accessToken={token}
              colors={colors}
              disabled={!token || !user?.id}
              sending={capture.isPending}
              hasText={!!text.trim()}
              onSend={() => {
                const value = text.trim();
                if (!value) {
                  setNotice('Écrivez un message avant de l’envoyer.');
                  return;
                }
                router.push({ pathname: '/assistant', params: { initial: value } });
              }}
              onError={setNotice}
            />
          </View>
          {capture.isPending ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Annuler la capture"
              onPress={() => void cancelCapture()}
              style={styles.cancel}
            >
              <Text style={styles.cancelText}>Annuler la capture</Text>
            </Pressable>
          ) : null}
          {notice ? (
            <Text accessibilityRole="alert" style={styles.notice}>
              {notice}
            </Text>
          ) : null}
          <Text style={styles.section}>Ce qui mérite votre attention</Text>
          {home.isPending ? (
            <ActivityIndicator color={colors.spruce} style={styles.loader} />
          ) : null}
          {!home.isPending && home.data?.signals.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>Rien à régler maintenant.</Text>
              <Text style={styles.emptyText}>
                Vos prochaines captures feront apparaître ici seulement ce qui devient utile.
              </Text>
            </View>
          ) : null}
          {home.data?.signals.map((signal) => (
            <View key={signal.id} style={styles.signal}>
              <Text style={styles.label}>{labels[signal.kind]}</Text>
              <Text style={styles.signalTitle}>{signal.title}</Text>
              <Text style={styles.reason}>{signal.reason}</Text>
              <Text style={styles.source}>{signal.source}</Text>
              {signal.proposal_id ? (
                <View style={styles.proposalActions}>
                  <Pressable
                    accessibilityRole="button"
                    disabled={confirm.isPending || cancelProposal.isPending}
                    onPress={() =>
                      confirm.mutate({ id: signal.proposal_id!, version: signal.payload_version })
                    }
                    style={[
                      styles.confirm,
                      (confirm.isPending || cancelProposal.isPending) && styles.disabled,
                    ]}
                  >
                    <Text style={styles.confirmText}>Confirmer</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    disabled={confirm.isPending || cancelProposal.isPending}
                    onPress={() => cancelProposal.mutate(signal.proposal_id!)}
                    style={[
                      styles.dismiss,
                      (confirm.isPending || cancelProposal.isPending) && styles.disabled,
                    ]}
                  >
                    <Text style={styles.dismissText}>Écarter</Text>
                  </Pressable>
                </View>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: colors.linen },
    gestureArea: { flex: 1 },
    content: { padding: 24, paddingBottom: 44 },
    top: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: 12,
    },
    heading: { flex: 1, minWidth: 0 },
    topActions: { flexDirection: 'row', gap: 8, flexShrink: 0 },
    kicker: { color: colors.clay, fontSize: 12, fontWeight: '800', letterSpacing: 2 },
    title: {
      color: colors.ink,
      fontSize: 30,
      fontWeight: '700',
      letterSpacing: -0.7,
      marginTop: 8,
    },
    intro: { color: colors.muted, fontSize: 16, lineHeight: 23, marginTop: 12 },
    profile: {
      alignItems: 'center',
      borderColor: colors.border,
      borderRadius: 22,
      borderWidth: 1,
      height: 44,
      justifyContent: 'center',
      width: 44,
    },
    profileText: { color: colors.ink, fontSize: 20 },
    capture: {
      alignItems: 'flex-end',
      backgroundColor: colors.white,
      borderColor: colors.spruce,
      borderRadius: 18,
      borderWidth: 1,
      flexDirection: 'row',
      marginTop: 24,
      padding: 8,
    },
    input: {
      color: colors.ink,
      flex: 1,
      fontSize: 16,
      lineHeight: 22,
      maxHeight: 120,
      minHeight: 52,
      paddingHorizontal: 8,
      paddingTop: 10,
    },
    disabled: { opacity: 0.55 },
    cancel: { alignSelf: 'flex-start', marginTop: 8, paddingHorizontal: 4, paddingVertical: 5 },
    cancelText: { color: colors.clay, fontWeight: '700' },
    notice: { color: colors.clay, lineHeight: 20, marginTop: 9 },
    section: { color: colors.ink, fontSize: 17, fontWeight: '800', marginTop: 30 },
    loader: { marginVertical: 28 },
    empty: {
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 14,
      padding: 18,
    },
    emptyTitle: { color: colors.ink, fontWeight: '800' },
    emptyText: { color: colors.muted, lineHeight: 20, marginTop: 5 },
    signal: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 12,
      padding: 16,
    },
    label: { color: colors.clay, fontSize: 12, fontWeight: '800', letterSpacing: 0.6 },
    signalTitle: { color: colors.ink, fontSize: 17, fontWeight: '800', marginTop: 5 },
    reason: { color: colors.muted, lineHeight: 20, marginTop: 6 },
    source: { color: colors.clay, fontSize: 12, marginTop: 10 },
    confirm: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 12,
      justifyContent: 'center',
      marginTop: 14,
      minHeight: 44,
    },
    confirmText: { color: colors.white, fontWeight: '800' },
    proposalActions: { gap: 8, marginTop: 14 },
    dismiss: {
      alignItems: 'center',
      borderColor: colors.border,
      borderRadius: 12,
      borderWidth: 1,
      justifyContent: 'center',
      minHeight: 44,
    },
    dismissText: { color: colors.muted, fontWeight: '800' },
  });
}
