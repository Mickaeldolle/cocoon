import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Crypto from 'expo-crypto';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { File } from 'expo-file-system';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  ApiError,
  conversationsApi,
  realtimeSocketUrl,
  secretApi,
  type Message,
} from '@/src/services/api';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, subtleBackground, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(value),
  );
}

type LocalMessage = Message & {
  localId: string;
  conversationId: string;
  ownerId: string;
  delivery: 'pending' | 'sent' | 'failed';
  serverId?: string;
};

function isLocalMessage(message: Message | LocalMessage): message is LocalMessage {
  return 'localId' in message;
}

function formatDuration(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function ConversationDetailScreen({ secret = false }: { secret?: boolean }) {
  const { id } = useLocalSearchParams<{ id: string }>();
  const token = useSessionStore((state) => state.accessToken);
  const secretToken = useSecretAccessStore((state) => state.token);
  const clearSecretAccess = useSecretAccessStore((state) => state.clear);
  const user = useSessionStore((state) => state.user);
  const userId = user?.id;
  const client = useQueryClient();
  const [body, setBody] = useState('');
  const bodyRef = useRef('');
  const [error, setError] = useState<string | null>(null);
  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const [typingConversationId, setTypingConversationId] = useState<string | null>(null);
  const [voiceDraft, setVoiceDraft] = useState<{ uri: string; duration: number } | null>(null);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [micPressed, setMicPressed] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const nearBottom = useRef(true);
  const socket = useRef<WebSocket | null>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const remoteTypingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceDraftUri = useRef<string | null>(null);
  const recordingActive = useRef(false);
  const voiceHeld = useRef(false);
  const voiceOperationBusy = useRef(false);
  const voiceStartedAt = useRef(0);
  const lastTypingSent = useRef(0);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const player = useAudioPlayer();
  const insets = useSafeAreaInsets();
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors, mode);
  const messagesKey = secret ? ['secret', 'messages', id] : ['messages', id, userId];
  const conversation = useQuery({
    queryKey: secret ? ['secret', 'conversation', id] : ['conversation', id, userId],
    enabled: Boolean(token && id && (!secret || secretToken)),
    queryFn: () =>
      secret
        ? secretApi.getConversation(token!, secretToken!, id)
        : conversationsApi.get(token!, id),
    retry: !secret,
  });
  const messages = useQuery({
    queryKey: messagesKey,
    enabled: Boolean(token && id && (!secret || secretToken)),
    queryFn: () =>
      secret
        ? secretApi.listMessages(token!, secretToken!, id)
        : conversationsApi.listMessages(token!, id),
    refetchInterval: 4000,
    retry: !secret,
  });
  const secretTyping = useQuery({
    queryKey: ['secret', 'typing', id],
    enabled: Boolean(secret && token && secretToken && id),
    queryFn: () => secretApi.getTyping(token!, secretToken!, id),
    refetchInterval: 1500,
    retry: false,
  });
  const correspondentTyping = secret
    ? secretTyping.data?.is_typing === true
    : typingConversationId === id;
  const recipientName = conversation.data?.recipient_name?.trim() ?? '';
  const visibleMessages = [
    ...(messages.data ?? []),
    ...localMessages.filter(
      (message) =>
        message.conversationId === id &&
        message.ownerId === userId &&
        !messages.data?.some((saved) => saved.id === message.id),
    ),
  ].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));

  useEffect(() => {
    voiceDraftUri.current = voiceDraft?.uri ?? null;
  }, [voiceDraft]);

  useEffect(
    () => () => {
      voiceHeld.current = false;
      if (recordingActive.current) {
        void recorder.stop().then(() => {
          void setAudioModeAsync({ allowsRecording: false });
          if (recorder.uri) {
            try {
              new File(recorder.uri).delete();
            } catch {
              // The temporary recording may already be gone.
            }
          }
        });
      }
      if (voiceDraftUri.current) {
        try {
          new File(voiceDraftUri.current).delete();
        } catch {
          /* Temporary recording is already gone. */
        }
      }
    },
    [recorder],
  );

  useEffect(() => {
    if (secret || !token || !id || !userId) return;
    let stopped = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let activeSocket: WebSocket | null = null;
    async function connect() {
      try {
        const { ticket } = await conversationsApi.issueRealtimeTicket(token!);
        if (stopped) return;
        const nextSocket = new WebSocket(realtimeSocketUrl());
        activeSocket = nextSocket;
        socket.current = nextSocket;
        nextSocket.onopen = () => nextSocket.send(JSON.stringify({ type: 'authenticate', ticket }));
        nextSocket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.conversation_id !== id) return;
            if (payload.type === 'message.created') {
              setTypingConversationId(null);
              void client.invalidateQueries({ queryKey: ['messages', id, userId] });
            } else if (payload.type === 'conversation.typing' && payload.user_id !== userId) {
              setTypingConversationId(payload.is_typing === true ? id : null);
              if (remoteTypingTimer.current) clearTimeout(remoteTypingTimer.current);
              if (payload.is_typing === true) {
                remoteTypingTimer.current = setTimeout(() => setTypingConversationId(null), 4500);
              }
            }
          } catch {
            // Ignore malformed realtime events; polling remains the fallback.
          }
        };
        nextSocket.onclose = () => {
          if (socket.current === nextSocket) socket.current = null;
          setTypingConversationId(null);
          if (!stopped) reconnectTimer = setTimeout(() => void connect(), 3000);
        };
        nextSocket.onerror = () => nextSocket.close();
      } catch {
        if (!stopped) reconnectTimer = setTimeout(() => void connect(), 3000);
      }
    }
    void connect();
    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (remoteTypingTimer.current) clearTimeout(remoteTypingTimer.current);
      if (typingTimer.current) clearTimeout(typingTimer.current);
      activeSocket?.close();
      if (socket.current === activeSocket) socket.current = null;
    };
  }, [client, id, secret, token, userId]);

  useEffect(() => {
    if (secret && (!token || !secretToken)) router.replace('/home');
  }, [secret, secretToken, token]);

  function publishTyping(isTyping: boolean) {
    if (secret) {
      if (token && secretToken) {
        void secretApi.setTyping(token, secretToken, id, isTyping).catch(() => undefined);
      }
      return;
    }
    if (socket.current?.readyState !== WebSocket.OPEN) return;
    socket.current.send(
      JSON.stringify({ type: 'conversation.typing', conversation_id: id, is_typing: isTyping }),
    );
  }

  function updateBody(value: string) {
    bodyRef.current = value;
    setBody(value);
    setError(null);
    if (typingTimer.current) clearTimeout(typingTimer.current);
    if (value.trim()) {
      if (Date.now() - lastTypingSent.current > 1500) {
        publishTyping(true);
        lastTypingSent.current = Date.now();
      }
      typingTimer.current = setTimeout(() => {
        publishTyping(false);
        lastTypingSent.current = 0;
      }, 2200);
    } else {
      publishTyping(false);
      lastTypingSent.current = 0;
    }
  }
  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const showSubscription = Keyboard.addListener(showEvent, () => setKeyboardVisible(true));
    const hideSubscription = Keyboard.addListener(hideEvent, () => setKeyboardVisible(false));
    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, []);
  useEffect(() => {
    if (nearBottom.current) {
      requestAnimationFrame(() => scroll.current?.scrollToEnd({ animated: true }));
    }
  }, [visibleMessages.length, correspondentTyping]);
  const send = useMutation({
    mutationFn: ({ text, localId }: { text: string; localId: string }) =>
      secret
        ? secretApi.sendMessage(token!, secretToken!, id, text, localId)
        : conversationsApi.sendMessage(token!, id, text, localId),
    onSuccess: (saved, { localId }) => {
      setLocalMessages((items) =>
        items.map((item) =>
          item.localId === localId ? { ...item, delivery: 'sent', serverId: saved.id } : item,
        ),
      );
      setError(null);
      void client.invalidateQueries({ queryKey: messagesKey });
      void client.invalidateQueries({
        queryKey: secret ? ['secret', 'conversations'] : ['conversations', userId],
      });
    },
    onError: (caught, { localId }) => {
      setLocalMessages((items) =>
        items.map((item) => (item.localId === localId ? { ...item, delivery: 'failed' } : item)),
      );
      setError(caught instanceof ApiError ? caught.message : 'Envoi impossible. Réessayez.');
    },
  });
  function submit() {
    const text = bodyRef.current.trim();
    if (!text || !userId || (secret && !secretToken)) return;
    const localId = Crypto.randomUUID();
    setLocalMessages((items) => [
      ...items,
      {
        localId,
        conversationId: id,
        ownerId: userId,
        id: localId,
        sender_id: userId,
        body: text,
        created_at: new Date().toISOString(),
        read_by_count: 0,
        delivery: 'pending',
      },
    ]);
    bodyRef.current = '';
    setBody('');
    nearBottom.current = true;
    setError(null);
    if (typingTimer.current) clearTimeout(typingTimer.current);
    publishTyping(false);
    lastTypingSent.current = 0;
    send.mutate({ text, localId });
  }

  function retry(message: LocalMessage) {
    if (message.delivery !== 'failed') return;
    setLocalMessages((items) =>
      items.map((item) =>
        item.localId === message.localId ? { ...item, delivery: 'pending' } : item,
      ),
    );
    setError(null);
    send.mutate({ text: message.body, localId: message.localId });
  }

  async function startVoice() {
    if (voiceOperationBusy.current || recordingActive.current || !voiceHeld.current) return;
    voiceOperationBusy.current = true;
    setVoiceBusy(true);
    setError(null);
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setError('Autorisez le micro pour enregistrer un message vocal.');
        return;
      }
      if (!voiceHeld.current) return;
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (!voiceHeld.current) {
        await setAudioModeAsync({ allowsRecording: false });
        return;
      }
      await recorder.prepareToRecordAsync();
      if (!voiceHeld.current) {
        await recorder.stop();
        await setAudioModeAsync({ allowsRecording: false });
        if (recorder.uri) {
          try {
            new File(recorder.uri).delete();
          } catch {
            // The empty temporary recording may already be gone.
          }
        }
        return;
      }
      recorder.record();
      recordingActive.current = true;
      voiceStartedAt.current = Date.now();
    } catch {
      void setAudioModeAsync({ allowsRecording: false });
      setError('Le micro est indisponible. Réessayez.');
    } finally {
      voiceOperationBusy.current = false;
      setVoiceBusy(false);
      if (recordingActive.current && !voiceHeld.current) void stopVoice();
    }
  }

  async function stopVoice() {
    if (voiceOperationBusy.current || !recordingActive.current) return;
    voiceHeld.current = false;
    voiceOperationBusy.current = true;
    setVoiceBusy(true);
    try {
      const duration = Math.max(recorderState.durationMillis, Date.now() - voiceStartedAt.current);
      await recorder.stop();
      recordingActive.current = false;
      await setAudioModeAsync({ allowsRecording: false });
      if (recorder.uri) {
        voiceDraftUri.current = recorder.uri;
        setVoiceDraft({ uri: recorder.uri, duration });
      }
    } catch {
      setError('Impossible de terminer l’enregistrement.');
    } finally {
      voiceOperationBusy.current = false;
      setVoiceBusy(false);
    }
  }

  function discardVoice() {
    if (recordingActive.current) {
      void (async () => {
        voiceHeld.current = false;
        voiceOperationBusy.current = true;
        setVoiceBusy(true);
        try {
          await recorder.stop();
          recordingActive.current = false;
          await setAudioModeAsync({ allowsRecording: false });
          if (recorder.uri) new File(recorder.uri).delete();
        } catch {
          setError('Impossible de supprimer cet enregistrement.');
        } finally {
          voiceOperationBusy.current = false;
          setVoiceBusy(false);
        }
      })();
      return;
    }
    if (voiceDraft) {
      player.pause();
      try {
        new File(voiceDraft.uri).delete();
      } catch {
        /* The temporary file may already be gone. */
      }
    }
    voiceDraftUri.current = null;
    setVoiceDraft(null);
  }

  // Stop rendering cached protected messages as soon as secret access is locked.
  if (secret && (!token || !secretToken)) return null;

  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Pressable
            accessibilityLabel={
              secret
                ? user?.is_superadmin
                  ? 'Retour aux discussions cachées'
                  : 'Retour à l’accueil'
                : 'Retour aux conversations'
            }
            accessibilityRole="button"
            onPress={() => {
              if (!secret) {
                router.back();
              } else if (user?.is_superadmin) {
                router.replace('/secret/conversations');
              } else {
                if (token && secretToken)
                  void secretApi.lock(token, secretToken).catch(() => undefined);
                clearSecretAccess();
                client.removeQueries({ queryKey: ['secret'] });
                router.replace('/home');
              }
            }}
            style={styles.back}
          >
            <Text style={styles.backIcon}>arrow_back</Text>
          </Pressable>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {(recipientName || conversation.data?.name || 'C').charAt(0).toUpperCase()}
            </Text>
          </View>
          <View style={styles.headerTitles}>
            <Text numberOfLines={1} style={styles.title}>
              {conversation.data?.name || 'Conversation privée'}
            </Text>
            {correspondentTyping ? (
              <Text style={styles.typingLabel}>Écrit un message…</Text>
            ) : !secret ? (
              <Text style={styles.headerSubtitle}>Conversation privée</Text>
            ) : null}
          </View>
        </View>
        {messages.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {messages.isError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            Impossible de charger les messages. Vérifiez votre connexion puis réessayez.
          </Text>
        ) : null}
        <ScrollView
          ref={scroll}
          contentContainerStyle={styles.messages}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => {
            if (nearBottom.current) scroll.current?.scrollToEnd({ animated: false });
          }}
          onScroll={(event) => {
            const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
            nearBottom.current =
              contentSize.height - contentOffset.y - layoutMeasurement.height < 100;
          }}
          scrollEventThrottle={100}
        >
          {visibleMessages.length === 0 && !messages.isPending ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyIcon}>chat_bubble_outline</Text>
              <Text style={styles.emptyTitle}>La discussion commence ici</Text>
              <Text style={styles.empty}>Écrivez un premier message à votre proche.</Text>
            </View>
          ) : null}
          {visibleMessages.map((message) => {
            const mine = message.sender_id === user?.id;
            const local = isLocalMessage(message) ? message : null;
            const read = message.read_by_count > 0;
            return (
              <View key={message.id} style={[styles.messageRow, mine && styles.mineRow]}>
                {mine && read && recipientName ? (
                  <View
                    accessible
                    accessibilityLabel={`Message lu par ${recipientName}`}
                    style={styles.recipientAvatar}
                  >
                    <Text style={styles.recipientInitial}>
                      {recipientName.charAt(0).toUpperCase()}
                    </Text>
                  </View>
                ) : null}
                <View style={[styles.message, mine ? styles.mine : styles.theirs]}>
                  <Text style={[styles.messageText, mine && styles.mineText]}>{message.body}</Text>
                  <View style={styles.meta}>
                    <Text style={[styles.metaText, mine && styles.mineMeta]}>
                      {formatTime(message.created_at)}
                    </Text>
                    {mine ? (
                      local?.delivery === 'failed' ? (
                        <Pressable
                          accessibilityLabel="Message non envoyé. Réessayer"
                          accessibilityRole="button"
                          onPress={() => retry(local)}
                          style={styles.failedAction}
                        >
                          <Text style={styles.failedIcon}>error_outline</Text>
                          <Text style={styles.failedText}>Réessayer</Text>
                        </Pressable>
                      ) : local?.delivery === 'pending' ? (
                        <Text style={[styles.metaText, styles.status, styles.mineMeta]}>
                          Envoi…
                        </Text>
                      ) : (
                        <Text
                          accessibilityLabel="Message envoyé"
                          style={[styles.sentCheck, styles.mineMeta]}
                        >
                          check
                        </Text>
                      )
                    ) : null}
                  </View>
                </View>
              </View>
            );
          })}
          {correspondentTyping ? (
            <View
              accessibilityLabel="Votre correspondant écrit un message"
              style={styles.typingBubble}
            >
              <Text style={styles.typingDots}>● ● ●</Text>
            </View>
          ) : null}
        </ScrollView>
        <View
          style={[
            styles.composer,
            { paddingBottom: keyboardVisible ? 12 : Math.max(insets.bottom, 24) },
          ]}
        >
          {error ? (
            <Text accessibilityRole="alert" style={styles.composerError}>
              {error}
            </Text>
          ) : null}
          {recorderState.isRecording || voiceDraft ? (
            <View style={styles.voicePanel}>
              <View style={styles.voiceStatus}>
                <View
                  style={[styles.recordDot, !recorderState.isRecording && styles.recordDotSaved]}
                />
                <Text style={styles.voiceText}>
                  {recorderState.isRecording
                    ? 'Enregistrement en cours · relâchez pour terminer'
                    : 'Vocal prêt à écouter'}
                </Text>
                <Text style={styles.voiceTime}>
                  {formatDuration(
                    recorderState.isRecording
                      ? recorderState.durationMillis
                      : (voiceDraft?.duration ?? 0),
                  )}
                </Text>
              </View>
              <View style={styles.voiceActions}>
                <Pressable
                  accessibilityLabel="Supprimer le vocal"
                  accessibilityRole="button"
                  disabled={voiceBusy}
                  onPress={discardVoice}
                  style={styles.voiceAction}
                >
                  <Text style={styles.voiceActionIcon}>delete_outline</Text>
                </Pressable>
                {recorderState.isRecording ? (
                  <Pressable
                    accessibilityRole="button"
                    disabled={voiceBusy}
                    onPress={() => void stopVoice()}
                    style={styles.voicePrimary}
                  >
                    <Text style={styles.voicePrimaryText}>Terminer</Text>
                  </Pressable>
                ) : voiceDraft ? (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => {
                      player.replace(voiceDraft.uri);
                      player.play();
                    }}
                    style={styles.voiceActionWide}
                  >
                    <Text style={styles.voiceActionIcon}>play_arrow</Text>
                    <Text style={styles.voiceActionText}>Écouter</Text>
                  </Pressable>
                ) : null}
              </View>
              {voiceDraft ? (
                <Text style={styles.voiceHint}>L’envoi de vocaux sera bientôt disponible.</Text>
              ) : null}
            </View>
          ) : null}
          <View style={styles.composerRow}>
            <TextInput
              accessibilityLabel="Votre message"
              autoFocus
              editable={!recorderState.isRecording}
              value={body}
              onChangeText={updateBody}
              multiline={!secret}
              blurOnSubmit={false}
              onSubmitEditing={submit}
              returnKeyType="send"
              style={styles.composerInput}
              placeholder="Écrire un message"
              placeholderTextColor={colors.muted}
              textAlignVertical="center"
            />
            {!body.trim() ? (
              <Pressable
                accessibilityLabel={
                  recorderState.isRecording
                    ? 'Terminer le vocal'
                    : 'Maintenir pour enregistrer un vocal'
                }
                accessibilityHint="Maintenez appuyé, puis relâchez pour terminer l’enregistrement."
                accessibilityRole="button"
                delayLongPress={300}
                disabled={Boolean(voiceDraft)}
                onPressIn={() => {
                  voiceHeld.current = true;
                  setMicPressed(true);
                }}
                onLongPress={() => void startVoice()}
                onPressOut={() => {
                  voiceHeld.current = false;
                  setMicPressed(false);
                  if (recordingActive.current) void stopVoice();
                }}
                style={[
                  styles.mic,
                  (micPressed || recorderState.isRecording) && styles.micRecording,
                  voiceDraft && styles.sendDisabled,
                ]}
              >
                <Text
                  style={[
                    styles.micIcon,
                    (micPressed || recorderState.isRecording) && styles.micRecordingIcon,
                  ]}
                >
                  {recorderState.isRecording ? 'stop' : 'mic'}
                </Text>
              </Pressable>
            ) : (
              <Pressable
                accessibilityLabel="Envoyer le message"
                accessibilityRole="button"
                onPress={submit}
                style={styles.send}
              >
                <Text style={styles.sendIcon}>send</Text>
              </Pressable>
            )}
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
function makeStyles(colors: ColorTokens, mode: 'light' | 'dark') {
  return StyleSheet.create({
    screen: { ...subtleBackground(colors), flex: 1 },
    flex: { flex: 1 },
    header: {
      alignItems: 'center',
      backgroundColor: colors.white,
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      flexDirection: 'row',
      gap: 11,
      minHeight: 66,
      paddingHorizontal: darkTheme.spacing.content,
      paddingVertical: 9,
    },
    back: { alignItems: 'center', justifyContent: 'center', height: 44, width: 32 },
    backIcon: { color: colors.ink, fontFamily: 'MaterialSymbols_400Regular', fontSize: 24 },
    avatar: {
      alignItems: 'center',
      backgroundColor: colors.spruceSoft,
      borderRadius: 18,
      height: 36,
      justifyContent: 'center',
      width: 36,
    },
    avatarText: { color: colors.spruceOn, fontSize: 16, fontWeight: '700' },
    headerTitles: { flex: 1, justifyContent: 'center' },
    title: { color: colors.ink, fontSize: 17, fontWeight: '700' },
    headerSubtitle: { color: colors.muted, fontSize: 12, marginTop: 2 },
    typingLabel: { color: colors.spruce, fontSize: 12, fontWeight: '600', marginTop: 2 },
    loader: { marginTop: 40 },
    error: {
      backgroundColor: colors.berrySoft,
      borderRadius: darkTheme.radius.input,
      color: colors.berry,
      margin: darkTheme.spacing.screen,
      padding: 12,
    },
    messages: {
      flexGrow: 1,
      gap: 9,
      paddingHorizontal: darkTheme.spacing.content,
      paddingTop: 20,
      paddingBottom: 24,
    },
    emptyCard: { alignItems: 'center', alignSelf: 'center', marginTop: 80, maxWidth: 260 },
    emptyIcon: {
      color: colors.spruce,
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 34,
      marginBottom: 12,
    },
    emptyTitle: { color: colors.ink, fontSize: 17, fontWeight: '700', textAlign: 'center' },
    empty: { color: colors.muted, lineHeight: 20, marginTop: 6, textAlign: 'center' },
    messageRow: { alignItems: 'flex-end', flexDirection: 'row', gap: 6 },
    mineRow: { justifyContent: 'flex-end' },
    message: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 18,
      borderWidth: 1,
      maxWidth: '82%',
      paddingHorizontal: 13,
      paddingVertical: 10,
    },
    theirs: { borderBottomLeftRadius: 5 },
    mine: {
      backgroundColor: colors.spruce,
      borderColor: colors.spruce,
      borderBottomRightRadius: 5,
    },
    messageText: { color: colors.ink, fontSize: 16, lineHeight: 22 },
    mineText: { color: mode === 'dark' ? '#111322' : '#FFFFFF' },
    meta: { alignItems: 'center', flexDirection: 'row', justifyContent: 'flex-end', marginTop: 5 },
    metaText: { color: colors.muted, fontSize: 11 },
    mineMeta: { color: mode === 'dark' ? '#111322' : '#FFFFFF' },
    status: { marginLeft: 8 },
    sentCheck: {
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 17,
      lineHeight: 18,
      marginLeft: 7,
    },
    recipientAvatar: {
      alignItems: 'center',
      backgroundColor: colors.spruceSoft,
      borderColor: colors.spruce,
      borderRadius: 12,
      borderWidth: 1,
      height: 24,
      justifyContent: 'center',
      marginBottom: 2,
      width: 24,
    },
    recipientInitial: { color: colors.spruceOn, fontSize: 11, fontWeight: '700' },
    failedAction: { alignItems: 'center', flexDirection: 'row', marginLeft: 8, minHeight: 28 },
    failedIcon: {
      color: mode === 'dark' ? '#111322' : '#FFFFFF',
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 15,
    },
    failedText: {
      color: mode === 'dark' ? '#111322' : '#FFFFFF',
      fontSize: 11,
      fontWeight: '700',
      marginLeft: 3,
      textDecorationLine: 'underline',
    },
    typingBubble: {
      alignSelf: 'flex-start',
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 17,
      borderBottomLeftRadius: 5,
      borderWidth: 1,
      paddingHorizontal: 15,
      paddingVertical: 10,
    },
    typingDots: { color: colors.muted, fontSize: 10, letterSpacing: 2 },
    composer: {
      backgroundColor: 'transparent',
      paddingHorizontal: darkTheme.spacing.content,
      paddingTop: 6,
    },
    composerError: { color: colors.berry, fontSize: 13, marginBottom: 7 },
    composerRow: {
      alignItems: 'flex-end',
      backgroundColor: 'transparent',
      flexDirection: 'row',
      gap: 8,
    },
    voicePanel: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginBottom: 9,
      padding: 12,
    },
    voiceStatus: { alignItems: 'center', flexDirection: 'row', gap: 8 },
    recordDot: { backgroundColor: colors.berry, borderRadius: 5, height: 9, width: 9 },
    recordDotSaved: { backgroundColor: colors.spruce },
    voiceText: { color: colors.ink, flex: 1, fontSize: 13, fontWeight: '600' },
    voiceTime: { color: colors.muted, fontSize: 12, fontVariant: ['tabular-nums'] },
    voiceActions: {
      alignItems: 'center',
      flexDirection: 'row',
      gap: 9,
      justifyContent: 'flex-end',
      marginTop: 10,
    },
    voiceAction: {
      alignItems: 'center',
      borderColor: colors.border,
      borderRadius: 12,
      borderWidth: 1,
      height: 40,
      justifyContent: 'center',
      width: 44,
    },
    voiceActionWide: {
      alignItems: 'center',
      borderColor: colors.border,
      borderRadius: 12,
      borderWidth: 1,
      flexDirection: 'row',
      gap: 5,
      height: 40,
      justifyContent: 'center',
      paddingHorizontal: 12,
    },
    voiceActionIcon: { color: colors.ink, fontFamily: 'MaterialSymbols_400Regular', fontSize: 20 },
    voiceActionText: { color: colors.ink, fontSize: 13, fontWeight: '600' },
    voicePrimary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 12,
      height: 40,
      justifyContent: 'center',
      paddingHorizontal: 17,
    },
    voicePrimaryText: {
      color: mode === 'dark' ? colors.linen : '#FFFFFF',
      fontSize: 13,
      fontWeight: '700',
    },
    voiceHint: { color: colors.muted, fontSize: 11, marginTop: 9 },
    composerInput: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 22,
      borderWidth: 1,
      color: colors.ink,
      elevation: 3,
      flex: 1,
      fontSize: 15,
      maxHeight: 110,
      minHeight: 44,
      paddingHorizontal: 15,
      paddingVertical: 8,
      shadowColor: '#000000',
      shadowOffset: { height: 2, width: 0 },
      shadowOpacity: 0.12,
      shadowRadius: 5,
    },
    send: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 22,
      elevation: 3,
      height: 44,
      justifyContent: 'center',
      shadowColor: '#000000',
      shadowOffset: { height: 2, width: 0 },
      shadowOpacity: 0.16,
      shadowRadius: 5,
      width: 44,
    },
    sendDisabled: { opacity: 0.45 },
    mic: {
      alignItems: 'center',
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 22,
      borderWidth: 1,
      height: 44,
      justifyContent: 'center',
      width: 44,
    },
    micRecording: { backgroundColor: colors.berrySoft, borderColor: colors.berry },
    micIcon: { color: colors.spruce, fontFamily: 'MaterialSymbols_400Regular', fontSize: 22 },
    micRecordingIcon: { color: colors.berry },
    sendIcon: {
      color: mode === 'dark' ? colors.linen : '#FFFFFF',
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 23,
      lineHeight: 25,
    },
  });
}
