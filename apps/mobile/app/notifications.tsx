import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { assistantApi, authApi, type PersonalNotification } from '@/src/services/api';
import {
  registerForPersonalNotifications,
  routeForPersonalNotification,
} from '@/src/services/notifications';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';

const statusLabels: Record<PersonalNotification['provider_status'], string> = {
  pending: 'En attente',
  accepted: 'Transmise',
  delivered: 'Livrée',
  retrying: 'Nouvel essai prévu',
  failed: 'À consulter dans Cocoon',
  receipt_failed: 'À consulter dans Cocoon',
};

export default function NotificationsScreen() {
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmingDisable, setConfirmingDisable] = useState(false);
  const notifications = useQuery({
    queryKey: ['personal', 'notifications', userId],
    enabled: Boolean(token),
    queryFn: () => assistantApi.listNotifications(token!),
    retry: false,
  });
  const markRead = useMutation({
    mutationFn: (id: string) => assistantApi.markNotificationRead(token!, id),
    onSuccess: (updated) => {
      client.setQueryData<PersonalNotification[]>(
        ['personal', 'notifications', userId],
        (current) => current?.map((item) => (item.id === updated.id ? updated : item)),
      );
    },
  });
  const register = useMutation({
    mutationFn: () => registerForPersonalNotifications(token!),
    onSuccess: () => setNotice('Les notifications personnelles sont activées.'),
    onError: (error) =>
      setNotice(
        error instanceof Error ? error.message : 'Les notifications ne peuvent pas être activées.',
      ),
  });
  const revoke = useMutation({
    mutationFn: () => authApi.revokeConsent(token!, 'notifications.push'),
    onSuccess: () => {
      setConfirmingDisable(false);
      setNotice('Les notifications sont désactivées sur tous vos appareils.');
      void client.invalidateQueries({ queryKey: ['auth', 'consents', userId] });
    },
    onError: (error) =>
      setNotice(
        error instanceof Error
          ? error.message
          : 'Les notifications ne peuvent pas être désactivées.',
      ),
  });
  const openNotification = async (notification: PersonalNotification) => {
    if (!notification.read_at) await markRead.mutateAsync(notification.id);
    router.push(routeForPersonalNotification(notification.data));
  };

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Accueil</Text>
        </Pressable>
        <Text style={styles.kicker}>SUIVI PERSONNEL</Text>
        <Text style={styles.title}>Rappels</Text>
        <Text style={styles.intro}>
          Vos échéances restent visibles ici, même si aucun appareil n’a pu recevoir la
          notification.
        </Text>
        <Pressable
          accessibilityRole="button"
          disabled={!token || register.isPending}
          onPress={() => register.mutate()}
          style={[styles.enable, register.isPending && styles.disabled]}
        >
          <Text style={styles.enableText}>
            {register.isPending ? 'Activation…' : 'Activer les notifications'}
          </Text>
        </Pressable>
        {confirmingDisable ? (
          <View style={styles.confirmation}>
            <Text style={styles.confirmationText}>
              La désactivation retire les jetons de notification de tous vos appareils.
            </Text>
            <View style={styles.confirmationActions}>
              <Pressable
                accessibilityRole="button"
                disabled={revoke.isPending}
                onPress={() => setConfirmingDisable(false)}
                style={styles.secondaryAction}
              >
                <Text style={styles.secondaryActionText}>Annuler</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={!token || revoke.isPending}
                onPress={() => revoke.mutate()}
                style={[styles.disableAction, revoke.isPending && styles.disabled]}
              >
                <Text style={styles.disableActionText}>
                  {revoke.isPending ? 'Désactivation…' : 'Désactiver'}
                </Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={!token || revoke.isPending}
            onPress={() => setConfirmingDisable(true)}
            style={styles.disableLink}
          >
            <Text style={styles.disableLinkText}>Désactiver les notifications</Text>
          </Pressable>
        )}
        {notice ? (
          <Text accessibilityRole="alert" style={styles.notice}>
            {notice}
          </Text>
        ) : null}

        {notifications.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {notifications.isError ? (
          <View accessibilityRole="alert" style={styles.alert}>
            <Text style={styles.alertTitle}>Les rappels ne peuvent pas être chargés.</Text>
            <Text style={styles.alertText}>
              Réessayez lorsque la connexion à Cocoon sera rétablie.
            </Text>
            <Pressable onPress={() => void notifications.refetch()} style={styles.retry}>
              <Text style={styles.retryText}>Réessayer</Text>
            </Pressable>
          </View>
        ) : null}
        {!notifications.isPending && !notifications.isError && notifications.data?.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Aucun rappel à consulter.</Text>
            <Text style={styles.emptyText}>
              Cocoon vous préviendra ici lorsque quelque chose mérite votre attention.
            </Text>
          </View>
        ) : null}
        {notifications.data?.map((notification) => {
          const content = (
            <>
              <View style={styles.cardHeader}>
                <Text style={styles.status}>{statusLabels[notification.provider_status]}</Text>
                {!notification.read_at ? <Text style={styles.unread}>Nouveau</Text> : null}
              </View>
              <Text style={styles.cardTitle}>{notification.title}</Text>
              <Text style={styles.body}>{notification.body}</Text>
              <Text style={styles.date}>{formatDate(notification.created_at)}</Text>
            </>
          );
          return notification.read_at ? (
            <View key={notification.id} style={styles.card}>
              {content}
            </View>
          ) : (
            <Pressable
              key={notification.id}
              accessibilityRole="button"
              accessibilityLabel={`Marquer comme lu : ${notification.title}`}
              disabled={markRead.isPending}
              onPress={() => void openNotification(notification)}
              style={[styles.card, styles.unreadCard, markRead.isPending && styles.disabled]}
            >
              {content}
            </Pressable>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('fr-FR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    content: { padding: 24, paddingBottom: 44 },
    back: { minHeight: 44, justifyContent: 'center' },
    backText: { color: colors.spruce, fontWeight: '800' },
    kicker: {
      color: colors.clay,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.4,
      marginTop: 14,
    },
    title: { color: colors.ink, fontSize: 32, fontWeight: '700', marginTop: 7 },
    intro: { color: colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
    enable: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 14,
      justifyContent: 'center',
      marginTop: 18,
      minHeight: 48,
    },
    enableText: { color: colors.white, fontWeight: '800' },
    disableLink: { justifyContent: 'center', minHeight: 44, marginTop: 4 },
    disableLinkText: { color: colors.berry, fontWeight: '800', textAlign: 'center' },
    confirmation: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 14,
      borderWidth: 1,
      marginTop: 10,
      padding: 14,
    },
    confirmationText: { color: colors.muted, lineHeight: 20 },
    confirmationActions: { flexDirection: 'row', gap: 8, marginTop: 8 },
    secondaryAction: { flex: 1, justifyContent: 'center', minHeight: 44 },
    secondaryActionText: { color: colors.spruce, fontWeight: '800', textAlign: 'center' },
    disableAction: {
      backgroundColor: colors.berry,
      borderRadius: 10,
      flex: 1,
      justifyContent: 'center',
      minHeight: 44,
    },
    disableActionText: { color: colors.white, fontWeight: '800', textAlign: 'center' },
    notice: { color: colors.clay, lineHeight: 20, marginTop: 10 },
    loader: { marginVertical: 34 },
    alert: {
      backgroundColor: colors.berrySoft,
      borderColor: colors.berry,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 16,
    },
    alertTitle: { color: colors.ink, fontWeight: '800' },
    alertText: { color: colors.muted, lineHeight: 20, marginTop: 6 },
    retry: { justifyContent: 'center', minHeight: 44, marginTop: 6 },
    retryText: { color: colors.spruce, fontWeight: '800' },
    empty: {
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 18,
    },
    emptyTitle: { color: colors.ink, fontWeight: '800' },
    emptyText: { color: colors.muted, lineHeight: 20, marginTop: 6 },
    card: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 12,
      padding: 16,
    },
    unreadCard: { borderLeftColor: colors.spruce, borderLeftWidth: 4 },
    cardHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
    status: { color: colors.clay, fontSize: 12, fontWeight: '800', letterSpacing: 0.4 },
    unread: { color: colors.spruce, fontSize: 12, fontWeight: '800' },
    cardTitle: { color: colors.ink, fontSize: 17, fontWeight: '800', marginTop: 8 },
    body: { color: colors.muted, lineHeight: 21, marginTop: 6 },
    date: { color: colors.clay, fontSize: 12, marginTop: 12 },
    disabled: { opacity: 0.6 },
  });
}
