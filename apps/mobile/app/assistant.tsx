import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import Markdown, { MarkdownIt, type RenderRules } from 'react-native-markdown-display';
import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
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

import {
  assistantApi,
  type AssistantHistory,
  type AssistantMessage,
  type AssistantProposal,
} from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme } from '@/src/theme';
import { makeMarkdownStyles, makeStyles } from '@/features/assistant/assistant-styles';
import { AssistantOrb } from '@/features/assistant/assistant-orb';
import { homeReplyKey, type HomeReply } from '@/features/assistant/home-reply';
import { VoiceCapture } from '@/features/assistant/voice-capture';

const assistantMarkdown = MarkdownIt({ typographer: true }).disable(['image']);
const assistantMarkdownRules: RenderRules = {
  code_block: (node, _children, _parent, styles, inheritedStyles = {}) => (
    <ScrollView
      key={node.key}
      contentContainerStyle={styles.codeScrollContent}
      horizontal
      showsHorizontalScrollIndicator
      style={styles.codeScroll}
    >
      <Text style={[inheritedStyles, styles.code_block]}>{node.content.trimEnd()}</Text>
    </ScrollView>
  ),
  fence: (node, _children, _parent, styles, inheritedStyles = {}) => (
    <ScrollView
      key={node.key}
      contentContainerStyle={styles.codeScrollContent}
      horizontal
      showsHorizontalScrollIndicator
      style={styles.codeScroll}
    >
      <Text style={[inheritedStyles, styles.fence]}>{node.content.trimEnd()}</Text>
    </ScrollView>
  ),
};

type LocalTurn = {
  key: string;
  text: string;
  delivery: 'pending' | 'failed' | 'sent';
  error?: string;
  reply?: AssistantMessage;
  model?: string;
};

type SendPayload = { message: string; key: string; retry: boolean; model?: string };

export default function AssistantScreen() {
  const userId = useSessionStore((state) => state.user?.id);
  const [routeOwner, setRouteOwner] = useState<string | null>(userId ?? null);
  // A deep link may mount before session restoration; bind its initial draft to
  // the first authenticated account so it cannot be replayed after a switch.
  if (userId && routeOwner === null) setRouteOwner(userId);
  if (!userId || routeOwner === null) return null;
  return <AccountAssistantScreen key={userId} initialAllowed={routeOwner === userId} />;
}

