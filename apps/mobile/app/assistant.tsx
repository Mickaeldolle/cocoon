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
  StyleSheet,
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
import { darkTheme, lightTheme, subtleBackground, type ColorTokens } from '@/src/theme';
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
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
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
    typeof params.initial === 'string' ? params.initial : '',
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
    enabled: Boolean(token),
    queryFn: () => assistantApi.history(token!),
    retry: false,
  });
  const freeModels = useQuery({
    queryKey: ['assistant', 'free-models', userId],
    enabled: Boolean(token && assistantEnabled),
    queryFn: () => assistantApi.freeModels(token!),
    staleTime: 300_000,
    retry: false,
  });
  const chosenModel = freeModels.data?.available
    ? (freeModels.data.models.find((item) => item.id === selectedModel) ??
      freeModels.data.models.find((item) => item.id === freeModels.data.default_model))
    : undefined;
  const modelsReady = freeModels.data?.available === false || Boolean(chosenModel);
  const send = useMutation({
    mutationFn: ({ message, key, retry, model }: SendPayload) =>
      (() => {
        streamAbort.current = new AbortController();
        return assistantApi.streamChat(
          token!,
          message,
          { onDelta: (delta) => setStreamingText((current) => current + delta) },
          streamAbort.current.signal,
          key,
          retry,
          model,
        );
      })(),
    onSuccess: (result, { key }) => {
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
      setMemoryProposals((current) => current.filter((item) => item.id !== proposal.id));
      void client.invalidateQueries({ queryKey: ['assistant', 'history', userId] });
    },
  });
  const cancelMemory = useMutation({
    mutationFn: (proposalId: string) => assistantApi.cancelProposal(token!, proposalId),
    onSuccess: (_result, proposalId) => {
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
      if (!token || !assistantEnabled || send.isPending || !modelsReady) return;
      const value = (message ?? text).trim();
      if (!value) {
        setNotice('Écrivez un message avant de l’envoyer.');
        return;
      }
      const key = retryKey ?? `mobile-chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const previousModel = retryKey
        ? localTurns.find((turn) => turn.key === retryKey)?.model
        : undefined;
      const model =
        previousModel && freeModels.data?.models.some((item) => item.id === previousModel)
          ? previousModel
          : chosenModel?.id;
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
      freeModels.data?.models,
      localTurns,
      modelsReady,
      send,
      setChoices,
      setLocalTurns,
      setNotice,
      setStreamingText,
      setText,
      text,
      token,
    ],
  );
  useEffect(() => {
    if (
      !token ||
      !assistantEnabled ||
      !modelsReady ||
      initialSubmitted.current ||
      typeof params.initial !== 'string' ||
      !params.initial.trim()
    ) {
      return;
    }
    initialSubmitted.current = true;
    requestAnimationFrame(() => submit(params.initial));
  }, [assistantEnabled, modelsReady, params.initial, submit, token]);
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
            disabled={send.isPending || !assistantEnabled || !modelsReady}
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
            Votre assistant
          </Text>
        </View>
        {freeModels.data?.available ? (
          <View style={styles.modelBar}>
            <Text style={styles.modelLabel}>Modèle gratuit</Text>
            <Pressable
              auditAction="assistant.model.open"
              accessibilityLabel={`Modèle gratuit : ${chosenModel?.name ?? 'Choisir'}`}
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
                {chosenModel?.name ?? 'Choisir'}
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
        {assistantEnabled && freeModels.isError ? (
          <Pressable
            auditAction="assistant.model.retry"
            accessibilityLabel="Réessayer le chargement des modèles gratuits"
            accessibilityRole="button"
            onPress={() => void freeModels.refetch()}
            style={styles.modelError}
          >
            <Text accessibilityRole="alert" style={styles.modelErrorText}>
              Modèles indisponibles. Réessayer
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
                  disabled={send.isPending || !assistantEnabled || !modelsReady}
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
              editable={assistantEnabled && modelsReady}
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
              disabled={!assistantEnabled || !modelsReady}
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
    content: {
      flexGrow: 1,
      padding: darkTheme.spacing.content,
      paddingBottom: 18,
    },
    back: { alignItems: 'center', justifyContent: 'center', height: 44, width: 32 },
    backIcon: { color: colors.ink, fontFamily: 'MaterialSymbols_400Regular', fontSize: 24 },
    title: {
      color: colors.ink,
      flex: 1,
      fontSize: 17,
      fontWeight: '700',
    },
    modelBar: {
      alignItems: 'center',
      backgroundColor: colors.white,
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      flexDirection: 'row',
      gap: 10,
      minHeight: 54,
      paddingHorizontal: darkTheme.spacing.content,
      zIndex: 5,
    },
    modelLabel: { color: colors.muted, fontSize: 12, fontWeight: '700' },
    modelButton: {
      alignItems: 'center',
      borderColor: colors.border,
      borderRadius: 10,
      borderWidth: 1,
      flex: 1,
      flexDirection: 'row',
      gap: 6,
      justifyContent: 'space-between',
      minHeight: 38,
      paddingHorizontal: 10,
    },
    modelButtonText: { color: colors.ink, flex: 1, fontSize: 13, fontWeight: '700' },
    modelArrow: { color: colors.spruce, fontFamily: 'MaterialSymbols_400Regular', fontSize: 20 },
    modelMenu: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 12,
      borderWidth: 1,
      elevation: 8,
      left: darkTheme.spacing.content,
      maxHeight: 240,
      position: 'absolute',
      right: darkTheme.spacing.content,
      shadowColor: '#000000',
      shadowOffset: { height: 3, width: 0 },
      shadowOpacity: 0.16,
      shadowRadius: 8,
      top: 50,
    },
    modelOption: {
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      justifyContent: 'center',
      minHeight: 44,
      paddingHorizontal: 12,
      paddingVertical: 7,
    },
    modelOptionActive: { backgroundColor: colors.spruceSoft },
    modelOptionText: { color: colors.ink, fontSize: 13, lineHeight: 18 },
    modelError: { backgroundColor: colors.berrySoft, paddingHorizontal: 16, paddingVertical: 9 },
    modelErrorText: { color: colors.berry, fontSize: 13, fontWeight: '700' },
    modelLoading: { color: colors.muted, fontSize: 12, marginBottom: 6 },
    messages: { gap: 9, paddingTop: 4 },
    loader: { marginVertical: 28 },
    historyError: {
      backgroundColor: colors.berrySoft,
      borderRadius: darkTheme.radius.input,
      color: colors.berry,
      lineHeight: 20,
      marginVertical: 12,
      padding: 12,
    },
    empty: { color: colors.muted, lineHeight: 21, paddingVertical: 24, textAlign: 'center' },
    message: {
      borderRadius: 18,
      maxWidth: '88%',
      paddingHorizontal: 13,
      paddingVertical: 10,
    },
    userRow: { alignItems: 'flex-end' },
    userMessage: {
      backgroundColor: colors.spruce,
      borderBottomRightRadius: 5,
      maxWidth: '100%',
    },
    agentMessage: {
      alignSelf: 'flex-start',
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderWidth: 1,
      borderBottomLeftRadius: 5,
      minWidth: 0,
      overflow: 'hidden',
    },
    messageText: { color: colors.ink, fontSize: 16, lineHeight: 22 },
    userMessageText: { color: mode === 'dark' ? '#111322' : '#FFFFFF' },
    typingDots: { color: colors.muted, fontSize: 12, letterSpacing: 2 },
    failedRow: { alignItems: 'flex-end', maxWidth: '88%', paddingTop: 4 },
    failedText: { color: colors.berry, fontSize: 12, lineHeight: 17, textAlign: 'right' },
    retry: { alignItems: 'center', flexDirection: 'row', gap: 3, minHeight: 30 },
    retryDisabled: { opacity: 0.5 },
    retryIcon: { color: colors.berry, fontFamily: 'MaterialSymbols_400Regular', fontSize: 17 },
    retryText: { color: colors.berry, fontSize: 12, fontWeight: '700' },
    pendingText: { color: colors.muted, fontSize: 11, paddingTop: 4 },
    memoryCard: {
      backgroundColor: colors.spruceSoft,
      borderRadius: 16,
      marginTop: 14,
      padding: 14,
    },
    memoryLabel: { color: colors.clay, fontSize: 12, fontWeight: '800', letterSpacing: 0.5 },
    memoryText: { color: colors.ink, lineHeight: 20, marginTop: 5 },
    proposalBlock: { marginTop: 4 },
    proposalActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
    confirmMemory: {
      backgroundColor: colors.spruce,
      borderRadius: 10,
      minHeight: 40,
      justifyContent: 'center',
      paddingHorizontal: 12,
    },
    confirmMemoryText: { color: colors.white, fontWeight: '800' },
    cancelMemory: {
      borderColor: colors.border,
      borderRadius: 10,
      borderWidth: 1,
      minHeight: 40,
      justifyContent: 'center',
      paddingHorizontal: 12,
    },
    cancelMemoryText: { color: colors.muted, fontWeight: '700' },
    choiceCard: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 14,
      padding: 14,
    },
    choiceLabel: { color: colors.muted, fontSize: 13, fontWeight: '800', marginBottom: 8 },
    choice: {
      borderColor: colors.spruce,
      borderRadius: 12,
      borderWidth: 1,
      justifyContent: 'center',
      marginTop: 8,
      minHeight: 44,
      paddingHorizontal: 12,
    },
    choiceText: { color: colors.spruce, fontWeight: '800', lineHeight: 19 },
    composer: {
      backgroundColor: 'transparent',
      paddingHorizontal: darkTheme.spacing.content,
      paddingTop: 6,
    },
    composerRow: { alignItems: 'flex-end', flexDirection: 'row', gap: 8 },
    composerInput: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 22,
      borderWidth: 1,
      color: colors.ink,
      elevation: 3,
      flex: 1,
      fontSize: 15,
      height: 44,
      paddingHorizontal: 15,
      paddingVertical: 8,
      shadowColor: '#000000',
      shadowOffset: { height: 2, width: 0 },
      shadowOpacity: 0.12,
      shadowRadius: 5,
    },
    notice: { color: colors.berry, fontSize: 13, lineHeight: 19, marginBottom: 7 },
    accessNotice: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 8 },
  });
}

function makeMarkdownStyles(colors: ColorTokens) {
  return {
    body: { color: colors.ink, flexShrink: 1, fontSize: 16, lineHeight: 22 },
    paragraph: { color: colors.ink, marginBottom: 10, marginTop: 0 },
    heading1: {
      color: colors.ink,
      fontSize: 24,
      fontWeight: '800' as const,
      lineHeight: 30,
      marginBottom: 8,
      marginTop: 4,
    },
    heading2: {
      color: colors.ink,
      fontSize: 20,
      fontWeight: '800' as const,
      lineHeight: 26,
      marginBottom: 7,
      marginTop: 4,
    },
    heading3: {
      color: colors.ink,
      fontSize: 18,
      fontWeight: '800' as const,
      lineHeight: 24,
      marginBottom: 6,
      marginTop: 4,
    },
    strong: { color: colors.ink, fontWeight: '800' as const },
    em: { color: colors.ink },
    bullet_list: { marginBottom: 8 },
    ordered_list: { marginBottom: 8 },
    list_item: { marginBottom: 4 },
    blockquote: {
      backgroundColor: colors.spruceSoft,
      borderLeftColor: colors.spruce,
      borderLeftWidth: 3,
      color: colors.ink,
      marginVertical: 8,
      paddingHorizontal: 12,
      paddingVertical: 8,
    },
    code_inline: {
      backgroundColor: colors.linen,
      borderColor: colors.border,
      borderRadius: 4,
      color: colors.clayInk,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      paddingHorizontal: 4,
    },
    codeScroll: {
      backgroundColor: colors.linen,
      borderColor: colors.border,
      borderRadius: 10,
      borderWidth: 1,
      marginBottom: 10,
      maxWidth: '100%' as const,
    },
    codeScrollContent: { padding: 12 },
    code_block: {
      color: colors.ink,
      flexShrink: 1,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      lineHeight: 19,
    },
    fence: {
      color: colors.ink,
      flexShrink: 1,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      lineHeight: 19,
    },
    link: { color: colors.spruce, textDecorationLine: 'underline' as const },
    hr: { backgroundColor: colors.border, marginVertical: 12 },
    table: { borderColor: colors.border, maxWidth: '100%' as const },
    th: { backgroundColor: colors.spruceSoft, color: colors.ink, fontWeight: '800' as const },
    td: { borderColor: colors.border, color: colors.ink },
  };
}
