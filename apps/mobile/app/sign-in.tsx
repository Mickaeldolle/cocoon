import { Link, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AuthForm, type Credentials } from '@/features/auth/auth-form';
import { authApi, ApiError, clearRefreshToken, loadRefreshToken } from '@/src/services/api';
import {
  authenticateAndroidBiometricLogin,
  disableAndroidBiometricLogin,
  isAndroidBiometricLoginEnabled,
} from '@/src/services/android-biometric-login';
import { getDevice } from '@/src/services/device';
import { loginWithWebPasskey, webPasskeysSupported } from '@/src/services/web-passkeys';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

export default function SignInScreen() {
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [biometricEnabled, setBiometricEnabled] = useState(false);
  const start = useSessionStore((state) => state.start);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    let active = true;
    void isAndroidBiometricLoginEnabled()
      .then((enabled) => {
        if (active) setBiometricEnabled(enabled);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

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

  async function signInWithPasskey(email: string) {
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError('Saisissez votre adresse email avant d’utiliser une passkey.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const tokens = await loginWithWebPasskey(email.trim());
      await start(tokens);
      router.replace('/home');
    } catch (caught) {
      console.error(caught);
      setError(caught instanceof Error ? caught.message : 'Connexion par passkey impossible.');
    } finally {
      setBusy(false);
    }
  }

  async function signInWithBiometrics() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await authenticateAndroidBiometricLogin();
      const refreshToken = await loadRefreshToken();
      if (!refreshToken) {
        await disableAndroidBiometricLogin();
        setBiometricEnabled(false);
        throw new Error('Aucune session conservée. Connectez-vous avec votre mot de passe.');
      }
      let tokens;
      try {
        tokens = await authApi.refresh(refreshToken);
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          await Promise.allSettled([clearRefreshToken(), disableAndroidBiometricLogin()]);
          setBiometricEnabled(false);
          throw new Error('Votre session a expiré. Connectez-vous avec votre mot de passe.');
        }
        throw caught;
      }
      await start(tokens);
      router.replace('/home');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Connexion biométrique impossible.');
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
        <AuthForm
          actionLabel="Se connecter"
          busy={busy}
          error={error}
          onSubmit={signIn}
          onPasskey={Platform.OS === 'web' ? signInWithPasskey : undefined}
          passkeyAvailable={webPasskeysSupported()}
          onBiometric={biometricEnabled ? signInWithBiometrics : undefined}
        />
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
