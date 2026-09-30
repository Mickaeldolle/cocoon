import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
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
import { secretBiometricMode } from '@/src/services/secret-biometric-mode';
import {
  enrollAndroidSecretBiometric,
  hasAndroidSecretBiometric,
  unlockWithAndroidSecretBiometric,
} from '@/src/services/android-secret-biometric';
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
import { darkTheme, lightTheme, subtleBackground, type ColorTokens } from '@/src/theme';
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
  const [passkeyHint, setPasskeyHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [biometricHint, setBiometricHint] = useState<string | null>(null);
  const [usePassword, setUsePassword] = useState(
    secretBiometricMode(Platform.OS, __DEV__) === 'none' &&
      !(Platform.OS === 'web' && webPasskeysSupported()),
  );
  const biometricMode = secretBiometricMode(Platform.OS, __DEV__);
  const isDevelopmentNativeDevice = biometricMode === 'development';
  const isInstalledAndroid = biometricMode === 'android';
  const isWeb = Platform.OS === 'web';
  const passkeySupported = isWeb && webPasskeysSupported();

  const completeUnlock = useCallback(
    async (access: SecretAccess) => {
      if (!accessToken || useSessionStore.getState().accessToken !== accessToken) return;
      grant(access);
      try {
        const conversations = await secretApi.listConversations(
          accessToken,
          access.secret_access_token,
        );
        if (
          useSessionStore.getState().accessToken !== accessToken ||
          useSecretAccessStore.getState().token !== access.secret_access_token
        )
          return;
        if (!conversations.some((conversation) => conversation.membership_status === 'pending')) {
          const joined = conversations.find(
            (conversation) => conversation.membership_status === 'accepted',
          );
          if (joined) {
            router.replace({ pathname: '/secret/conversation/[id]', params: { id: joined.id } });
            return;
          }
        }
      } catch {
        // The list screen displays the server error and keeps access guarded.
      }
      if (
        useSessionStore.getState().accessToken !== accessToken ||
        useSecretAccessStore.getState().token !== access.secret_access_token
      )
        return;
      router.replace('/secret/conversations');
    },
    [accessToken, grant],
  );

  const performDevelopmentBiometricUnlock = useCallback(
    async (isActive: () => boolean = () => true) => {
      if (!accessToken || !userId) return;
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
        if (isActive()) await completeUnlock(access);
      } catch (caught) {
        if (!isActive()) return;
        setUsePassword(true);
        setError(
          caught instanceof ApiError && caught.status === 404
            ? 'La biométrie n’est pas activée sur ce serveur. Utilisez votre mot de passe.'
            : caught instanceof Error
              ? caught.message
              : 'La vérification biométrique n’a pas été validée.',
        );
      } finally {
        if (isActive()) setBusy(false);
      }
    },
    [accessToken, userId, completeUnlock],
  );

  useEffect(() => {
    if (!isInstalledAndroid || !accessToken || !userId) return;
    let active = true;
    void hasAndroidSecretBiometric(userId)
      .then(async (ready) => {
        if (!active) return;
        setBiometricReady(ready);
        if (!ready) {
          setUsePassword(true);
          return;
        }
        setBusy(true);
        try {
          const access = await unlockWithAndroidSecretBiometric(accessToken, userId);
          if (active) await completeUnlock(access);
        } catch (caught) {
          if (active) {
            setUsePassword(true);
            setError(caught instanceof Error ? caught.message : 'Biométrie indisponible.');
          }
        } finally {
          if (active) setBusy(false);
        }
      })
      .catch(() => {
        if (active) setUsePassword(true);
      });
    return () => {
      active = false;
    };
  }, [accessToken, completeUnlock, isInstalledAndroid, userId]);

  useEffect(() => {
    if (!isDevelopmentNativeDevice) return;
    let active = true;
    void hasDevelopmentBiometricCredential()
      .then((ready) => {
        if (active) {
          setBiometricReady(ready);
          if (!ready) setUsePassword(true);
          else void performDevelopmentBiometricUnlock(() => active);
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
  }, [isDevelopmentNativeDevice, performDevelopmentBiometricUnlock]);

  useEffect(() => {
    if (!passkeySupported || !accessToken) return;
    let active = true;
    void secretApi
      .passkeyStatus(accessToken)
      .then(async (status) => {
        if (!active) return;
        setPasskeyAvailable(status.available);
        setHasPasskey(status.has_passkeys);
        setUsePassword(!status.available || !status.has_passkeys);
        setPasskeyHint(status.available ? null : 'Les passkeys ne sont pas configurées sur l’API.');
        if (status.available && status.has_passkeys) {
          setBusy(true);
          try {
            const access = await unlockWithWebPasskey(accessToken);
            if (active) await completeUnlock(access);
          } catch (caught) {
            if (active) {
              setUsePassword(true);
              setError(
                caught instanceof Error ? caught.message : 'Vérification par passkey impossible.',
              );
            }
          } finally {
            if (active) setBusy(false);
          }
        }
      })
      .catch(() => {
        if (active) {
          setUsePassword(true);
          setPasskeyHint('Impossible de vérifier la disponibilité des passkeys.');
        }
      });
    return () => {
      active = false;
    };
  }, [accessToken, passkeySupported, completeUnlock]);

  async function unlock() {
    if (!accessToken || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const access = await secretApi.unlock(accessToken, password);
      if (isInstalledAndroid && userId) {
        try {
          if (!(await hasAndroidSecretBiometric(userId))) {
            await enrollAndroidSecretBiometric(accessToken, userId, password);
          }
        } catch {
          // The password unlock remains valid if device enrollment is unavailable.
        }
      }
      await completeUnlock(access);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Vérification impossible. Réessayez.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function unlockWithAndroidBiometrics() {
    if (!accessToken || !userId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const access = await unlockWithAndroidSecretBiometric(accessToken, userId);
      await completeUnlock(access);
    } catch (caught) {
      setUsePassword(true);
      setError(caught instanceof Error ? caught.message : 'Vérification biométrique impossible.');
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
      await completeUnlock(access);
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
      await completeUnlock(access);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Création de la passkey impossible.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function revokePasskeys() {
    if (!accessToken || !password || busy || !isWeb) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await secretApi.revokePasskeys(accessToken, password);
      setHasPasskey(false);
      setUsePassword(true);
      setConfirmRevoke(false);
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
            {isWeb && !passkeySupported ? (
              <Text style={styles.developmentHint}>
                Les passkeys nécessitent un navigateur compatible sur une page HTTPS.
              </Text>
            ) : null}
            {passkeyHint ? <Text style={styles.developmentHint}>{passkeyHint}</Text> : null}
            {notice ? <Text style={styles.developmentHint}>{notice}</Text> : null}
            {usePassword ? (
              <>
                <Text style={styles.label}>Mot de passe du compte</Text>
                <TextInput
                  accessibilityLabel="Mot de passe du compte"
                  autoCapitalize="none"
                  autoComplete="current-password"
                  autoFocus={usePassword}
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
            {!usePassword &&
            (isInstalledAndroid || isDevelopmentNativeDevice || (isWeb && hasPasskey)) ? (
              <Pressable
                accessibilityRole="button"
                disabled={
                  ((isInstalledAndroid || isDevelopmentNativeDevice) && !biometricReady) || busy
                }
                onPress={() => {
                  if (isWeb) void unlockWithPasskey();
                  else if (isInstalledAndroid) void unlockWithAndroidBiometrics();
                  else if (!busy) void performDevelopmentBiometricUnlock();
                }}
                style={[
                  styles.primary,
                  (((isInstalledAndroid || isDevelopmentNativeDevice) && !biometricReady) ||
                    busy) &&
                    styles.disabled,
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
            {((isInstalledAndroid || isDevelopmentNativeDevice) && biometricReady) ||
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
              confirmRevoke ? (
                <View>
                  <Text style={styles.developmentHint}>
                    Supprimer toutes les passkeys de ce compte ?
                  </Text>
                  <Pressable
                    accessibilityRole="button"
                    disabled={!password || busy}
                    onPress={() => void revokePasskeys()}
                    style={[styles.alternative, (!password || busy) && styles.disabled]}
                  >
                    <Text style={styles.alternativeText}>Confirmer la suppression</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => setConfirmRevoke(false)}
                    style={styles.alternative}
                  >
                    <Text style={styles.alternativeText}>Annuler</Text>
                  </Pressable>
                </View>
              ) : (
                <Pressable
                  accessibilityRole="button"
                  disabled={!password || busy}
                  onPress={() => setConfirmRevoke(true)}
                  style={[styles.alternative, (!password || busy) && styles.disabled]}
                >
                  <Text style={styles.alternativeText}>Supprimer mes passkeys</Text>
                </Pressable>
              )
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
    screen: { ...subtleBackground(colors), flex: 1 },
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
