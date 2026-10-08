import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { useQueryClient } from '@tanstack/react-query';
import { Redirect, router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { authApi, neuralApi, secretApi } from '@/src/services/api';
import {
  homePushAction,
  personalNotificationPermission,
  registerForPersonalNotifications,
} from '@/src/services/notifications';
import {
  clearPendingCapture,
  loadPendingCapture,
  updatePendingCaptureRunId,
} from '@/src/services/pending-capture';
import { AssistantOrb } from '@/features/assistant/assistant-orb';
import { homeReplyKey, requestHomeReply } from '@/features/assistant/home-reply';
import { VoiceCapture } from '@/features/assistant/voice-capture';
import { useSecretGesture } from '@/src/hooks/use-secret-gesture';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, subtleBackground, type ColorTokens } from '@/src/theme';

export default function HomeScreen() {
  const initialized = useSessionStore((state) => state.initialized);
  const token = useSessionStore((state) => state.accessToken);
  const user = useSessionStore((state) => state.user);
  const deferredNotificationAccountId = useSessionStore(
    (state) => state.deferredNotificationAccountId,
  );
  const refreshUser = useSessionStore((state) => state.refreshUser);
  const assistantEnabled = user?.enable_assistant === true;
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
  const [opening, setOpening] = useState(false);
  const streamAbort = useRef<AbortController | null>(null);
  const previousTurn = useRef<{ owner: string; key: string; text: string } | null>(null);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  useFocusEffect(
    useCallback(() => {
      setOpening(false);
      if (!assistantEnabled || previousTurn.current?.owner !== user?.id) {
        previousTurn.current = null;
      }
      return () => {
        streamAbort.current?.abort();
        streamAbort.current = null;
      };
    }, [user?.id, assistantEnabled]),
  );
  useEffect(() => {
    const show = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow',
      () => setKeyboardVisible(true),
    );
    const hide = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide',
      () => setKeyboardVisible(false),
    );
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  useFocusEffect(
    useCallback(() => {
      void refreshUser().catch(() => undefined);
    }, [refreshUser]),
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [pushAction, setPushAction] = useState<'offer' | 'blocked' | 'retry' | null>(null);
  const [pushError, setPushError] = useState<string | null>(null);
  const [pushBusy, setPushBusy] = useState(false);
  const orbSize = Math.max(100, Math.min(width - 48, height - 340 - (pushAction ? 150 : 0), 380));
  const checkPush = useCallback(
    async (isCancelled: () => boolean = () => false) => {
      if (!token || !user?.id) return;
      if (deferredNotificationAccountId === user?.id) {
        setPushAction(null);
        return;
      }
      try {
        const consents = await authApi.listConsents(token);
        if (isCancelled()) return;
        const permission = await personalNotificationPermission();
        if (isCancelled()) return;
        const action = homePushAction(consents, permission, Platform.OS);
        if (action === 'skip') {
          setPushAction(null);
        } else if (action === 'blocked') {
          setPushAction('blocked');
        } else if (action === 'offer') {
          setPushAction('offer');
        } else {
          await registerForPersonalNotifications(token);
          if (!isCancelled()) {
            setPushAction(null);
            setPushError(null);
          }
        }
      } catch (error) {
        if (isCancelled()) return;
        const permission = await personalNotificationPermission().catch(() => 'unsupported');
        if (isCancelled()) return;
        setPushAction(permission === 'denied' ? 'blocked' : 'retry');
        setPushError(
          error instanceof Error ? error.message : 'Inscription aux notifications impossible.',
        );
      }
    },
    [token, user?.id, deferredNotificationAccountId],
  );
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      void checkPush(() => cancelled);
      return () => {
        cancelled = true;
      };
    }, [checkPush]),
  );
  const enablePush = () => {
    if (!token || pushBusy) return;
    setPushBusy(true);
    setPushError(null);
    void registerForPersonalNotifications(token)
      .then(() => {
        setPushAction(null);
        setPushError(null);
      })
      .catch(async (error) => {
        const permission = await personalNotificationPermission().catch(() => 'unsupported');
        setPushAction(permission === 'denied' ? 'blocked' : 'offer');
        setPushError(
          error instanceof Error ? error.message : 'Inscription aux notifications impossible.',
        );
      })
      .finally(() => setPushBusy(false));
  };
  const input = useRef<TextInput>(null);
  const recoveryKey = useRef<string | null>(null);
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
          setNotice('La capture conservée doit être relancée depuis le champ de message.');
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
  const cancelStreaming = () => {
    streamAbort.current?.abort();
    streamAbort.current = null;
    setOpening(false);
    setNotice('Génération arrêtée. Votre message est conservé.');
  };
  const openAssistant = async () => {
    if (!assistantEnabled || !token || !user?.id || streamAbort.current) return;
    const value = text.trim();
    if (!value) {
      setNotice('Écrivez un message avant de l’envoyer.');
      input.current?.focus();
      return;
    }
    const controller = new AbortController();
    streamAbort.current = controller;
    const owner = user.id;
    const previous = previousTurn.current;
    const retry = previous?.owner === owner && previous.text === value;
    const key = retry
      ? previous.key
      : `mobile-chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    previousTurn.current = { owner, key, text: value };
    setOpening(true);
    setNotice(null);
    Keyboard.dismiss();
    try {
      const reply = await requestHomeReply(
        client,
        token,
        owner,
        { key, text: value, retry },
        controller.signal,
      );
      const session = useSessionStore.getState();
      if (
        streamAbort.current !== controller ||
        controller.signal.aborted ||
        session.user?.id !== owner ||
        !session.user.enable_assistant
      )
        return;
      // Only the opaque key goes into the URL. The completed turn is handed off in memory.
      const cacheKey = homeReplyKey(owner, key);
      client.setQueryDefaults(['assistant', 'home-reply'], { gcTime: 60_000 });
      client.setQueryData(cacheKey, reply);
      void client.invalidateQueries({ queryKey: ['assistant', 'history', owner] });
      previousTurn.current = null;
      setText('');
      router.push({ pathname: '/assistant', params: { completed: key } });
    } catch (error) {
      if (streamAbort.current !== controller) return;
      setNotice(error instanceof Error ? error.message : 'Le modèle est indisponible. Réessayez.');
    } finally {
      if (streamAbort.current === controller) {
        streamAbort.current = null;
        setOpening(false);
      }
    }
  };
  if (initialized && (!token || !user)) return <Redirect href="/sign-in" />;
  if (initialized && user && !user.welcome_completed_at)
    return <Redirect href={'/welcome' as never} />;
  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        enabled={Platform.OS !== 'web'}
        keyboardVerticalOffset={0}
        style={styles.flex}
      >
        <View style={styles.gestureArea} {...secretGestureHandlers}>
          <View style={styles.top}>
            <View style={styles.heading}>
              <Text style={styles.kicker}>{user?.assistant_name ?? 'COCOON'}</Text>
            </View>
            <View style={styles.topActions}>
              <Pressable
                auditAction="home.notifications.open"
                accessibilityRole="button"
                accessibilityLabel="Ouvrir mes rappels"
                onPress={() => router.push('/notifications' as never)}
                style={styles.profile}
              >
                <Text style={styles.profileText}>◷</Text>
              </Pressable>
              <Pressable
                auditAction="home.profile.open"
                accessibilityRole="button"
                accessibilityLabel="Ouvrir mon profil"
                onPress={() => router.push('/profile')}
                style={styles.profile}
              >
                <Text style={styles.profileText}>☰</Text>
              </Pressable>
            </View>
          </View>
          <ScrollView
            style={styles.flex}
            contentContainerStyle={styles.content}
            keyboardDismissMode="interactive"
            keyboardShouldPersistTaps="handled"
          >
            {pushAction ? (
              <View style={styles.pushCard}>
                <Text style={styles.pushTitle}>Notifications</Text>
                <Text style={styles.pushText}>
                  {pushAction === 'blocked'
                    ? `Autorisez les notifications dans les réglages du ${Platform.OS === 'web' ? 'navigateur' : 'téléphone'}.`
                    : pushAction === 'retry'
                      ? 'Impossible de vérifier votre inscription aux notifications.'
                      : 'Recevez vos rappels et nouveaux messages sur cet appareil.'}
                </Text>
                {pushError ? (
                  <Text accessibilityRole="alert" style={styles.pushError}>
                    {pushError}
                  </Text>
                ) : null}
                {pushAction !== 'blocked' ? (
                  <Pressable
                    auditAction="home.notifications.enable"
                    accessibilityRole="button"
                    disabled={pushBusy}
                    onPress={pushAction === 'retry' ? () => void checkPush() : enablePush}
                    style={[styles.pushButton, pushBusy && styles.disabled]}
                  >
                    <Text style={styles.pushButtonText}>
                      {pushBusy
                        ? 'Activation…'
                        : pushAction === 'retry'
                          ? 'Réessayer'
                          : 'Activer les notifications'}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            ) : null}
            <View style={styles.presence}>
              <AssistantOrb size={orbSize} active={opening} enabled={assistantEnabled} />
              <Text style={styles.presenceTitle}>{user?.assistant_name ?? 'Cocoon'}</Text>
              <Text accessibilityLiveRegion="polite" style={styles.presenceStatus}>
                {opening
                  ? 'Votre assistant prépare sa réponse…'
                  : assistantEnabled
                    ? 'Que souhaitez-vous partager ?'
                    : 'Assistant indisponible'}
              </Text>
              <Pressable
                auditAction="home.assistant.open"
                accessibilityRole="button"
                accessibilityLabel="Ouvrir la conversation avec votre assistant"
                accessibilityState={{ disabled: opening }}
                disabled={opening}
                onPress={() => router.push('/assistant')}
                style={({ pressed }) => [styles.conversationLink, pressed && styles.pressed]}
              >
                <Text style={styles.conversationLinkIcon}>chat_bubble_outline</Text>
                <Text style={styles.conversationLinkText}>Voir la conversation</Text>
                <Text style={styles.conversationLinkIcon}>arrow_forward</Text>
              </Pressable>
            </View>
          </ScrollView>
          <View
            style={[
              styles.composer,
              { paddingBottom: keyboardVisible ? 12 : Math.max(insets.bottom, 24) },
            ]}
          >
            {notice ? (
              <Text accessibilityRole="alert" style={styles.notice}>
                {notice}
              </Text>
            ) : null}
            <View style={styles.capture}>
              <TextInput
                ref={input}
                accessibilityLabel="Votre message"
                editable={assistantEnabled && !opening}
                multiline={false}
                blurOnSubmit={false}
                returnKeyType="send"
                onSubmitEditing={openAssistant}
                value={text}
                onChangeText={(value) => {
                  setText(value);
                  setNotice(null);
                }}
                placeholder="Écrire un message"
                placeholderTextColor={colors.muted}
                style={styles.input}
                textAlignVertical="center"
              />
              <VoiceCapture
                accessToken={token}
                colors={colors}
                variant="chat"
                disabled={!token || !user?.id || !assistantEnabled}
                sending={opening}
                hasText={!!text.trim()}
                onSend={openAssistant}
                onCancelSend={cancelStreaming}
                onError={setNotice}
              />
            </View>
            {!assistantEnabled ? (
              <Text accessibilityRole="alert" style={styles.accessNotice}>
                Vous n&apos;avez pas accès à cette fonctionnalité
              </Text>
            ) : null}
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { flex: 1, ...subtleBackground(colors) },
    flex: { flex: 1, minHeight: 0 },
    gestureArea: { flex: 1, minHeight: 0 },
    content: { flexGrow: 1, paddingHorizontal: 24, paddingBottom: 16 },
    top: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 12,
      paddingHorizontal: 24,
      paddingTop: 16,
      paddingBottom: 8,
    },
    heading: { flex: 1, minWidth: 0 },
    topActions: { flexDirection: 'row', gap: 8, flexShrink: 0 },
    kicker: { color: colors.ink, fontSize: 16, fontWeight: '800', letterSpacing: 3 },
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
    presence: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 16 },
    presenceTitle: {
      color: colors.ink,
      fontSize: 24,
      fontWeight: '600',
      letterSpacing: -0.5,
      textAlign: 'center',
    },
    presenceStatus: {
      color: colors.muted,
      fontSize: 14,
      lineHeight: 22,
      marginTop: 8,
      textAlign: 'center',
    },
    conversationLink: {
      alignItems: 'center',
      flexDirection: 'row',
      gap: 7,
      minHeight: 44,
      marginTop: 18,
      paddingHorizontal: 8,
    },
    conversationLinkIcon: {
      color: colors.clay,
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 18,
    },
    conversationLinkText: { color: colors.clay, fontSize: 13, fontWeight: '600' },
    composer: {
      paddingHorizontal: 24,
      paddingTop: 12,
      width: '100%',
      maxWidth: 760,
      alignSelf: 'center',
    },
    capture: { alignItems: 'flex-end', flexDirection: 'row', gap: 8 },
    input: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 22,
      borderWidth: 1,
      color: colors.ink,
      flex: 1,
      minWidth: 0,
      fontSize: 15,
      minHeight: 44,
      paddingHorizontal: 15,
      paddingVertical: 10,
      boxShadow: '0 2px 5px rgba(0, 0, 0, 0.08)',
    },
    accessNotice: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 8 },
    notice: { color: colors.clay, lineHeight: 20, marginBottom: 9 },
    pressed: { opacity: 0.7 },
    disabled: { opacity: 0.55 },
    pushCard: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 14,
      borderWidth: 1,
      marginTop: 16,
      padding: 14,
      maxWidth: 712,
      width: '100%',
      alignSelf: 'center',
    },
    pushTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' },
    pushText: { color: colors.muted, fontSize: 13, lineHeight: 18, marginTop: 4 },
    pushError: { color: colors.berry, fontSize: 12, lineHeight: 17, marginTop: 6 },
    pushButton: {
      alignItems: 'center',
      alignSelf: 'flex-start',
      backgroundColor: colors.spruce,
      borderRadius: 10,
      justifyContent: 'center',
      marginTop: 10,
      minHeight: 44,
      paddingHorizontal: 14,
    },
    pushButtonText: { color: colors.white, fontSize: 13, fontWeight: '800' },
  });
}