function AccountAssistantScreen({ initialAllowed }: { initialAllowed: boolean }) {
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const assistantName = useSessionStore((state) => state.user?.assistant_name ?? 'Cocoon');
  const assistantEnabled = useSessionStore((state) => state.user?.enable_assistant === true);
  const refreshUser = useSessionStore((state) => state.refreshUser);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors, mode);
  const markdownStyles = makeMarkdownStyles(colors);
  const client = useQueryClient();
  const insets = useSafeAreaInsets();
  const scroll = useRef<ScrollView>(null);
  const input = useRef<TextInput>(null);
  const initialSubmitted = useRef(false);
  const streamAbort = useRef<AbortController | null>(null);
  const params = useLocalSearchParams<{ initial?: string; completed?: string }>();
  const completed =
    typeof params.completed === 'string'
      ? client.getQueryData<HomeReply>(homeReplyKey(userId, params.completed))
      : undefined;
  const [text, setText] = useState(() =>
    initialAllowed && typeof params.initial === 'string' ? params.initial : '',
  );
  const [streamingText, setStreamingText] = useState('');
  const [selectedModel, setSelectedModel] = useState<string | null>(completed?.model ?? null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [localTurns, setLocalTurns] = useState<LocalTurn[]>(() =>
    completed
      ? [
          {
            key: completed.key,
            text: completed.text,
            delivery: 'sent',
            reply: completed.result.message,
            model: completed.model,
          },
        ]
      : [],
  );
  const [choices, setChoices] = useState<string[]>(completed?.result.choices ?? []);
  const [memoryProposals, setMemoryProposals] = useState<AssistantProposal[]>(
    () => completed?.result.message.proposals.filter((proposal) => proposal.kind === 'note') ?? [],
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  useEffect(() => () => streamAbort.current?.abort(), []);
  useEffect(() => {
    if (typeof params.completed === 'string') {
      client.removeQueries({ queryKey: homeReplyKey(userId, params.completed), exact: true });
    }
  }, [client, params.completed, userId]);
  useFocusEffect(
    useCallback(() => {
      void refreshUser().catch(() => undefined);
    }, [refreshUser]),
  );
  const history = useQuery({
    queryKey: ['assistant', 'history', userId],
    enabled: Boolean(token && userId),
    queryFn: () => assistantApi.history(token!),
    retry: false,
  });
  const freeModels = useQuery({
    queryKey: ['assistant', 'free-models', userId],
    enabled: Boolean(token && userId && assistantEnabled),
    queryFn: () => assistantApi.freeModels(token!),
    staleTime: 300_000,
    retry: false,
  });
  const chosenModel = freeModels.data?.available
    ? freeModels.data.models.find(
        (item) => item.id === (selectedModel ?? freeModels.data?.default_model),
      )
    : undefined;
  const selectedModelUnavailable = Boolean(
    selectedModel && freeModels.data?.available && !chosenModel,
  );
  const send = useMutation({
    mutationFn: ({ message, key, retry, model }: SendPayload) =>
      (() => {
        streamAbort.current = new AbortController();
        return assistantApi.streamChat(
          token!,
          message,
          {
            onDelta: (delta) => {
              if (useSessionStore.getState().user?.id === userId)
                setStreamingText((current) => current + delta);
            },
          },
          streamAbort.current.signal,
          key,
          retry,
          model,
        );
      })(),
    onSuccess: (result, { key }) => {
      if (useSessionStore.getState().user?.id !== userId) return;
      streamAbort.current = null;
      setStreamingText('');
      setLocalTurns((current) =>
        current.map((turn) =>
          turn.key === key ? { ...turn, delivery: 'sent', reply: result.message } : turn,
        ),
      );
      setChoices(result.choices);
      setMemoryProposals(result.message.proposals.filter((proposal) => proposal.kind === 'note'));
      setNotice(null);
      const historyKey = ['assistant', 'history', userId];
      void client.invalidateQueries({ queryKey: historyKey }).then(() => {
        if (useSessionStore.getState().user?.id !== userId) return;
        const savedMessages = client.getQueryData<AssistantHistory>(historyKey)?.messages ?? [];
        const savedKeys = new Set(
          savedMessages.map((message) => message.idempotency_key).filter(Boolean),
        );
        const savedIds = new Set(savedMessages.map((message) => message.id));
        setLocalTurns((current) =>
          current.filter(
            (turn) =>
              turn.delivery !== 'sent' ||
              !savedKeys.has(turn.key) ||
              !turn.reply ||
              !savedIds.has(turn.reply.id),
          ),
        );
      });
    },
    onError: (error, { key }) => {
      if (useSessionStore.getState().user?.id !== userId) return;
      streamAbort.current = null;
      setStreamingText('');
      const detail =
        error instanceof Error && error.name === 'AbortError'
          ? 'Génération arrêtée.'
          : error instanceof Error
            ? error.message
            : 'Le modèle est indisponible.';
      setLocalTurns((current) =>
        current.map((turn) =>
          turn.key === key ? { ...turn, delivery: 'failed', error: detail } : turn,
        ),
      );
    },
  });
  const cancelStreaming = () => {
    streamAbort.current?.abort();
  };
  const confirmMemory = useMutation({
    mutationFn: (proposal: AssistantProposal) =>
      assistantApi.confirmProposal(token!, proposal.id, proposal.payload_version),
    onSuccess: (_result, proposal) => {
      if (useSessionStore.getState().user?.id !== userId) return;
      setMemoryProposals((current) => current.filter((item) => item.id !== proposal.id));
      void client.invalidateQueries({ queryKey: ['assistant', 'history', userId] });
    },
  });
  const cancelMemory = useMutation({
    mutationFn: (proposalId: string) => assistantApi.cancelProposal(token!, proposalId),
    onSuccess: (_result, proposalId) => {
      if (useSessionStore.getState().user?.id !== userId) return;
      setMemoryProposals((current) => current.filter((proposal) => proposal.id !== proposalId));
      void client.invalidateQueries({ queryKey: ['assistant', 'history', userId] });
    },
  });
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
    requestAnimationFrame(() =>
      scroll.current?.scrollToEnd({ animated: Boolean(history.data?.messages.length) }),
    );
  }, [
    history.data?.messages.length,
    localTurns.length,
    choices.length,
    memoryProposals.length,
    send.isPending,
  ]);
  const submit = useCallback(
    (message?: string, retryKey?: string) => {
      if (!token || !userId || !assistantEnabled || send.isPending) return;
      const value = (message ?? text).trim();
      if (!value) {
        setNotice('Écrivez un message avant de l’envoyer.');
        return;
      }
      const key = retryKey ?? `mobile-chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const previousModel = retryKey
        ? localTurns.find((turn) => turn.key === retryKey)?.model
        : undefined;
      const model = previousModel ?? selectedModel ?? chosenModel?.id;
      setLocalTurns((current) =>
        retryKey
          ? current.map((turn) =>
              turn.key === key ? { ...turn, delivery: 'pending', error: undefined } : turn,
            )
          : [...current, { key, text: value, delivery: 'pending', model }],
      );
      if (!retryKey) {
        setText('');
        setChoices([]);
      }
      setStreamingText('');
      setNotice(null);
      send.mutate({ message: value, key, retry: Boolean(retryKey), model });
    },
    [
      assistantEnabled,
      chosenModel?.id,
      localTurns,
      selectedModel,
      send,
      setChoices,
      setLocalTurns,
      setNotice,
      setStreamingText,
      setText,
      text,
      token,
      userId,
    ],
  );
  useEffect(() => {
    if (
      !token ||
      !initialAllowed ||
      !assistantEnabled ||
      initialSubmitted.current ||
      typeof params.initial !== 'string' ||
      !params.initial.trim()
    ) {
      return;
    }
    initialSubmitted.current = true;
    requestAnimationFrame(() => submit(params.initial));
  }, [assistantEnabled, initialAllowed, params.initial, submit, token]);
  const choose = (choice: string) => {
    submit(choice);
  };
  const savedKeys = new Set(
    history.data?.messages.map((message) => message.idempotency_key).filter(Boolean),
  );
  const savedIds = new Set(history.data?.messages.map((message) => message.id));
  const unsavedTurns = localTurns.filter((turn) => !savedKeys.has(turn.key));
  const renderUserMessage = (content: string, key: string, local?: LocalTurn) => (
    <View key={key} style={styles.userRow}>
      <View style={[styles.message, styles.userMessage]}>
        <Text style={[styles.messageText, styles.userMessageText]}>{content}</Text>
      </View>
      {local?.delivery === 'failed' ? (
        <View style={styles.failedRow}>
          <Text accessibilityRole="alert" style={styles.failedText}>
            {local.error}
          </Text>
          <Pressable
            auditAction="assistant.message.retry"
            accessibilityRole="button"
            accessibilityLabel={`Réessayer l’envoi de : ${content}`}
            disabled={send.isPending || !assistantEnabled}
            onPress={() => submit(local.text, local.key)}
            style={[styles.retry, send.isPending && styles.retryDisabled]}
          >
            <Text style={styles.retryIcon}>refresh</Text>
            <Text style={styles.retryText}>Réessayer</Text>
          </Pressable>
        </View>
      ) : local?.delivery === 'pending' ? (
        <Text style={styles.pendingText}>Envoi…</Text>
      ) : null}
    </View>
  );
  const renderAssistantMessage = (message: AssistantMessage) => (
    <View key={message.id} style={[styles.message, styles.agentMessage]}>
      <Markdown
        markdownit={assistantMarkdown}
        rules={assistantMarkdownRules}
        style={markdownStyles}
      >
        {message.content}
      </Markdown>
    </View>
  );
  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Pressable
            auditAction="assistant.back"
            accessibilityLabel="Retour à l’accueil"
            accessibilityRole="button"
            onPress={() => router.back()}
            style={styles.back}
          >
            <Text style={styles.backIcon}>arrow_back</Text>
          </Pressable>
          <AssistantOrb size={52} active={send.isPending} enabled={assistantEnabled} />
          <Text numberOfLines={1} style={styles.title}>
            {assistantName}
          </Text>
        </View>
        {freeModels.data?.available ? (
          <View style={styles.modelBar}>
            <Text style={styles.modelLabel}>Modèle gratuit</Text>
            <Pressable
              auditAction="assistant.model.open"
              accessibilityLabel={`Modèle gratuit : ${selectedModelUnavailable ? 'choix indisponible' : (chosenModel?.name ?? 'Choisir')}`}
              accessibilityRole="button"
              accessibilityState={{ expanded: modelMenuOpen, disabled: send.isPending }}
              disabled={send.isPending}
              onPress={() => {
                Keyboard.dismiss();
                setModelMenuOpen((open) => !open);
              }}
              style={styles.modelButton}
            >
              <Text numberOfLines={1} style={styles.modelButtonText}>
                {selectedModelUnavailable ? 'Choix indisponible' : (chosenModel?.name ?? 'Choisir')}
              </Text>
              <Text style={styles.modelArrow}>{modelMenuOpen ? 'expand_less' : 'expand_more'}</Text>
            </Pressable>
            {modelMenuOpen ? (
              <ScrollView nestedScrollEnabled style={styles.modelMenu}>
                {freeModels.data.models.map((item) => (
                  <Pressable
                    auditAction="assistant.model.select"
                    key={item.id}
                    accessibilityLabel={`Utiliser ${item.name}`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: item.id === chosenModel?.id }}
                    onPress={() => {
                      setSelectedModel(item.id);
                      setModelMenuOpen(false);
                    }}
                    style={[
                      styles.modelOption,
                      item.id === chosenModel?.id && styles.modelOptionActive,
                    ]}
                  >
                    <Text numberOfLines={2} style={styles.modelOptionText}>
                      {item.name}
                    </Text>
                  </Pressable>
                ))}
              </ScrollView>
            ) : null}
          </View>
        ) : null}
        {selectedModelUnavailable ? (
          <Text accessibilityRole="alert" style={styles.modelErrorText}>
            Ce modèle n’est plus dans la liste. Choisissez-en un autre ; son envoi sera vérifié par
            le serveur.
          </Text>
        ) : null}
        {assistantEnabled && freeModels.isError ? (
          <Pressable
            auditAction="assistant.model.retry"
            accessibilityLabel="Réessayer le chargement des modèles gratuits"
            accessibilityRole="button"
            onPress={() => void freeModels.refetch()}
            style={styles.modelError}
          >
            <Text accessibilityRole="alert" style={styles.modelErrorText}>
              Choix de modèles indisponible. Réessayer
            </Text>
          </Pressable>
        ) : null}
        <ScrollView
          ref={scroll}
          contentContainerStyle={styles.content}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}
        >
          <View style={styles.messages}>
            {history.isPending ? (
              <ActivityIndicator color={colors.spruce} style={styles.loader} />
            ) : null}
            {history.isError ? (
              <Text accessibilityRole="alert" style={styles.historyError}>
                Impossible de charger la conversation. Vérifiez votre connexion puis réessayez.
              </Text>
            ) : null}
            {!history.isPending &&
            !history.isError &&
            history.data?.messages.length === 0 &&
            localTurns.length === 0 ? (
              <Text style={styles.empty}>La discussion commence ici.</Text>
            ) : null}
            {history.data?.messages.map((message) => {
              if (message.role === 'assistant') return renderAssistantMessage(message);
              const local = localTurns.find((turn) => turn.key === message.idempotency_key);
              return (
                <Fragment key={message.id}>
                  {renderUserMessage(message.content, message.id, local)}
                  {local?.reply && !savedIds.has(local.reply.id)
                    ? renderAssistantMessage(local.reply)
                    : null}
                </Fragment>
              );
            })}
            {unsavedTurns.map((turn) => (
              <Fragment key={turn.key}>
                {renderUserMessage(turn.text, turn.key, turn)}
                {turn.reply && !savedIds.has(turn.reply.id)
                  ? renderAssistantMessage(turn.reply)
                  : null}
              </Fragment>
            ))}
            {send.isPending ? (
              <View
                accessibilityLabel={streamingText ? undefined : 'Votre assistant écrit une réponse'}
                accessibilityLiveRegion="polite"
                style={[styles.message, styles.agentMessage]}
              >
                {streamingText ? (
                  <Text style={styles.messageText}>{streamingText}</Text>
                ) : (
                  <Text style={styles.typingDots}>● ● ●</Text>
                )}
              </View>
            ) : null}
          </View>
          {memoryProposals.length ? (
            <View style={styles.memoryCard}>
              <Text style={styles.memoryLabel}>Souvenir proposé</Text>
              {memoryProposals.map((proposal) => (
                <View key={proposal.id} style={styles.proposalBlock}>
                  <Text style={styles.memoryText}>{String(proposal.payload.summary ?? '')}</Text>
                  <View style={styles.proposalActions}>
                    <Pressable
                      auditAction="assistant.memory.keep"
                      accessibilityRole="button"
                      accessibilityLabel="Conserver ce souvenir"
                      disabled={confirmMemory.isPending || cancelMemory.isPending}
                      onPress={() => confirmMemory.mutate(proposal)}
                      style={styles.confirmMemory}
                    >
                      <Text style={styles.confirmMemoryText}>Conserver</Text>
                    </Pressable>
                    <Pressable
                      auditAction="assistant.memory.skip"
                      accessibilityRole="button"
                      accessibilityLabel="Ne pas conserver ce souvenir"
                      disabled={confirmMemory.isPending || cancelMemory.isPending}
                      onPress={() => cancelMemory.mutate(proposal.id)}
                      style={styles.cancelMemory}
                    >
                      <Text style={styles.cancelMemoryText}>Ne pas conserver</Text>
                    </Pressable>
                  </View>
                </View>
              ))}
            </View>
          ) : null}
          {choices.length ? (
            <View style={styles.choiceCard}>
              <Text style={styles.choiceLabel}>Vous pouvez répondre</Text>
              {choices.map((choice) => (
                <Pressable
                  auditAction="assistant.suggestion.choose"
                  key={choice}
                  accessibilityRole="button"
                  accessibilityLabel={`Envoyer la réponse : ${choice}`}
                  disabled={send.isPending || !assistantEnabled}
                  onPress={() => choose(choice)}
                  style={styles.choice}
                >
                  <Text style={styles.choiceText}>{choice}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
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
          {assistantEnabled && freeModels.isPending ? (
            <Text accessibilityLiveRegion="polite" style={styles.modelLoading}>
              Chargement des modèles…
            </Text>
          ) : null}
          <View style={styles.composerRow}>
            <TextInput
              ref={input}
              accessibilityLabel="Votre message"
              autoFocus={assistantEnabled && Boolean(params.initial?.trim())}
              editable={assistantEnabled}
              blurOnSubmit={false}
              multiline={false}
              onChangeText={(value) => {
                setText(value);
                setNotice(null);
              }}
              onFocus={() =>
                requestAnimationFrame(() => scroll.current?.scrollToEnd({ animated: true }))
              }
              onSubmitEditing={() => submit()}
              placeholder="Écrire un message"
              placeholderTextColor={colors.muted}
              returnKeyType="send"
              style={styles.composerInput}
              textAlignVertical="center"
              value={text}
            />
            <VoiceCapture
              accessToken={token}
              colors={colors}
              variant="chat"
              disabled={!assistantEnabled}
              sending={send.isPending}
              hasText={!!text.trim()}
              onSend={() => submit()}
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
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
