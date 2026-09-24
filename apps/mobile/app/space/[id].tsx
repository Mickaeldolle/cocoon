import { useMutation, useQuery } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError, familySpacesApi, type FamilyRole } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

export default function SpaceDetailScreen() {
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const theme = { ...darkTheme, colors };
  const { id } = useLocalSearchParams<{ id: string }>();
  const accessToken = useSessionStore((state) => state.accessToken);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<FamilyRole>('MEMBER');
  const [error, setError] = useState<string | null>(null);
  const space = useQuery({
    queryKey: ['family-space', id],
    enabled: Boolean(accessToken && id),
    queryFn: () => familySpacesApi.get(accessToken!, id),
  });
  const addMember = useMutation({
    mutationFn: () => familySpacesApi.addMember(accessToken!, id, email.trim(), role),
    onSuccess: () => {
      setEmail('');
      setError(null);
    },
    onError: (caught) =>
      setError(caught instanceof ApiError ? caught.message : 'Ajout impossible. Réessayez.'),
  });
  const canManage = space.data?.role === 'OWNER' || space.data?.role === 'ADMIN';
  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Espaces</Text>
        </Pressable>
        {space.isPending ? (
          <ActivityIndicator color={theme.colors.spruce} style={styles.loader} />
        ) : null}
        {space.isError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            Cet espace est introuvable ou n’est plus accessible.
          </Text>
        ) : null}
        {space.data ? (
          <>
            <Text style={styles.kicker}>ESPACE PRIVÉ</Text>
            <Text style={styles.title}>{space.data.name}</Text>
            <Text style={styles.description}>
              {space.data.description || 'Un espace familial privé.'}
            </Text>
            <View style={styles.notice}>
              <Text style={styles.noticeTitle}>Publications à venir</Text>
              <Text style={styles.noticeText}>
                Le fil familial et les médias sécurisés seront ajoutés après la première boucle de
                test des espaces et conversations.
              </Text>
            </View>
            {canManage ? (
              <View style={styles.form}>
                <Text style={styles.formTitle}>Ajouter un membre</Text>
                <Text style={styles.label}>Adresse email</Text>
                <TextInput
                  accessibilityLabel="Adresse email du membre"
                  autoCapitalize="none"
                  keyboardType="email-address"
                  value={email}
                  onChangeText={setEmail}
                  style={styles.input}
                  placeholder="proche@exemple.fr"
                  placeholderTextColor={theme.colors.muted}
                />
                <Text style={styles.label}>Rôle</Text>
                <View style={styles.roles}>
                  {(['MEMBER', 'ADMIN'] as FamilyRole[]).map((candidate) => (
                    <Pressable
                      key={candidate}
                      accessibilityRole="button"
                      onPress={() => setRole(candidate)}
                      style={[styles.roleButton, role === candidate && styles.roleSelected]}
                    >
                      <Text
                        style={[styles.roleText, role === candidate && styles.roleTextSelected]}
                      >
                        {candidate === 'ADMIN' ? 'Administrateur' : 'Membre'}
                      </Text>
                    </Pressable>
                  ))}
                </View>
                {error ? (
                  <Text accessibilityRole="alert" style={styles.error}>
                    {error}
                  </Text>
                ) : null}
                <Pressable
                  accessibilityRole="button"
                  disabled={addMember.isPending}
                  onPress={() => {
                    if (!email.trim()) {
                      setError('Saisissez une adresse email.');
                      return;
                    }
                    addMember.mutate();
                  }}
                  style={[styles.primary, addMember.isPending && styles.busy]}
                >
                  {addMember.isPending ? (
                    <ActivityIndicator color={theme.colors.white} />
                  ) : (
                    <Text style={styles.primaryText}>Ajouter ce membre</Text>
                  )}
                </Pressable>
              </View>
            ) : (
              <Text style={styles.muted}>
                Seuls les propriétaires et administrateurs peuvent ajouter un membre.
              </Text>
            )}
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}
function makeStyles(colors: ColorTokens) {
  const theme = { ...darkTheme, colors };
  return StyleSheet.create({
    screen: { backgroundColor: theme.colors.linen, flex: 1 },
    content: { padding: theme.spacing.screen, paddingBottom: 36 },
    back: { minHeight: 44, justifyContent: 'center' },
    backText: { color: theme.colors.spruce, fontWeight: '700' },
    loader: { marginTop: 60 },
    kicker: {
      color: theme.colors.clay,
      fontSize: 12,
      fontWeight: '800',
      letterSpacing: 1.6,
      marginTop: 16,
    },
    title: { color: theme.colors.ink, fontSize: 32, fontWeight: '700', marginTop: 8 },
    description: { color: theme.colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
    notice: {
      backgroundColor: '#E5EEE8',
      borderRadius: theme.radius.card,
      marginTop: 24,
      padding: 18,
    },
    noticeTitle: { color: theme.colors.ink, fontSize: 17, fontWeight: '700' },
    noticeText: { color: theme.colors.muted, lineHeight: 21, marginTop: 6 },
    form: {
      backgroundColor: theme.colors.white,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      marginTop: 24,
      padding: 16,
    },
    formTitle: { color: theme.colors.ink, fontSize: 18, fontWeight: '700' },
    label: { color: theme.colors.ink, fontSize: 14, fontWeight: '700', marginTop: 16 },
    input: {
      backgroundColor: theme.colors.linen,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.input,
      borderWidth: 1,
      color: theme.colors.ink,
      fontSize: 16,
      marginTop: 6,
      minHeight: 50,
      paddingHorizontal: 12,
    },
    roles: { flexDirection: 'row', gap: 8, marginTop: 8 },
    roleButton: {
      borderColor: theme.colors.border,
      borderRadius: theme.radius.input,
      borderWidth: 1,
      minHeight: 44,
      paddingHorizontal: 14,
      justifyContent: 'center',
    },
    roleSelected: { backgroundColor: '#E5EEE8', borderColor: theme.colors.spruce },
    roleText: { color: theme.colors.muted, fontWeight: '700' },
    roleTextSelected: { color: theme.colors.spruce },
    primary: {
      alignItems: 'center',
      backgroundColor: theme.colors.spruce,
      borderRadius: theme.radius.button,
      justifyContent: 'center',
      marginTop: 20,
      minHeight: 52,
    },
    primaryText: { color: theme.colors.white, fontSize: 16, fontWeight: '700' },
    busy: { opacity: 0.7 },
    error: {
      backgroundColor: '#FDECEE',
      borderRadius: theme.radius.input,
      color: theme.colors.berry,
      marginTop: 12,
      padding: 12,
    },
    muted: { color: theme.colors.muted, lineHeight: 21, marginTop: 24 },
  });
}
