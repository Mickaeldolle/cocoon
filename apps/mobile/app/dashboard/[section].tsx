import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

import { assistantApi, personalApi, type MealPlanEntry } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

const pages = {
  tasks: ['À FAIRE', 'Vos priorités', 'Un détail à la fois, sans perdre le fil.'],
  groceries: ['COURSES', 'Votre liste', 'Cochez au fur et à mesure dans le magasin.'],
  health: ['SANTÉ', 'Votre mouvement', 'Votre progression de la semaine, simplement.'],
} as const;
type Section = keyof typeof pages;
const trainingLabels = { renforcement: 'Renforcement', course: 'Course', mobilite: 'Mobilité' };

export default function DashboardSectionScreen() {
  const raw = useLocalSearchParams<{ section: Section }>().section;
  const section: Section = raw in pages ? raw : 'tasks';
  const [kicker, title, intro] = pages[section];
  const token = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const client = useQueryClient();
  const [value, setValue] = useState('');
  const [detail, setDetail] = useState('');
  const [timing, setTiming] = useState('Cette semaine');
  const [type, setType] = useState<'renforcement' | 'course' | 'mobilite'>('renforcement');
  const [notice, setNotice] = useState<string | null>(null);
  const [meals, setMeals] = useState<MealPlanEntry[] | null>(null);
  const tasks = useQuery({
    queryKey: ['personal', 'tasks', userId],
    enabled: Boolean(token),
    queryFn: () => personalApi.listTasks(token!),
    retry: false,
  });
  const groceries = useQuery({
    queryKey: ['personal', 'groceries', userId],
    enabled: Boolean(token),
    queryFn: () => personalApi.listGroceries(token!),
    retry: false,
  });
  const trainings = useQuery({
    queryKey: ['personal', 'trainings', userId],
    enabled: Boolean(token),
    queryFn: () => personalApi.listTrainings(token!),
    retry: false,
  });
  const profile = useQuery({
    queryKey: ['personal', 'profile', userId],
    enabled: Boolean(token),
    queryFn: () => personalApi.getProfile(token!),
    retry: false,
  });
  const key = section === 'tasks' ? 'tasks' : section === 'groceries' ? 'groceries' : 'trainings';
  const add = useMutation<unknown, Error, void>({
    mutationFn: () => {
      if (!value.trim()) throw new Error('Ajoutez un intitulé avant d’enregistrer.');
      if (section === 'tasks')
        return personalApi.createTask(token!, {
          title: value.trim(),
          detail: detail.trim() || null,
          due_date: null,
        });
      if (section === 'groceries') return personalApi.createGrocery(token!, value.trim());
      return personalApi.createTraining(token!, {
        label: value.trim(),
        training_type: type,
        timing: timing.trim() || 'Cette semaine',
      });
    },
    onSuccess: () => {
      setValue('');
      setDetail('');
      setNotice(null);
      void client.invalidateQueries({ queryKey: ['personal', key, userId] });
    },
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : 'Enregistrement impossible.'),
  });
  const toggle = useMutation<unknown, Error, { id: string; checked: boolean }>({
    mutationFn: ({ id, checked }: { id: string; checked: boolean }) => {
      if (section === 'tasks') return personalApi.updateTask(token!, id, checked);
      if (section === 'groceries') return personalApi.updateGrocery(token!, id, checked);
      return personalApi.updateTraining(token!, id, checked);
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ['personal', key, userId] }),
    onError: () => setNotice('La mise à jour n’a pas été enregistrée. Réessayez.'),
  });
  const plan = useMutation({
    mutationFn: () =>
      assistantApi.planMeals(token!, {
        grocery_items:
          groceries.data?.filter((item) => !item.checked).map((item) => item.label) ?? [],
      }),
    onSuccess: (result) => setMeals(result.meals),
    onError: () => setNotice('Le menu ne peut pas être proposé pour le moment.'),
  });
  const rows =
    section === 'tasks' ? tasks.data : section === 'groceries' ? groceries.data : trainings.data;
  const activeQuery = section === 'tasks' ? tasks : section === 'groceries' ? groceries : trainings;
  const completed = trainings.data?.filter((item) => item.completed).length ?? 0;
  const trainingTarget = profile.data?.weekly_training_target ?? 3;
  const weightLoss =
    profile.data?.weight_kg && profile.data.target_weight_kg
      ? profile.data.weight_kg - profile.data.target_weight_kg
      : null;
  const description =
    section === 'groceries'
      ? 'Ajouter à la liste'
      : section === 'health'
        ? 'Nom de la séance'
        : 'Nouvelle priorité';

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Tableau de bord</Text>
        </Pressable>
        <Text style={styles.kicker}>{kicker}</Text>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.intro}>{intro}</Text>
        {section === 'health' ? (
          <View style={styles.goal}>
            <Text style={styles.goalTitle}>Objectif personnel</Text>
            <Text style={styles.goalText}>
              {weightLoss && weightLoss > 0
                ? `Objectif : -${weightLoss.toFixed(1)} kg`
                : 'Ajoutez vos mesures et votre cible dans votre profil.'}
            </Text>
            <Pressable accessibilityRole="button" onPress={() => router.push('/profile')}>
              <Text style={styles.link}>Ouvrir mon profil →</Text>
            </Pressable>
          </View>
        ) : null}
        <View style={styles.form}>
          <Text style={styles.label}>{description}</Text>
          <TextInput
            accessibilityLabel={description}
            value={value}
            onChangeText={setValue}
            style={styles.input}
            placeholder={section === 'groceries' ? 'Ex. Lait' : 'Ex. Appeler le dentiste'}
            placeholderTextColor={colors.muted}
            onSubmitEditing={() => add.mutate()}
            returnKeyType="done"
          />
          {section === 'tasks' ? (
            <TextInput
              accessibilityLabel="Détail facultatif"
              value={detail}
              onChangeText={setDetail}
              style={styles.input}
              placeholder="Détail facultatif"
              placeholderTextColor={colors.muted}
            />
          ) : null}
          {section === 'health' ? (
            <>
              <View style={styles.choices}>
                {(Object.keys(trainingLabels) as (keyof typeof trainingLabels)[]).map((next) => (
                  <Pressable
                    key={next}
                    accessibilityRole="button"
                    onPress={() => setType(next)}
                    style={[styles.choice, type === next && styles.choiceActive]}
                  >
                    <Text style={[styles.choiceText, type === next && styles.choiceTextActive]}>
                      {trainingLabels[next]}
                    </Text>
                  </Pressable>
                ))}
              </View>
              <TextInput
                accessibilityLabel="Moment prévu"
                value={timing}
                onChangeText={setTiming}
                style={styles.input}
                placeholderTextColor={colors.muted}
              />
            </>
          ) : null}
          {notice ? (
            <Text accessibilityRole="alert" style={styles.error}>
              {notice}
            </Text>
          ) : null}
          <Pressable
            accessibilityRole="button"
            disabled={add.isPending}
            onPress={() => add.mutate()}
            style={[styles.primary, add.isPending && styles.disabled]}
          >
            {add.isPending ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <Text style={styles.primaryText}>Ajouter</Text>
            )}
          </Pressable>
        </View>
        {section === 'health' ? (
          <Text style={styles.progress}>
            {completed}/{trainingTarget} séances terminées cette semaine
          </Text>
        ) : null}
        {activeQuery.isError ? (
          <View accessibilityRole="alert" style={styles.apiError}>
            <Text style={styles.apiErrorText}>
              Cette version de l’API ne propose pas encore vos données personnelles. Redémarrez
              l’API Cocoon puis réessayez.
            </Text>
            <Pressable accessibilityRole="button" onPress={() => void activeQuery.refetch()}>
              <Text style={styles.link}>Réessayer</Text>
            </Pressable>
          </View>
        ) : null}
        {rows === undefined && !activeQuery.isError ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {rows?.length === 0 ? (
          <Text style={styles.empty}>Rien ici pour le moment. Ajoutez le premier élément.</Text>
        ) : null}
        <View style={styles.list}>
          {rows?.map((item) => {
            const checked = 'completed' in item ? item.completed : item.checked;
            const headline = 'title' in item ? item.title : item.label;
            const subtext =
              'detail' in item
                ? item.detail
                : 'timing' in item
                  ? `${trainingLabels[item.training_type]} · ${item.timing}`
                  : null;
            return (
              <Pressable
                key={item.id}
                accessibilityRole="checkbox"
                accessibilityState={{ checked, disabled: toggle.isPending }}
                disabled={toggle.isPending}
                onPress={() => toggle.mutate({ id: item.id, checked: !checked })}
                style={[styles.row, checked && styles.rowChecked]}
              >
                <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
                  <Text style={styles.checkmark}>{checked ? '✓' : ''}</Text>
                </View>
                <View style={styles.rowCopy}>
                  <Text style={[styles.rowTitle, checked && styles.strike]}>{headline}</Text>
                  {subtext ? (
                    <Text style={[styles.rowText, checked && styles.strike]}>{subtext}</Text>
                  ) : null}
                </View>
              </Pressable>
            );
          })}
        </View>
        {section === 'groceries' && groceries.data?.length ? (
          <Pressable
            accessibilityRole="button"
            disabled={plan.isPending}
            onPress={() => plan.mutate()}
            style={[styles.outline, plan.isPending && styles.disabled]}
          >
            <Text style={styles.outlineText}>
              {plan.isPending ? 'Préparation…' : 'Proposer des repas avec le reste'}
            </Text>
          </Pressable>
        ) : null}
        {meals ? (
          <View style={styles.goal}>
            {meals.map((meal) => (
              <View key={meal.day} style={styles.meal}>
                <Text style={styles.mealDay}>{meal.day}</Text>
                <Text style={styles.mealName}>{meal.name}</Text>
                <Text style={styles.rowText}>{meal.description}</Text>
              </View>
            ))}
          </View>
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
    backText: { color: theme.colors.spruce, fontWeight: '800' },
    kicker: {
      color: theme.colors.clay,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.4,
      marginTop: 14,
    },
    title: { color: theme.colors.ink, fontSize: 32, fontWeight: '700', marginTop: 7 },
    intro: { color: theme.colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
    form: {
      backgroundColor: theme.colors.white,
      borderColor: theme.colors.border,
      borderLeftColor: theme.colors.spruce,
      borderLeftWidth: 4,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      marginTop: 24,
      padding: 16,
    },
    label: { color: theme.colors.ink, fontSize: 14, fontWeight: '700' },
    input: {
      backgroundColor: theme.colors.linen,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.input,
      borderWidth: 1,
      color: theme.colors.ink,
      fontSize: 16,
      marginTop: 8,
      minHeight: 48,
      paddingHorizontal: 12,
    },
    primary: {
      alignItems: 'center',
      backgroundColor: theme.colors.spruce,
      borderRadius: theme.radius.button,
      justifyContent: 'center',
      marginTop: 12,
      minHeight: 48,
    },
    primaryText: { color: theme.colors.white, fontWeight: '800' },
    disabled: { opacity: 0.6 },
    error: { color: theme.colors.berry, marginTop: 10 },
    apiError: {
      backgroundColor: theme.colors.berrySoft,
      borderColor: theme.colors.berry,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      marginTop: 20,
      padding: 14,
    },
    apiErrorText: { color: theme.colors.ink, lineHeight: 20 },
    choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 12 },
    choice: {
      borderColor: theme.colors.border,
      borderRadius: 999,
      borderWidth: 1,
      minHeight: 36,
      paddingHorizontal: 10,
      justifyContent: 'center',
    },
    choiceActive: { backgroundColor: theme.colors.spruceSoft, borderColor: theme.colors.spruce },
    choiceText: { color: theme.colors.muted, fontSize: 12, fontWeight: '700' },
    choiceTextActive: { color: theme.colors.spruce },
    progress: { color: theme.colors.spruce, fontSize: 13, fontWeight: '800', marginTop: 18 },
    loader: { marginTop: 28 },
    empty: { color: theme.colors.muted, marginTop: 24, textAlign: 'center' },
    list: { marginTop: 14 },
    row: {
      alignItems: 'center',
      backgroundColor: theme.colors.white,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      flexDirection: 'row',
      marginTop: 9,
      minHeight: 62,
      padding: 12,
    },
    rowChecked: { backgroundColor: theme.colors.linenMuted },
    checkbox: {
      alignItems: 'center',
      borderColor: theme.colors.spruce,
      borderRadius: 10,
      borderWidth: 1.5,
      height: 25,
      justifyContent: 'center',
      marginRight: 12,
      width: 25,
    },
    checkboxChecked: { backgroundColor: theme.colors.spruce },
    checkmark: { color: theme.colors.white, fontWeight: '800' },
    rowCopy: { flex: 1 },
    rowTitle: { color: theme.colors.ink, fontSize: 15, fontWeight: '700' },
    rowText: { color: theme.colors.muted, fontSize: 13, lineHeight: 19, marginTop: 3 },
    strike: { color: theme.colors.muted, textDecorationLine: 'line-through' },
    outline: {
      alignItems: 'center',
      borderColor: theme.colors.spruce,
      borderRadius: theme.radius.button,
      borderWidth: 1,
      justifyContent: 'center',
      marginTop: 16,
      minHeight: 48,
    },
    outlineText: { color: theme.colors.spruce, fontWeight: '800' },
    goal: {
      backgroundColor: theme.colors.spruceSoft,
      borderColor: theme.colors.moss,
      borderRadius: theme.radius.card,
      borderWidth: 1,
      marginTop: 20,
      padding: 16,
    },
    goalTitle: { color: theme.colors.ink, fontSize: 16, fontWeight: '800' },
    goalText: { color: theme.colors.muted, lineHeight: 20, marginTop: 4 },
    link: { color: theme.colors.spruce, fontWeight: '800', marginTop: 10 },
    meal: { borderColor: theme.colors.moss, borderTopWidth: 1, marginTop: 10, paddingTop: 10 },
    mealDay: { color: theme.colors.clayInk, fontSize: 11, fontWeight: '800' },
    mealName: { color: theme.colors.ink, fontSize: 15, fontWeight: '800', marginTop: 3 },
  });
}
