import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { Redirect, router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { useReducedMotion } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OrbBirth } from '@/features/assistant/orb-birth';
import { authApi } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';
import { darkTheme, lightTheme, subtleBackground, type ColorTokens } from '@/src/theme';

const introduction = "Bonjour et merci de m'avoir allumé ! Souhaites-tu me donner un nom ?";

function presentation(name: string, enabled: boolean) {
  let text = `${name}, j'adore ce nom ! Je serai ton assistant personnel.\n\nJe suis bien plus qu'un simple chatbot IA : je suis doté d'une mémoire, je peux apprendre à connaître tes habitudes et tes préférences, et t'aider dans tous tes projets.`;

  if (!enabled) {
    text += "\n\nTu n'as pas encore accès à la fonctionnalité d'assistant IA pour le moment.";
  }

  return text;
}

function concept(enabled: boolean) {
  return `Je suis encore en phase de développement, alors ne sois pas trop dur avec moi ! Pour l'instant, tu peux me parler de tout ce qui te passe par la tête. Cela m'aide à mieux te connaître et à te proposer des réponses plus pertinentes pour toi.\n\nJe suis capable de retenir certaines informations que tu me partages afin de pouvoir les utiliser plus tard lorsque cela peut t'être utile.`;
}

function firstStep(enabled: boolean) {
  return `Bientôt, si tu m'y autorises, je pourrai accéder à tes mails et à ton agenda pour t'aider à ne rien perdre de vue, préparer une liste de courses, te proposer des menus pour la semaine, construire un programme sportif adapté à tes objectifs, rechercher des offres d'emploi correspondant à ton profil... et bien d'autres choses encore !`;
}

