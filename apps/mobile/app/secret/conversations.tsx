import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError, secretApi } from '@/src/services/api';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

const secretConversationsKey = ['secret', 'conversations'];

export default function SecretConversationsScreen() {
  const accessToken = useSessionStore((state) => state.accessToken);
  const secretToken = useSecretAccessStore((state) => state.token);
  const clearSecretAccess = useSecretAccessStore((state) => state.clear);
  const client = useQueryClient();
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [invitee, setInvitee] = useState('');
  const [error, setError] = useState<string | null>(null);
  const conversations = useQuery({
    queryKey: secretConversationsKey,
    enabled: Boolean(accessToken && secretToken),
    queryFn: () => secretApi.listConversations(accessToken!, secretToken!),
    retry: false,
  });

  useEffect(() => {
    if (!accessToken || !secretToken) router.replace('/home');
  }, [accessToken, secretToken]);

  async function lock() {
    if (accessToken && secretToken)
      await secretApi.lock(accessToken, secretToken).catch(() => undefined);
    clearSecretAccess();
    client.removeQueries({ queryKey: ['secret'] });
    router.replace('/home');
  }

  async function createConversation() {
    if (!invitee.trim() || !accessToken || !secretToken) {
      setError('Ajoutez le pseudo ou l’adresse email d’un proche.');
      return;
    }
    setError(null);
    try {
      const conversation = await secretApi.createConversation(accessToken, secretToken, {
        name: name.trim() || undefined,
        invitee: invitee.trim(),
      });
      await client.invalidateQueries({ queryKey: secretConversationsKey });
      setOpen(false);
      setName('');
      setInvitee('');
      router.push({ pathname: '/secret/conversation/[id]', params: { id: conversation.id } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Création impossible. Réessayez.');
    }
  }

  useEffect(() => {
    if (conversations.error instanceof ApiError && conversations.error.status === 401) void lock();
  }, [conversations.error]);

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.topbar}>
        <Text style={styles.title}>Discussions</Text>
        <View style={styles.topbarActions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Verrouiller les discussions"
            onPress={() => void lock()}
            style={styles.lock}
          >
            <Text style={styles.lockText}>Verrouiller</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Créer une discussion secrète"
            onPress={() => setOpen(true)}
            style={styles.add}
          >
            <Text style={styles.addText}>add</Text>
          </Pressable>
        </View>
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Modal animationType="slide" transparent visible={open} onRequestClose={() => setOpen(false)}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalBackdrop}
          >
            <View style={styles.modalCard}>
              <View style={styles.modalHeader}>
                <View>
                  <Text style={styles.modalEyebrow}>Nouvelle discussion secrète</Text>
                  <Text style={styles.modalTitle}>Inviter un proche</Text>
                </View>
                <Pressable
                  accessibilityLabel="Fermer la modale"
                  accessibilityRole="button"
                  onPress={() => setOpen(false)}
                  style={styles.close}
                >
                  <Text style={styles.closeText}>close</Text>
                </Pressable>
              </View>
              <Text style={styles.helper}>L’invité devra accepter avant de voir les messages.</Text>
              <Text style={styles.label}>Nom de la discussion (facultatif)</Text>
              <TextInput
                accessibilityLabel="Nom de la discussion"
                onChangeText={setName}
                placeholder="Ex. À deux"
                placeholderTextColor={colors.muted}
                style={styles.input}
                value={name}
              />
              <Text style={styles.label}>Pseudo ou adresse email</Text>
              <TextInput
                accessibilityLabel="Pseudo ou adresse email de la personne à inviter"
                autoCapitalize="none"
                onChangeText={setInvitee}
                placeholder="lea@exemple.fr ou Léa"
                placeholderTextColor={colors.muted}
                style={styles.input}
                value={invitee}
              />
              <Text style={styles.helper}>Sans nom, le nom de l’invité sera utilisé.</Text>
              {error ? <Text style={styles.formError}>{error}</Text> : null}
              <Pressable accessibilityRole="button" onPress={() => void createConversation()} style={styles.primary}>
                <Text style={styles.primaryText}>Créer la discussion</Text>
              </Pressable>
            </View>
          </KeyboardAvoidingView>
        </Modal>
        {conversations.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {conversations.isError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            L’accès n’est plus disponible. Réessayez après vérification.
          </Text>
        ) : null}
        {conversations.data?.length === 0 ? (
          <Text style={styles.empty}>Aucune discussion à afficher.</Text>
        ) : null}
        {conversations.data?.map((conversation) => (
          <View
            key={conversation.id}
            style={styles.row}
          >
            <Pressable
              accessibilityRole="button"
              disabled={conversation.membership_status === 'pending'}
              onPress={() =>
                router.push({
                  pathname: '/secret/conversation/[id]',
                  params: { id: conversation.id },
                })
              }
              style={({ pressed }) => [styles.rowMain, pressed && styles.rowPressed]}
            >
              <View style={styles.rowCopy}>
                <Text numberOfLines={1} style={styles.rowTitle}>
                  {conversation.name || 'Discussion privée'}
                </Text>
                {conversation.membership_status === 'pending' ? (
                  <Text style={styles.pending}>Invitation en attente</Text>
                ) : null}
              </View>
              {conversation.membership_status === 'pending' ? null : <Text style={styles.arrow}>›</Text>}
            </Pressable>
            {conversation.membership_status === 'pending' ? (
              <View style={styles.actions}>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => {
                    if (accessToken && secretToken)
                      void secretApi
                        .acceptInvitation(accessToken, secretToken, conversation.id)
                        .then(() => client.invalidateQueries({ queryKey: secretConversationsKey }));
                  }}
                  style={styles.accept}
                >
                  <Text style={styles.acceptText}>Accepter</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => {
                    if (accessToken && secretToken)
                      void secretApi
                        .declineInvitation(accessToken, secretToken, conversation.id)
                        .then(() => client.invalidateQueries({ queryKey: secretConversationsKey }));
                  }}
                  style={styles.decline}
                >
                  <Text style={styles.declineText}>Refuser</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    topbar: {
      alignItems: 'center',
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      flexDirection: 'row',
      justifyContent: 'space-between',
      minHeight: 64,
      paddingHorizontal: darkTheme.spacing.content,
    },
    title: { color: colors.ink, fontSize: 20, fontWeight: '700' },
    topbarActions: { alignItems: 'center', flexDirection: 'row' },
    lock: {
      alignItems: 'center',
      borderColor: colors.border,
      borderRadius: darkTheme.radius.button,
      borderWidth: 1,
      justifyContent: 'center',
      minHeight: 44,
      paddingHorizontal: 13,
    },
    lockText: { color: colors.ink, fontSize: 14, fontWeight: '700' },
    add: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 22,
      height: 44,
      justifyContent: 'center',
      marginLeft: 8,
      width: 44,
    },
    addText: {
      color: colors.white,
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 24,
    },
    content: { paddingBottom: 36 },
    loader: { marginTop: 36 },
    error: { color: colors.berry, lineHeight: 20, margin: darkTheme.spacing.content },
    empty: { color: colors.muted, margin: darkTheme.spacing.content, textAlign: 'center' },
    row: {
      backgroundColor: colors.white,
      borderBottomColor: colors.border,
      borderBottomWidth: 1,
      padding: darkTheme.spacing.content,
    },
    rowMain: { alignItems: 'center', flexDirection: 'row', minHeight: 44 },
    rowCopy: { flex: 1, marginRight: 12 },
    rowPressed: { backgroundColor: colors.linenMuted },
    rowTitle: { color: colors.ink, flex: 1, fontSize: 17, fontWeight: '700', marginRight: 12 },
    arrow: { color: colors.spruce, fontSize: 28, lineHeight: 30 },
    pending: { color: colors.muted, fontSize: 13, marginTop: 4 },
    actions: { flexDirection: 'row', gap: 8, marginTop: 10 },
    accept: {
      backgroundColor: colors.spruce,
      borderRadius: darkTheme.radius.button,
      justifyContent: 'center',
      minHeight: 44,
      paddingHorizontal: 16,
    },
    acceptText: { color: colors.white, fontWeight: '700' },
    decline: {
      borderColor: colors.border,
      borderRadius: darkTheme.radius.button,
      borderWidth: 1,
      justifyContent: 'center',
      minHeight: 44,
      paddingHorizontal: 16,
    },
    declineText: { color: colors.ink, fontWeight: '700' },
    modalBackdrop: {
      backgroundColor: 'rgba(10, 12, 18, 0.62)',
      flex: 1,
      justifyContent: 'flex-end',
    },
    modalCard: {
      backgroundColor: colors.white,
      borderTopLeftRadius: darkTheme.radius.card,
      borderTopRightRadius: darkTheme.radius.card,
      padding: darkTheme.spacing.content,
      paddingBottom: 28,
    },
    modalHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
    modalEyebrow: { color: colors.spruce, fontSize: 13, fontWeight: '700' },
    modalTitle: { color: colors.ink, fontSize: 22, fontWeight: '700', marginTop: 3 },
    close: { alignItems: 'center', height: 44, justifyContent: 'center', width: 44 },
    closeText: { color: colors.muted, fontFamily: 'MaterialSymbols_400Regular', fontSize: 24 },
    helper: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 8 },
    label: { color: colors.ink, fontSize: 14, fontWeight: '700', marginTop: 12 },
    input: {
      backgroundColor: colors.linen,
      borderColor: colors.border,
      borderRadius: darkTheme.radius.input,
      borderWidth: 1,
      color: colors.ink,
      fontSize: 16,
      marginTop: 6,
      minHeight: 50,
      paddingHorizontal: 12,
    },
    formError: { color: colors.berry, lineHeight: 20, marginTop: 12 },
    primary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: darkTheme.radius.button,
      justifyContent: 'center',
      marginTop: 16,
      minHeight: 52,
    },
    primaryText: { color: colors.white, fontSize: 16, fontWeight: '700' },
  });
}
