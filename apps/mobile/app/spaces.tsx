import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
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

import { ApiError, familySpacesApi } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

export default function SpacesScreen() {
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const theme = { ...darkTheme, colors };
  const accessToken = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const client = useQueryClient();
  const spacesKey = ['family-spaces', userId] as const;
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spaces = useQuery({
    queryKey: spacesKey,
    enabled: Boolean(accessToken),
    queryFn: () => familySpacesApi.list(accessToken!),
  });
  const create = useMutation({
    mutationFn: () =>
      familySpacesApi.create(accessToken!, {
        name: name.trim(),
        description: description.trim() || undefined,
      }),
    onSuccess: (space) => {
      void client.invalidateQueries({ queryKey: spacesKey });
      setName('');
      setDescription('');
      setFormOpen(false);
      router.push(`/space/${space.id}` as never);
    },
    onError: (caught) =>
      setError(caught instanceof ApiError ? caught.message : 'Création impossible. Réessayez.'),
  });

  function submit() {
    if (!name.trim()) {
      setError('Donnez un nom à cet espace.');
      return;
    }
    setError(null);
    create.mutate();
  }

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Accueil</Text>
        </Pressable>
        <Text style={styles.kicker}>VOS LIENS</Text>
        <Text style={styles.title}>Espaces familiaux</Text>
        <Text style={styles.description}>
          Chaque espace réunit les proches qui partagent les mêmes nouvelles.
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => setFormOpen((open) => !open)}
          style={styles.primary}
        >
          <Text style={styles.primaryText}>
            {formOpen ? 'Fermer la création' : 'Créer un espace'}
          </Text>
        </Pressable>
        {formOpen ? (
          <View style={styles.form}>
            <Text style={styles.label}>Nom de l’espace</Text>
            <TextInput
              accessibilityLabel="Nom de l’espace"
              autoFocus
              value={name}
              onChangeText={setName}
              style={styles.input}
              placeholder="Ex. Famille Martin"
              placeholderTextColor={theme.colors.muted}
            />
            <Text style={styles.label}>Description (facultatif)</Text>
            <TextInput
              accessibilityLabel="Description de l’espace"
              value={description}
              onChangeText={setDescription}
              multiline
              style={[styles.input, styles.textarea]}
              placeholder="À quoi servira cet espace ?"
              placeholderTextColor={theme.colors.muted}
            />
            {error ? (
              <Text accessibilityRole="alert" style={styles.error}>
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
                <ActivityIndicator color={theme.colors.white} />
              ) : (
                <Text style={styles.primaryText}>Créer l’espace</Text>
              )}
            </Pressable>
          </View>
        ) : null}
        {spaces.isPending ? (
          <ActivityIndicator color={theme.colors.spruce} style={styles.loader} />
        ) : null}
        {spaces.isError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            Impossible de charger vos espaces. Tirez pour réessayer.
          </Text>
        ) : null}
        {spaces.data?.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Votre premier espace commence ici.</Text>
            <Text style={styles.emptyText}>Créez-le, puis ajoutez les membres autorisés.</Text>
          </View>
        ) : null}
        {spaces.data?.map((space) => (
          <Pressable
            key={space.id}
            accessibilityRole="button"
            onPress={() => router.push(`/space/${space.id}` as never)}
            style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
          >
            <Text style={styles.cardTitle}>{space.name}</Text>
            <Text style={styles.cardText}>
              {space.description || 'Un espace privé pour votre famille.'}
            </Text>
            <Text style={styles.role}>
              {space.role === 'OWNER'
                ? 'Propriétaire'
                : space.role === 'ADMIN'
                  ? 'Administrateur'
                  : 'Membre'}
            </Text>
          </Pressable>
        ))}
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
    kicker: {
      color: theme.colors.clay,
      fontSize: 12,
      fontWeight: '800',
      letterSpacing: 1.6,
      marginTop: 12,
    },
    title: { color: theme.colors.ink, fontSize: 32, fontWeight: '700', marginTop: 8 },
    description: { color: theme.colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
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
    form: {
      backgroundColor: theme.colors.white,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      marginTop: 16,
      padding: 16,
    },
    label: { color: theme.colors.ink, fontSize: 14, fontWeight: '700', marginTop: 8 },
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
    textarea: { minHeight: 96, paddingTop: 12, textAlignVertical: 'top' },
    error: {
      backgroundColor: '#FDECEE',
      borderRadius: theme.radius.input,
      color: theme.colors.berry,
      marginTop: 12,
      padding: 12,
    },
    loader: { marginTop: 32 },
    empty: {
      borderColor: theme.colors.border,
      borderRadius: theme.radius.card,
      borderStyle: 'dashed',
      borderWidth: 1,
      marginTop: 24,
      padding: 20,
    },
    emptyTitle: { color: theme.colors.ink, fontSize: 17, fontWeight: '700' },
    emptyText: { color: theme.colors.muted, lineHeight: 21, marginTop: 6 },
    card: {
      backgroundColor: theme.colors.white,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      marginTop: 14,
      padding: 18,
    },
    cardPressed: { backgroundColor: '#E5EEE8' },
    cardTitle: { color: theme.colors.ink, fontSize: 18, fontWeight: '700' },
    cardText: { color: theme.colors.muted, lineHeight: 21, marginTop: 6 },
    role: { color: theme.colors.spruce, fontSize: 13, fontWeight: '700', marginTop: 14 },
  });
}
