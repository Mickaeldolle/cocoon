import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import Markdown, { MarkdownIt, type RenderRules } from 'react-native-markdown-display';
import { useCallback, useEffect, useRef, useState } from 'react';
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

import { assistantApi, type AssistantProposal } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
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

export default function AssistantScreen() {
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const markdownStyles = makeMarkdownStyles(colors);
  const client = useQueryClient();
  const insets = useSafeAreaInsets();
  const scroll = useRef<ScrollView>(null);
  const input = useRef<TextInput>(null);
  const initialSubmitted = useRef(false);
  const idempotencyKey = useRef<string | null>(null);
  const streamAbort = useRef<AbortController | null>(null);
  const params = useLocalSearchParams<{ initial?: string }>();
  const [text, setText] = useState(() =>
    typeof params.initial === 'string' ? params.initial : '',
  );
  const [streamingText, setStreamingText] = useState('');
  const [choices, setChoices] = useState<string[]>([]);
  const [memoryProposals, setMemoryProposals] = useState<AssistantProposal[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const history = useQuery({
    queryKey: ['assistant', 'history', userId],
    enabled: Boolean(token),
    queryFn: () => assistantApi.history(token!),
    retry: false,
  });
  const send = useMutation({
    mutationFn: ({ message, key }: { message: string; key: string }) =>
      (() => {
        streamAbort.current = new AbortController();
        return assistantApi.streamChat(
          token!,
          message,
          { onDelta: (delta) => setStreamingText((current) => current + delta) },
          streamAbort.current.signal,
          key,
        );
      })(),
    onSuccess: (result) => {
      streamAbort.current = null;
      setStreamingText('');
      idempotencyKey.current = null;
      setText('');
      setChoices(result.choices);
      setMemoryProposals(result.message.proposals.filter((proposal) => proposal.kind === 'note'));
      setNotice(null);
      void client.invalidateQueries({ queryKey: ['assistant', 'history', userId] });
    },
    onError: (error) => {
      streamAbort.current = null;
      setStreamingText('');
      if (error instanceof Error && error.name === 'AbortError') {
        setNotice('Génération arrêtée. Votre message reste dans la conversation.');
        return;
      }
      setNotice(
        error instanceof Error
          ? error.message
          : 'Le modèle est indisponible. Réessayez dans un instant.',
      );
    },
  });
  const cancelStreaming = () => {
    streamAbort.current?.abort();
    streamAbort.current = null;
    setStreamingText('');
    setNotice('Génération arrêtée. Votre message reste dans la conversation.');
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
  }, [history.data?.messages.length, choices.length, memoryProposals.length, send.isPending]);
  const submit = useCallback(() => {
    if (send.isPending) return;
    if (!text.trim()) {
      setNotice('Écrivez un message avant de l’envoyer.');
      return;
    }
    const key =
      idempotencyKey.current ?? `mobile-chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    idempotencyKey.current = key;
    send.mutate({ message: text.trim(), key });
  }, [send, setNotice, text]);
  useEffect(() => {
    if (
      !token ||
      initialSubmitted.current ||
      typeof params.initial !== 'string' ||
      !params.initial.trim()
    ) {
      return;
    }
    initialSubmitted.current = true;
    requestAnimationFrame(submit);
  }, [params.initial, submit, token]);
  const choose = (choice: string) => {
    setText(choice);
    setChoices([]);
    setNotice(null);
    requestAnimationFrame(() => input.current?.focus());
  };
  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
            <Text style={styles.backText}>‹ Accueil</Text>
          </Pressable>
          <Text style={styles.title}>Votre assistant</Text>
        </View>
        <ScrollView
          ref={scroll}
          contentContainerStyle={styles.content}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}
        >
          <Text style={styles.intro}>Écrivez à Cocoon. Il vous répond directement.</Text>
          <View style={styles.messages}>
            {history.isPending ? (
              <ActivityIndicator color={colors.spruce} style={styles.loader} />
            ) : null}
            {history.isError ? (
              <Text accessibilityRole="alert" style={styles.historyError}>
                Impossible de charger la conversation. Vérifiez votre connexion puis réessayez.
              </Text>
            ) : null}
            {history.data?.messages.length === 0 ? (
              <Text style={styles.empty}>Dites-moi ce que vous avez en tête.</Text>
            ) : null}
            {history.data?.messages.map((message) => (
              <View
                key={message.id}
                style={[
                  styles.message,
                  message.role === 'user' ? styles.userMessage : styles.agentMessage,
                ]}
              >
                {message.role === 'assistant' ? (
                  <Markdown
                    markdownit={assistantMarkdown}
                    rules={assistantMarkdownRules}
                    style={markdownStyles}
                  >
                    {message.content}
                  </Markdown>
                ) : (
                  <Text style={[styles.messageText, styles.userMessageText]}>
                    {message.content}
                  </Text>
                )}
              </View>
            ))}
            {send.isPending ? (
              <View accessibilityLiveRegion="polite" style={[styles.message, styles.agentMessage]}>
                <Text style={styles.messageText}>
                  {streamingText || 'Cocoon prépare une réponse…'}
                </Text>
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
                      accessibilityRole="button"
                      accessibilityLabel="Conserver ce souvenir"
                      disabled={confirmMemory.isPending || cancelMemory.isPending}
                      onPress={() => confirmMemory.mutate(proposal)}
                      style={styles.confirmMemory}
                    >
                      <Text style={styles.confirmMemoryText}>Conserver</Text>
                    </Pressable>
                    <Pressable
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
                  key={choice}
                  accessibilityRole="button"
                  accessibilityLabel={`Utiliser la réponse : ${choice}`}
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
            { paddingBottom: keyboardVisible ? 4 : Math.max(insets.bottom, 18) },
          ]}
        >
          {notice ? (
            <Text accessibilityRole="alert" style={styles.notice}>
              {notice}
            </Text>
          ) : null}
          <View style={styles.composerRow}>
            <TextInput
              ref={input}
              accessibilityLabel="Votre message"
              autoFocus
              blurOnSubmit={false}
              multiline
              onChangeText={(value) => {
                idempotencyKey.current = null;
                setText(value);
                setNotice(null);
              }}
              onFocus={() =>
                requestAnimationFrame(() => scroll.current?.scrollToEnd({ animated: true }))
              }
              onSubmitEditing={submit}
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
              sending={send.isPending}
              hasText={!!text.trim()}
              onSend={submit}
              onCancelSend={cancelStreaming}
              onError={setNotice}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    flex: { flex: 1 },
    header: {
      backgroundColor: colors.white,
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      paddingHorizontal: darkTheme.spacing.screen,
      paddingVertical: 10,
    },
    content: {
      flexGrow: 1,
      padding: darkTheme.spacing.content,
      paddingBottom: 18,
    },
    back: { justifyContent: 'center', minHeight: 38 },
    backText: { color: colors.spruce, fontWeight: '800' },
    title: {
      color: colors.ink,
      fontSize: 20,
      fontWeight: '700',
      marginBottom: 6,
    },
    intro: { color: colors.muted, fontSize: 15, lineHeight: 22 },
    messages: { marginTop: 10 },
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
    message: { borderRadius: 16, marginTop: 10, padding: 14 },
    userMessage: { alignSelf: 'flex-end', backgroundColor: colors.spruce, maxWidth: '90%' },
    agentMessage: {
      alignSelf: 'stretch',
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderWidth: 1,
      minWidth: 0,
      overflow: 'hidden',
    },
    messageText: { color: colors.ink, lineHeight: 21 },
    userMessageText: { color: colors.white },
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
      paddingTop: 8,
    },
    composerRow: { alignItems: 'flex-end', flexDirection: 'row', gap: 8 },
    composerInput: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 21,
      borderWidth: 1,
      color: colors.ink,
      elevation: 3,
      flex: 1,
      fontSize: 15,
      maxHeight: 110,
      minHeight: 42,
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
    sendIcon: {
      color: colors.white,
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 23,
      lineHeight: 25,
    },
    notice: { color: colors.berry, fontSize: 13, lineHeight: 19, marginBottom: 7 },
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