export default function WelcomeScreen() {
  const initialized = useSessionStore((state) => state.initialized);
  const token = useSessionStore((state) => state.accessToken);
  const user = useSessionStore((state) => state.user);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const reducedMotion = useReducedMotion();
  const { width, height } = useWindowDimensions();
  const orbSize = Math.max(150, Math.min(width - 80, height * 0.32, 270));
  const [stepIndex, setStepIndex] = useState(0);
  const [visible, setVisible] = useState(0);
  const [hatched, setHatched] = useState(false);
  const [nameInput, setNameInput] = useState<string | null>(null);
  const [name, setName] = useState(user?.assistant_name ?? 'Cocoon');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chosenName = nameInput ?? user?.assistant_name ?? '';
  const finishBirth = useCallback(() => setHatched(true), []);

  const messages = [
    introduction,
    presentation(name, user?.enable_assistant === true),
    concept(user?.enable_assistant === true),
    firstStep(user?.enable_assistant === true),
  ];
  const message = messages[stepIndex] ?? messages[0];
  const isLastStep = stepIndex === messages.length - 1;
  function advance() {
    if (isLastStep) return;
    setVisible(0);
    setStepIndex((index) => index + 1);
  }
  useEffect(() => {
    if (!hatched || reducedMotion) return;
    let offset = 0;
    const interval = setInterval(() => {
      offset = Math.min(message.length, offset + 2);
      setVisible(offset);
      if (offset === message.length) clearInterval(interval);
    }, 32);
    return () => clearInterval(interval);
  }, [hatched, message, reducedMotion]);

  async function chooseName() {
    if (!token || busy) return;
    const normalized = chosenName.trim().replace(/\s+/g, ' ');
    if (normalized.length > 40) {
      setError('Le nom doit contenir 40 caractères au maximum.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await authApi.setAssistantName(token, normalized || null);
      if (useSessionStore.getState().accessToken !== token) return;
      useSessionStore.setState({ user: updated });
      setName(updated.assistant_name ?? 'Cocoon');
      advance();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible d’enregistrer le nom.');
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await authApi.completeWelcome(token);
      if (useSessionStore.getState().accessToken !== token) return;
      useSessionStore.setState({ user: updated });
      router.replace('/home');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible de terminer la présentation.');
    } finally {
      setBusy(false);
    }
  }

  if (!initialized) {
    return (
      <View style={[styles.screen, styles.loading]}>
        <ActivityIndicator color={colors.spruce} />
      </View>
    );
  }
  if (!token || !user) return <Redirect href="/sign-in" />;
  if (user.welcome_completed_at) return <Redirect href="/home" />;
  const shown = reducedMotion ? message.length : visible;
  const finishedMessage = hatched && shown >= message.length;
  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.fill}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {/* <Text style={styles.eyebrow}>BIENVENUE</Text> */}
          <View style={[styles.orbFrame, { width: orbSize, height: orbSize }]}>
            <OrbBirth size={orbSize} onComplete={finishBirth} />
          </View>
          <View style={styles.card}>
            <Text style={styles.speaker}>{stepIndex === 0 ? 'COCOON' : name.toUpperCase()}</Text>
            <Text
              accessible
              accessibilityLabel={finishedMessage ? message : 'Présentation en cours'}
              style={styles.message}
            >
              {message.slice(0, shown)}
              {!finishedMessage && hatched ? <Text style={styles.cursor}>▍</Text> : null}
            </Text>
          </View>
          {error ? (
            <Text accessibilityRole="alert" style={styles.error}>
              {error}
            </Text>
          ) : null}
          {stepIndex === 0 && finishedMessage ? (
            <View style={styles.actions}>
              <Text style={styles.label}>Nom de l’assistant · facultatif</Text>
              <TextInput
                accessibilityLabel="Nom de l’assistant"
                autoCapitalize="words"
                maxLength={40}
                onChangeText={setNameInput}
                placeholder="Cocoon"
                placeholderTextColor={colors.muted}
                returnKeyType="done"
                style={styles.input}
                value={chosenName}
              />
              <Pressable
                auditAction="welcome.name.continue"
                accessibilityRole="button"
                disabled={busy}
                onPress={() => void chooseName()}
                style={styles.primary}
              >
                <Text style={styles.primaryText}>
                  {busy
                    ? 'Enregistrement…'
                    : chosenName.trim()
                      ? 'Continuer avec ce nom'
                      : 'Continuer avec Cocoon'}
                </Text>
              </Pressable>
            </View>
          ) : null}
          {stepIndex > 0 && finishedMessage ? (
            <Pressable
              auditAction={isLastStep ? 'welcome.complete' : 'welcome.continue'}
              accessibilityRole="button"
              disabled={isLastStep && busy}
              onPress={isLastStep ? () => void finish() : advance}
              style={[styles.primary, styles.finish]}
            >
              <Text style={styles.primaryText}>
                {isLastStep ? (busy ? 'Ouverture…' : 'Commencer') : 'Continuer'}
              </Text>
            </Pressable>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { flex: 1, ...subtleBackground(colors) },
    fill: { flex: 1 },
    loading: { alignItems: 'center', justifyContent: 'center' },
    content: {
      alignItems: 'center',
      flexGrow: 1,
      justifyContent: 'center',
      padding: 24,
      paddingBottom: 40,
    },
    eyebrow: {
      color: colors.clay,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.8,
      marginBottom: 8,
    },
    orbFrame: { alignItems: 'center', justifyContent: 'center', marginVertical: 8 },
    card: {
      alignSelf: 'stretch',
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 24,
      borderWidth: 1,
      minHeight: 170,
      padding: 22,
    },
    speaker: {
      color: colors.spruce,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.3,
      marginBottom: 12,
    },
    message: { color: colors.ink, fontSize: 17, lineHeight: 26 },
    cursor: { color: colors.spruce },
    actions: { alignSelf: 'stretch', marginTop: 22 },
    label: { color: colors.muted, fontSize: 13, fontWeight: '700', marginBottom: 8 },
    input: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 14,
      borderWidth: 1,
      color: colors.ink,
      fontSize: 17,
      minHeight: 52,
      paddingHorizontal: 16,
    },
    primary: {
      alignItems: 'center',
      alignSelf: 'stretch',
      backgroundColor: colors.spruce,
      borderRadius: 16,
      justifyContent: 'center',
      minHeight: 52,
      marginTop: 14,
      paddingHorizontal: 16,
    },
    primaryText: { color: colors.spruceOn, fontSize: 15, fontWeight: '800', textAlign: 'center' },
    finish: { marginTop: 24 },
    error: { alignSelf: 'stretch', color: colors.berry, marginTop: 12 },
  });
}
