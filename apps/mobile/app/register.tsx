import { Link, router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AuthForm, type Credentials } from '@/features/auth/auth-form';
import { authApi, ApiError } from '@/src/services/api';
import { getDevice } from '@/src/services/device';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

export default function RegisterScreen() {
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = useSessionStore((state) => state.start);

  async function register({ email, password, display_name }: Credentials) {
    const displayName = display_name?.trim();
    if (!displayName) {
      setError('Indiquez le nom sous lequel votre famille vous reconnaît.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const tokens = await authApi.register({
        ...(await getDevice()),
        email,
        password,
        display_name: displayName,
      });
      await start(tokens);
      router.replace('/home');
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'Création du compte impossible. Réessayez.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.content}>
        <Text style={styles.kicker}>BIENVENUE</Text>
        <Text style={styles.title}>Créez votre cocon familial.</Text>
        <Text style={styles.description}>
          Utilisez un mot de passe long. Il restera uniquement sur cet appareil via votre
          gestionnaire de mots de passe.
        </Text>
        <AuthForm
          actionLabel="Créer mon compte"
          busy={busy}
          error={error}
          showDisplayName
          onSubmit={register}
        />
        <Link href="/sign-in" style={styles.link}>
          J’ai déjà un compte
        </Link>
      </View>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  const theme = { ...darkTheme, colors };
  return StyleSheet.create({
    screen: { backgroundColor: theme.colors.linen, flex: 1 },
    content: { flex: 1, justifyContent: 'center', padding: theme.spacing.screen },
    kicker: { color: theme.colors.clay, fontSize: 13, fontWeight: '800', letterSpacing: 2 },
    title: {
      color: theme.colors.ink,
      fontSize: 32,
      fontWeight: '700',
      letterSpacing: -0.8,
      lineHeight: 38,
      marginTop: 12,
    },
    description: {
      color: theme.colors.muted,
      fontSize: 16,
      lineHeight: 23,
      marginBottom: 16,
      marginTop: 12,
    },
    link: {
      color: theme.colors.spruce,
      fontSize: 16,
      fontWeight: '700',
      marginTop: 24,
      textAlign: 'center',
    },
  });
}
