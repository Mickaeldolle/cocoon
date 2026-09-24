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

export default function SignInScreen() {
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = useSessionStore((state) => state.start);

  async function signIn({ email, password }: Credentials) {
    setBusy(true);
    setError(null);
    try {
      const tokens = await authApi.login({ ...(await getDevice()), email, password });
      await start(tokens);
      router.replace('/home');
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Connexion impossible. Réessayez.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.content}>
        <Text style={styles.kicker}>COCOON</Text>
        <Text style={styles.title}>Retrouvez votre famille, simplement.</Text>
        <Text style={styles.description}>Connectez-vous pour accéder à vos espaces privés.</Text>
        <AuthForm actionLabel="Se connecter" busy={busy} error={error} onSubmit={signIn} />
        <Link href="/register" style={styles.link}>
          Créer mon compte
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
      fontSize: 34,
      fontWeight: '700',
      letterSpacing: -0.8,
      lineHeight: 40,
      marginTop: 12,
    },
    description: {
      color: theme.colors.muted,
      fontSize: 16,
      lineHeight: 24,
      marginBottom: 24,
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
