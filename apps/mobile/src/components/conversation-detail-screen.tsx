import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
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
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { makeStyles } from '@/src/components/conversation-detail-styles';
import {
  ApiError,
  conversationsApi,
  realtimeSocketUrl,
  secretApi,
  type Message,
} from '@/src/services/api';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme } from '@/src/theme';
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
    staleTime: 15_000,
  });
  const messages = useQuery({
    queryKey: messagesKey,
    enabled: Boolean(token && id && (!secret || secretToken)),
    queryFn: () =>
      secret
        ? secretApi.listMessages(token!, secretToken!, id)
        : conversationsApi.listMessages(token!, id),
    refetchInterval: 4000,
    staleTime: 3000,
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
      if (
        useSessionStore.getState().user?.id !== userId ||
        (secret && useSecretAccessStore.getState().token !== secretToken)
      ) {
        return;
      }
      client.setQueryData<Message[]>(messagesKey, (items) => {
        const previous = items ?? [];
        return previous.some((message) => message.id === saved.id)
          ? previous.map((message) => (message.id === saved.id ? saved : message))
          : [...previous, saved];
      });
      setLocalMessages((items) => items.filter((item) => item.localId !== localId));
      setError(null);
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
            auditAction={secret ? 'protected.press' : 'conversation.back'}
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
                          auditAction={secret ? 'protected.press' : 'conversation.message.retry'}
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
                  auditAction={secret ? 'protected.press' : 'conversation.voice.discard'}
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
                    auditAction={secret ? 'protected.press' : 'conversation.voice.finish'}
                    accessibilityRole="button"
                    disabled={voiceBusy}
                    onPress={() => void stopVoice()}
                    style={styles.voicePrimary}
                  >
                    <Text style={styles.voicePrimaryText}>Terminer</Text>
                  </Pressable>
                ) : voiceDraft ? (
                  <Pressable
                    auditAction={secret ? 'protected.press' : 'conversation.voice.play'}
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
                auditAction={secret ? 'protected.press' : 'conversation.voice.record'}
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
                auditAction={secret ? 'protected.press' : 'conversation.message.send'}
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
