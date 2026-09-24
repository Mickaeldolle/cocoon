import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Pressable,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError, conversationsApi } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

export default function ConversationsScreen() {
  const accessToken = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [emails, setEmails] = useState('');
  const [error, setError] = useState<string | null>(null);
  const conversationsKey = ['conversations', userId] as const;
  const conversations = useQuery({
    queryKey: conversationsKey,
    enabled: Boolean(accessToken),
    queryFn: () => conversationsApi.list(accessToken!),
  });
  const create = useMutation({
    mutationFn: () =>
      conversationsApi.create(accessToken!, {
        name: name.trim() || undefined,
        invitee: emails.trim(),
      }),
    onSuccess: (conversation) => {
      void client.invalidateQueries({ queryKey: conversationsKey });
      setOpen(false);
      setName('');
      setEmails('');
      router.push({ pathname: '/conversation/[id]', params: { id: conversation.id } });
    },
    onError: (caught) =>
      setError(caught instanceof ApiError ? caught.message : 'Création impossible. Réessayez.'),
  });
  function submit() {
    if (!emails.trim()) {
      setError('Ajoutez le pseudo ou l’adresse email d’un proche.');
      return;
    }
    setError(null);
    create.mutate();
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.topbar}>
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Accueil</Text>
        </Pressable>
        <Pressable
          accessibilityLabel={open ? 'Fermer la création' : 'Créer une discussion'}
          accessibilityRole="button"
          onPress={() => setOpen((value) => !value)}
          style={styles.createButton}
        >
          <Text style={styles.createIcon}>{open ? 'close' : 'add'}</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Modal animationType="slide" transparent visible={open} onRequestClose={() => setOpen(false)}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalBackdrop}
          >
            <View style={styles.modalCard}>
              <View style={styles.modalHeader}>
                <View>
                  <Text style={styles.modalEyebrow}>Nouvelle discussion</Text>
                  <Text style={styles.modalTitle}>Inviter un proche</Text>
                </View>
                <Pressable
                  accessibilityLabel="Fermer la modale"
                  accessibilityRole="button"
                  onPress={() => setOpen(false)}
                  style={styles.closeButton}
                >
                  <Text style={styles.closeIcon}>close</Text>
                </Pressable>
              </View>
              <Text style={styles.helper}>
                La personne devra accepter l’invitation avant de voir les messages.
              </Text>
              <Text style={styles.label}>Nom de la discussion (facultatif)</Text>
              <TextInput
                accessibilityLabel="Nom de la discussion"
                value={name}
                onChangeText={setName}
                style={styles.input}
                placeholder="Ex. Week-end en famille"
                placeholderTextColor={colors.muted}
              />
              <Text style={styles.label}>Pseudo ou adresse email</Text>
              <TextInput
                accessibilityLabel="Pseudo ou adresse email de la personne à inviter"
                autoCapitalize="none"
                value={emails}
                onChangeText={setEmails}
                style={styles.input}
                placeholder="lea@exemple.fr ou Léa"
                placeholderTextColor={colors.muted}
              />
              <Text style={styles.helper}>
                Sans nom, la discussion prendra le nom de la personne invitée.
              </Text>
              {error ? (
                <Text accessibilityRole="alert" style={styles.formError}>
                  {error}
                </Text>
              ) : null}
              <Pressable
                accessibilityRole="button"
                disabled={create.isPending}
                onPress={submit}
                style={[styles.primary, create.isPending && styles.busy]}
              >
                {create.isPending ? (
                  <ActivityIndicator color={colors.white} />
                ) : (
                  <Text style={styles.primaryText}>Créer la discussion</Text>
                )}
              </Pressable>
            </View>
          </KeyboardAvoidingView>
        </Modal>
        {conversations.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {conversations.isError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            Impossible de charger vos discussions.
          </Text>
        ) : null}
        {conversations.data?.length === 0 ? (
          <Text style={styles.empty}>Aucune discussion pour le moment.</Text>
        ) : null}
        <View style={styles.list}>
          {conversations.data?.map((conversation) => (
            <View
              key={conversation.id}
              style={styles.row}
            >
              <Pressable
                accessibilityRole="button"
                disabled={conversation.membership_status === 'pending'}
                onPress={() =>
                  router.push({ pathname: '/conversation/[id]', params: { id: conversation.id } })
                }
                style={({ pressed }) => [styles.rowMain, pressed && styles.rowPressed]}
              >
                <View style={styles.rowCopy}>
                  <Text numberOfLines={1} style={styles.rowTitle}>
                    {conversation.name || 'Discussion privée'}
                  </Text>
                  {conversation.membership_status === 'pending' ? (
                    <Text style={styles.pendingLabel}>Invitation en attente</Text>
                  ) : null}
                </View>
                {conversation.membership_status === 'pending' ? null : (
                  <Text style={styles.rowArrow}>›</Text>
                )}
              </Pressable>
              {conversation.membership_status === 'pending' ? (
                <View style={styles.inviteActions}>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => {
                      void conversationsApi.accept(accessToken!, conversation.id).then(() =>
                        client.invalidateQueries({ queryKey: conversationsKey }),
                      );
                    }}
                    style={styles.acceptButton}
                  >
                    <Text style={styles.acceptText}>Accepter</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => {
                      void conversationsApi.decline(accessToken!, conversation.id).then(() =>
                        client.invalidateQueries({ queryKey: conversationsKey }),
                      );
                    }}
                    style={styles.declineButton}
                  >
                    <Text style={styles.declineText}>Refuser</Text>
                  </Pressable>
                </View>
              ) : null}
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    topbar: {
      alignItems: 'center',
      flexDirection: 'row',
      justifyContent: 'space-between',
      minHeight: 60,
      paddingHorizontal: darkTheme.spacing.content,
    },
    back: { justifyContent: 'center', minHeight: 44 },
    backText: { color: colors.spruce, fontWeight: '700' },
    createButton: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 22,
      height: 44,
      justifyContent: 'center',
      width: 44,
    },
    createIcon: {
      color: colors.white,
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 24,
      lineHeight: 26,
    },
    content: { paddingBottom: 36 },
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
    closeButton: { alignItems: 'center', height: 44, justifyContent: 'center', width: 44 },
    closeIcon: {
      color: colors.muted,
      fontFamily: 'MaterialSymbols_400Regular',
      fontSize: 24,
    },
    helper: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 8 },
    label: { color: colors.ink, fontSize: 14, fontWeight: '700', marginTop: 8 },
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
    primary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: darkTheme.radius.button,
      justifyContent: 'center',
      marginTop: 16,
      minHeight: 52,
    },
    primaryText: { color: colors.white, fontSize: 16, fontWeight: '700' },
    busy: { opacity: 0.7 },
    error: { color: colors.berry, lineHeight: 20, margin: darkTheme.spacing.content },
    formError: { color: colors.berry, lineHeight: 20, marginTop: 12 },
    loader: { marginTop: 32 },
    empty: { color: colors.muted, margin: darkTheme.spacing.content, textAlign: 'center' },
    list: { borderTopColor: colors.border, borderTopWidth: 1 },
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
    rowArrow: { color: colors.spruce, fontSize: 28, lineHeight: 30 },
    pendingLabel: { color: colors.muted, fontSize: 13, marginTop: 4 },
    inviteActions: { flexDirection: 'row', gap: 8, marginTop: 10 },
    acceptButton: {
      backgroundColor: colors.spruce,
      borderRadius: darkTheme.radius.button,
      minHeight: 44,
      paddingHorizontal: 16,
      justifyContent: 'center',
    },
    acceptText: { color: colors.white, fontWeight: '700' },
    declineButton: {
      borderColor: colors.border,
      borderRadius: darkTheme.radius.button,
      borderWidth: 1,
      minHeight: 44,
      paddingHorizontal: 16,
      justifyContent: 'center',
    },
    declineText: { color: colors.ink, fontWeight: '700' },
  });
}
