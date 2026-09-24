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

import { personalApi, type PersonalProject } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';

const statusLabels: Record<PersonalProject['status'], string> = {
  active: 'En cours',
  paused: 'En pause',
  completed: 'Terminé',
};

export default function ProjectsScreen() {
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const client = useQueryClient();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const projects = useQuery({
    queryKey: ['personal', 'projects', userId],
    enabled: Boolean(token),
    queryFn: () => personalApi.listProjects(token!),
    retry: false,
  });
  const create = useMutation({
    mutationFn: () =>
      personalApi.createProject(token!, {
        name: name.trim(),
        description: description.trim() || null,
      }),
    onSuccess: () => {
      setName('');
      setDescription('');
      setNotice('Projet créé.');
      void client.invalidateQueries({ queryKey: ['personal', 'projects', userId] });
    },
    onError: () => setNotice('Le projet ne peut pas être créé pour le moment.'),
  });
  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: PersonalProject['status'] }) =>
      personalApi.updateProject(token!, id, { status }),
    onSuccess: () => {
      setNotice('Statut du projet mis à jour.');
      void client.invalidateQueries({ queryKey: ['personal', 'projects', userId] });
    },
    onError: () => setNotice('Le statut ne peut pas être mis à jour pour le moment.'),
  });
  const canCreate = Boolean(name.trim()) && !create.isPending;

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Profil</Text>
        </Pressable>
        <Text style={styles.kicker}>MON ESPACE</Text>
        <Text style={styles.title}>Mes projets</Text>
        <Text style={styles.intro}>
          Les projets restent personnels. Cocoon peut s’en servir pour mieux comprendre le contexte
          de vos demandes.
        </Text>
        <View style={styles.formCard}>
          <Text style={styles.sectionTitle}>Ajouter un projet</Text>
          <Text style={styles.label}>Nom</Text>
          <TextInput
            accessibilityLabel="Nom du projet"
            placeholder="Ex. Refonte de la maison"
            placeholderTextColor={colors.muted}
            value={name}
            onChangeText={setName}
            style={styles.input}
          />
          <Text style={styles.label}>Description (facultative)</Text>
          <TextInput
            accessibilityLabel="Description du projet"
            multiline
            placeholder="Ce que vous voulez garder en tête"
            placeholderTextColor={colors.muted}
            value={description}
            onChangeText={setDescription}
            style={[styles.input, styles.multiline]}
          />
          <Pressable
            accessibilityRole="button"
            disabled={!canCreate}
            onPress={() => create.mutate()}
            style={[styles.primary, !canCreate && styles.disabled]}
          >
            <Text style={styles.primaryText}>
              {create.isPending ? 'Création…' : 'Créer le projet'}
            </Text>
          </Pressable>
        </View>
        {notice ? (
          <Text accessibilityRole="alert" style={styles.notice}>
            {notice}
          </Text>
        ) : null}
        {projects.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {projects.isError ? (
          <View style={styles.alert}>
            <Text style={styles.alertTitle}>Les projets ne peuvent pas être chargés.</Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => void projects.refetch()}
              style={styles.retry}
            >
              <Text style={styles.retryText}>Réessayer</Text>
            </Pressable>
          </View>
        ) : null}
        {!projects.isPending && !projects.isError && projects.data?.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Aucun projet pour le moment.</Text>
            <Text style={styles.emptyText}>
              Ajoutez un projet pour donner un contexte durable à Cocoon.
            </Text>
          </View>
        ) : null}
        {projects.data?.map((project) => (
          <ProjectCard
            key={project.id}
            project={project}
            styles={styles}
            pending={update.isPending}
            onStatusChange={(status) => update.mutate({ id: project.id, status })}
          />
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function ProjectCard({
  project,
  styles,
  pending,
  onStatusChange,
}: {
  project: PersonalProject;
  styles: ReturnType<typeof makeStyles>;
  pending: boolean;
  onStatusChange: (status: PersonalProject['status']) => void;
}) {
  const nextStatus: PersonalProject['status'] =
    project.status === 'active' ? 'paused' : project.status === 'paused' ? 'active' : 'active';
  return (
    <View style={styles.card}>
      <View style={styles.cardHeading}>
        <Text style={styles.cardTitle}>{project.name}</Text>
        <Text style={styles.status}>{statusLabels[project.status]}</Text>
      </View>
      {project.description ? <Text style={styles.description}>{project.description}</Text> : null}
      {project.status === 'completed' ? (
        <Pressable
          accessibilityRole="button"
          disabled={pending}
          onPress={() => onStatusChange('active')}
          style={[styles.secondary, pending && styles.disabled]}
        >
          <Text style={styles.secondaryText}>Rouvrir</Text>
        </Pressable>
      ) : (
        <Pressable
          accessibilityRole="button"
          disabled={pending}
          onPress={() => onStatusChange(nextStatus)}
          style={[styles.secondary, pending && styles.disabled]}
        >
          <Text style={styles.secondaryText}>
            {nextStatus === 'paused' ? 'Mettre en pause' : 'Reprendre'}
          </Text>
        </Pressable>
      )}
      {project.status !== 'completed' ? (
        <Pressable
          accessibilityRole="button"
          disabled={pending}
          onPress={() => onStatusChange('completed')}
          style={[styles.linkAction, pending && styles.disabled]}
        >
          <Text style={styles.linkText}>Marquer terminé</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    content: { padding: 24, paddingBottom: 44 },
    back: { justifyContent: 'center', minHeight: 44 },
    backText: { color: colors.spruce, fontWeight: '800' },
    kicker: {
      color: colors.clay,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.4,
      marginTop: 14,
    },
    title: { color: colors.ink, fontSize: 30, fontWeight: '700', marginTop: 7 },
    intro: { color: colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
    formCard: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 16,
    },
    sectionTitle: { color: colors.ink, fontSize: 17, fontWeight: '800' },
    label: { color: colors.muted, fontSize: 13, fontWeight: '700', marginTop: 14 },
    input: {
      backgroundColor: colors.linen,
      borderColor: colors.border,
      borderRadius: 10,
      borderWidth: 1,
      color: colors.ink,
      marginTop: 6,
      minHeight: 44,
      paddingHorizontal: 12,
    },
    multiline: { minHeight: 72, paddingTop: 10, textAlignVertical: 'top' },
    primary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 12,
      justifyContent: 'center',
      marginTop: 16,
      minHeight: 44,
      paddingHorizontal: 14,
    },
    primaryText: { color: colors.white, fontWeight: '800' },
    notice: { color: colors.clay, lineHeight: 20, marginTop: 14 },
    loader: { marginVertical: 28 },
    alert: {
      backgroundColor: colors.berrySoft,
      borderColor: colors.berry,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 16,
    },
    alertTitle: { color: colors.ink, fontWeight: '800' },
    retry: { justifyContent: 'center', marginTop: 8, minHeight: 40 },
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
      marginTop: 14,
      padding: 16,
    },
    cardHeading: {
      alignItems: 'center',
      flexDirection: 'row',
      justifyContent: 'space-between',
      gap: 12,
    },
    cardTitle: { color: colors.ink, flex: 1, fontSize: 17, fontWeight: '800' },
    status: { color: colors.clay, fontSize: 12, fontWeight: '800' },
    description: { color: colors.muted, lineHeight: 20, marginTop: 8 },
    secondary: {
      borderColor: colors.spruce,
      borderRadius: 12,
      borderWidth: 1,
      justifyContent: 'center',
      marginTop: 14,
      minHeight: 42,
      paddingHorizontal: 14,
    },
    secondaryText: { color: colors.spruce, fontWeight: '800', textAlign: 'center' },
    linkAction: { justifyContent: 'center', minHeight: 40, marginTop: 4 },
    linkText: { color: colors.berry, fontWeight: '800', textAlign: 'center' },
    disabled: { opacity: 0.55 },
  });
}
