import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

import { ApiError, secretApi } from '@/src/services/api';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(value),
  );
}

export default function SecretConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const accessToken = useSessionStore((state) => state.accessToken);
  const user = useSessionStore((state) => state.user);
  const secretToken = useSecretAccessStore((state) => state.token);
  const client = useQueryClient();
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const insets = useSafeAreaInsets();
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const conversation = useQuery({
    queryKey: ['secret', 'conversation', id],
    enabled: Boolean(accessToken && secretToken && id),
    queryFn: () => secretApi.getConversation(accessToken!, secretToken!, id),
    retry: false,
  });
  const messages = useQuery({
    queryKey: ['secret', 'messages', id],
    enabled: Boolean(accessToken && secretToken && id),
    queryFn: () => secretApi.listMessages(accessToken!, secretToken!, id),
    refetchInterval: 8000,
    retry: false,
  });
  const send = useMutation({
    mutationFn: () => secretApi.sendMessage(accessToken!, secretToken!, id, body.trim()),
    onSuccess: () => {
      setBody('');
      setError(null);
      void client.invalidateQueries({ queryKey: ['secret', 'messages', id] });
    },
    onError: (caught) =>
      setError(caught instanceof ApiError ? caught.message : 'Envoi impossible. Réessayez.'),
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
    if (!accessToken || !secretToken) router.replace('/home');
  }, [accessToken, secretToken]);
  useEffect(() => {
    requestAnimationFrame(() =>
      scroll.current?.scrollToEnd({ animated: messages.data?.length !== 0 }),
    );
  }, [messages.data?.length]);
  function submit() {
    if (body.trim() && !send.isPending) send.mutate();
  }

  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
            <Text style={styles.backText}>‹ Discussions</Text>
          </Pressable>
          <Text numberOfLines={1} style={styles.title}>
            {conversation.data?.name || 'Discussion privée'}
          </Text>
        </View>
        {messages.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {messages.isError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            Impossible de charger les messages.
          </Text>
        ) : null}
        <ScrollView
          ref={scroll}
          contentContainerStyle={styles.messages}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}
        >
          {messages.data?.length === 0 ? (
            <Text style={styles.empty}>Commencez la conversation avec un message simple.</Text>
          ) : null}
          {messages.data?.map((message) => {
            const mine = message.sender_id === user?.id;
            return (
              <View key={message.id} style={[styles.message, mine ? styles.mine : styles.theirs]}>
                <Text style={[styles.messageText, mine && styles.mineText]}>{message.body}</Text>
                <Text style={[styles.meta, mine && styles.mineMeta]}>
                  {formatTime(message.created_at)}
                </Text>
              </View>
            );
          })}
        </ScrollView>
        <View
          style={[
            styles.composer,
            { paddingBottom: keyboardVisible ? 4 : Math.max(insets.bottom, 18) },
          ]}
        >
          {error ? (
            <Text accessibilityRole="alert" style={styles.composerError}>
              {error}
            </Text>
          ) : null}
          <View style={styles.composerRow}>
            <TextInput
              accessibilityLabel="Votre message"
              autoFocus
              blurOnSubmit={false}
              multiline
              onChangeText={(value) => {
                setBody(value);
                setError(null);
              }}
              onSubmitEditing={submit}
              placeholder="Écrire un message"
              placeholderTextColor={colors.muted}
              returnKeyType="send"
              style={styles.composerInput}
              textAlignVertical="center"
              value={body}
            />
            <Pressable
              accessibilityLabel="Envoyer le message"
              accessibilityRole="button"
              disabled={send.isPending || !body.trim()}
              onPress={submit}
              style={[styles.send, (send.isPending || !body.trim()) && styles.sendDisabled]}
            >
              {send.isPending ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.sendIcon}>send</Text>
              )}
            </Pressable>
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
      alignItems: 'center',
      backgroundColor: colors.white,
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      flexDirection: 'row',
      gap: 12,
      paddingHorizontal: darkTheme.spacing.screen,
      paddingVertical: 8,
    },
    back: { justifyContent: 'center', minHeight: 38 },
    backText: { color: colors.spruce, fontWeight: '700' },
    title: { color: colors.ink, flex: 1, fontSize: 18, fontWeight: '700' },
    loader: { marginTop: 40 },
    error: {
      backgroundColor: '#FDECEE',
      borderRadius: darkTheme.radius.input,
      color: colors.berry,
      margin: darkTheme.spacing.screen,
      padding: 12,
    },
    messages: { flexGrow: 1, gap: 10, padding: darkTheme.spacing.content, paddingBottom: 18 },
    empty: { color: colors.muted, lineHeight: 22, marginTop: 24, textAlign: 'center' },
    message: {
      alignSelf: 'flex-start',
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: darkTheme.radius.card,
      borderWidth: 1,
      maxWidth: '84%',
      padding: 12,
    },
    theirs: { alignSelf: 'flex-start' },
    mine: { alignSelf: 'flex-end', backgroundColor: colors.spruce, borderColor: colors.spruce },
    messageText: { color: colors.ink, fontSize: 16, lineHeight: 22 },
    mineText: { color: colors.white },
    meta: { color: colors.muted, fontSize: 11, marginTop: 6, textAlign: 'right' },
    mineMeta: { color: colors.spruceOn },
    composer: {
      backgroundColor: 'transparent',
      paddingHorizontal: darkTheme.spacing.content,
      paddingTop: 8,
    },
    composerError: { color: colors.berry, fontSize: 13, marginBottom: 7 },
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
  });
}
