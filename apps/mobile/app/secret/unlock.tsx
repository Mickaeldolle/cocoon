import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError, secretApi, type SecretAccess } from '@/src/services/api';
import {
  authenticateDevelopmentBiometric,
  hasDevelopmentBiometricCredential,
} from '@/src/services/development-biometric';
import {
  registerWebPasskey,
  unlockWithWebPasskey,
  webPasskeysSupported,
} from '@/src/services/web-passkeys';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useThemeStore } from '@/src/stores/theme-store';

export default function SecretUnlockScreen() {
  const accessToken = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id);
  const grant = useSecretAccessStore((state) => state.grant);
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [biometricReady, setBiometricReady] = useState(false);
  const [passkeyAvailable, setPasskeyAvailable] = useState(false);
  const [hasPasskey, setHasPasskey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [biometricHint, setBiometricHint] = useState<string | null>(null);
  const [usePassword, setUsePassword] = useState(!(__DEV__ && Platform.OS !== 'web'));
  const isDevelopmentNativeDevice = __DEV__ && Platform.OS !== 'web';
  const isWeb = Platform.OS === 'web';

  useEffect(() => {
    if (!isDevelopmentNativeDevice) return;
    let active = true;
    void hasDevelopmentBiometricCredential()
      .then((ready) => {
        if (active) {
          setBiometricReady(ready);
          if (!ready) setUsePassword(true);
        }
      })
      .catch((caught) => {
        if (!active) return;
        setBiometricHint(
          caught instanceof Error
            ? caught.message
            : 'La biométrie est indisponible. Utilisez votre mot de passe.',
        );
        setUsePassword(true);
      });
    return () => {
      active = false;
    };
  }, [isDevelopmentNativeDevice]);

  useEffect(() => {
    if (!isWeb || !accessToken || !webPasskeysSupported()) return;
    let active = true;
    void secretApi
      .passkeyStatus(accessToken)
      .then((status) => {
        if (!active) return;
        setPasskeyAvailable(status.available);
        setHasPasskey(status.has_passkeys);
        setUsePassword(!status.available || !status.has_passkeys);
      })
      .catch(() => {
        if (active) setUsePassword(true);
      });
    return () => {
      active = false;
    };
  }, [accessToken, isWeb]);

  async function unlock() {
    if (!accessToken || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const access = await secretApi.unlock(accessToken, password);
      grant(access);
      router.replace('/secret/conversations');
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Vérification impossible. Réessayez.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function unlockWithBiometrics() {
    if (!accessToken || !userId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const credential = await authenticateDevelopmentBiometric(accessToken, userId);
      let access: SecretAccess;
      try {
        access = await secretApi.unlockWithDevelopmentBiometric(accessToken, credential);
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.status !== 401) throw caught;
        await secretApi.enrollDevelopmentBiometric(accessToken, credential);
        access = await secretApi.unlockWithDevelopmentBiometric(accessToken, credential);
      }
      grant(access);
      router.replace('/secret/conversations');
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 404
          ? 'La biométrie n’est pas activée sur ce serveur. Utilisez votre mot de passe.'
          : caught instanceof Error
            ? caught.message
            : 'La vérification biométrique n’a pas été validée.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function unlockWithPasskey() {
    if (!accessToken || busy) return;
    setBusy(true);
    setError(null);
    try {
      const access = await unlockWithWebPasskey(accessToken);
      grant(access);
      router.replace('/secret/conversations');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Vérification par passkey impossible.');
    } finally {
      setBusy(false);
    }
  }

  async function createPasskey() {
    if (!accessToken || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const access = await registerWebPasskey(accessToken, password);
      setHasPasskey(true);
      grant(access);
      router.replace('/secret/conversations');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Création de la passkey impossible.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function revokePasskeys() {
    if (!accessToken || !password || busy || !isWeb) return;
    if (!window.confirm('Supprimer toutes les passkeys de ce compte ?')) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await secretApi.revokePasskeys(accessToken, password);
      setHasPasskey(false);
      setUsePassword(true);
      setNotice('Les passkeys de ce compte ont été supprimées.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Suppression des passkeys impossible.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.keyboard}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.card}>
            <Text style={styles.eyebrow}>VÉRIFICATION</Text>
            <Text style={styles.title}>Confirmez votre identité</Text>
            <Text style={styles.text}>
              L’accès est limité à cinq minutes et se reverrouille dès que Cocoon passe en
              arrière-plan.
            </Text>
            {biometricHint ? <Text style={styles.developmentHint}>{biometricHint}</Text> : null}
            {notice ? <Text style={styles.developmentHint}>{notice}</Text> : null}
            {usePassword ? (
              <>
                <Text style={styles.label}>Mot de passe du compte</Text>
                <TextInput
                  accessibilityLabel="Mot de passe du compte"
                  autoCapitalize="none"
                  autoComplete="current-password"
                  autoFocus
                  onChangeText={(value) => {
                    setPassword(value);
                    setError(null);
                  }}
                  onSubmitEditing={() => void unlock()}
                  placeholder="Votre mot de passe"
                  placeholderTextColor={colors.muted}
                  returnKeyType="done"
                  secureTextEntry
                  style={styles.input}
                  textContentType="password"
                  value={password}
                />
              </>
            ) : null}
            {error ? (
              <Text accessibilityRole="alert" style={styles.error}>
                {error}
              </Text>
            ) : null}
            {!usePassword && (isDevelopmentNativeDevice || (isWeb && hasPasskey)) ? (
              <Pressable
                accessibilityRole="button"
                disabled={(isDevelopmentNativeDevice && !biometricReady) || busy}
                onPress={() => void (isWeb ? unlockWithPasskey() : unlockWithBiometrics())}
                style={[
                  styles.primary,
                  ((isDevelopmentNativeDevice && !biometricReady) || busy) && styles.disabled,
                ]}
              >
                {busy ? (
                  <ActivityIndicator color={darkTheme.colors.ink} />
                ) : (
                  <Text style={styles.primaryText}>
                    {isWeb ? 'Déverrouiller avec une passkey' : 'Utiliser la biométrie'}
                  </Text>
                )}
              </Pressable>
            ) : (
              <Pressable
                accessibilityRole="button"
                disabled={!password || busy}
                onPress={() => void unlock()}
                style={[styles.primary, (!password || busy) && styles.disabled]}
              >
                {busy ? (
                  <ActivityIndicator color={darkTheme.colors.ink} />
                ) : (
                  <Text style={styles.primaryText}>Déverrouiller</Text>
                )}
              </Pressable>
            )}
            {(isDevelopmentNativeDevice && biometricReady) ||
            (isWeb && passkeyAvailable && hasPasskey) ? (
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={() => {
                  setUsePassword((value) => !value);
                  setError(null);
                }}
                style={styles.alternative}
              >
                <Text style={styles.alternativeText}>
                  {usePassword
                    ? isWeb
                      ? 'Utiliser ma passkey'
                      : 'Utiliser la biométrie'
                    : 'Utiliser mon mot de passe'}
                </Text>
              </Pressable>
            ) : null}
            {isWeb && passkeyAvailable && usePassword ? (
              <Pressable
                accessibilityRole="button"
                disabled={!password || busy}
                onPress={() => void createPasskey()}
                style={[styles.alternative, (!password || busy) && styles.disabled]}
              >
                <Text style={styles.alternativeText}>Créer une passkey avec ce mot de passe</Text>
              </Pressable>
            ) : null}
            {isWeb && hasPasskey && usePassword ? (
              <Pressable
                accessibilityRole="button"
                disabled={!password || busy}
                onPress={() => void revokePasskeys()}
                style={[styles.alternative, (!password || busy) && styles.disabled]}
              >
                <Text style={styles.alternativeText}>Supprimer mes passkeys</Text>
              </Pressable>
            ) : null}
            {isDevelopmentNativeDevice ? (
              <Text style={styles.developmentHint}>
                Développement : Cocoon associe cet appareil à votre compte après validation de Touch
                ID ou de l’empreinte. L’accès secret reste limité à cinq minutes.
              </Text>
            ) : null}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    keyboard: { flex: 1 },
    content: { flexGrow: 1, justifyContent: 'center', padding: darkTheme.spacing.screen },
    card: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: darkTheme.radius.card,
      borderWidth: 1,
      padding: 20,
    },
    eyebrow: { color: colors.clay, fontSize: 12, fontWeight: '800', letterSpacing: 1.2 },
    title: {
      color: colors.ink,
      fontSize: 26,
      fontWeight: '700',
      letterSpacing: -0.4,
      marginTop: 8,
    },
    text: { color: colors.muted, fontSize: 15, lineHeight: 22, marginTop: 10 },
    label: { color: colors.ink, fontSize: 14, fontWeight: '700', marginTop: 24 },
    input: {
      backgroundColor: colors.linen,
      borderColor: colors.border,
      borderRadius: darkTheme.radius.input,
      borderWidth: 1,
      color: colors.ink,
      fontSize: 16,
      marginTop: 7,
      minHeight: 50,
      paddingHorizontal: 12,
    },
    error: { color: colors.berry, lineHeight: 20, marginTop: 10 },
    primary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: darkTheme.radius.button,
      justifyContent: 'center',
      marginTop: 18,
      minHeight: 52,
    },
    primaryText: { color: darkTheme.colors.ink, fontSize: 16, fontWeight: '700' },
    alternative: { minHeight: 48, justifyContent: 'center', alignItems: 'center', marginTop: 8 },
    alternativeText: { color: colors.spruce, fontSize: 14, fontWeight: '600' },
    developmentHint: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: 14 },
    disabled: { opacity: 0.5 },
  });
}
