import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  ApiError,
  authApi,
  personalApi,
  secretApi,
  loadRefreshToken,
  type Device,
  type Profile,
} from '@/src/services/api';
import { registerWebPasskey, webPasskeysSupported } from '@/src/services/web-passkeys';
import {
  canUseAndroidBiometrics,
  disableAndroidBiometricLogin,
  enableAndroidBiometricLogin,
  isAndroidBiometricLoginEnabled,
} from '@/src/services/android-biometric-login';
import { darkTheme, lightTheme, type ColorTokens } from '@/src/theme';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';

export default function ProfileScreen() {
  const token = useSessionStore((state) => state.accessToken);
  const user = useSessionStore((state) => state.user);
  const endSession = useSessionStore((state) => state.end);
  const mode = useThemeStore((state) => state.mode);
  const setMode = useThemeStore((state) => state.setMode);
  const client = useQueryClient();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const styles = makeStyles(colors);
  const profile = useQuery({
    queryKey: ['personal', 'profile', user?.id],
    enabled: Boolean(token),
    queryFn: () => personalApi.getProfile(token!),
    retry: false,
  });
  const devices = useQuery({
    queryKey: ['auth', 'devices', user?.id],
    enabled: Boolean(token),
    queryFn: () => authApi.listDevices(token!),
    retry: false,
  });
  const fallback: Profile | null = user
    ? {
        display_name: user.display_name,
        email: user.email,
        birth_date: null,
        height_cm: null,
        weight_kg: null,
        target_weight_kg: null,
        weekly_training_target: 3,
      }
    : null;
  const isStaleApi = profile.error instanceof ApiError && profile.error.status === 404;
  async function signOut() {
    if (isSigningOut) return;
    setIsSigningOut(true);
    try {
      await endSession();
    } finally {
      client.clear();
      router.replace('/sign-in');
      setIsSigningOut(false);
    }
  }
  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Pressable
          auditAction="profile.back"
          accessibilityRole="button"
          onPress={() => router.back()}
          style={styles.back}
        >
          <Text style={styles.backText}>‹ Accueil</Text>
        </Pressable>
        <Text style={styles.kicker}>MON ESPACE</Text>
        <Text style={styles.title}>Profil</Text>
        <Text style={styles.intro}>
          Vos mesures restent privées. Elles servent uniquement à votre suivi personnel.
        </Text>
        <View style={styles.themeCard}>
          <Text style={styles.themeTitle}>Apparence</Text>
          <View style={styles.themeSwitch}>
            {(['dark', 'light'] as const).map((candidate) => (
              <Pressable
                auditAction="profile.theme.select"
                key={candidate}
                accessibilityRole="button"
                accessibilityState={{ selected: mode === candidate }}
                onPress={() => void setMode(candidate)}
                style={[styles.themeOption, mode === candidate && styles.themeOptionActive]}
              >
                <Text
                  style={[
                    styles.themeOptionText,
                    mode === candidate && styles.themeOptionTextActive,
                  ]}
                >
                  {candidate === 'dark' ? 'Sombre' : 'Clair'}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
        <DeviceManager token={token!} devices={devices.data ?? []} styles={styles} />
        {Platform.OS === 'web' && token ? (
          <PasskeyManager token={token} userId={user!.id} styles={styles} colors={colors} />
        ) : null}
        {Platform.OS === 'android' && token ? (
          <AndroidBiometricSettings styles={styles} colors={colors} />
        ) : null}
        <Pressable
          auditAction="profile.memory.open"
          accessibilityRole="button"
          onPress={() => router.push('/memory' as never)}
          style={styles.memoryButton}
        >
          <Text style={styles.memoryButtonTitle}>Gérer ma mémoire</Text>
          <Text style={styles.memoryButtonText}>
            Voir, corriger ou oublier ce que Cocoon retient.
          </Text>
        </Pressable>
        <Pressable
          auditAction="profile.projects.open"
          accessibilityRole="button"
          onPress={() => router.push('/projects' as never)}
          style={styles.memoryButton}
        >
          <Text style={styles.memoryButtonTitle}>Gérer mes projets</Text>
          <Text style={styles.memoryButtonText}>
            Ajouter un projet et préciser le contexte que Cocoon peut retenir.
          </Text>
        </Pressable>
        {profile.isPending ? (
          <ActivityIndicator color={colors.spruce} style={styles.loader} />
        ) : null}
        {profile.error ? (
          <View accessibilityRole="alert" style={styles.alert}>
            <Text style={styles.alertTitle}>
              {isStaleApi
                ? 'L’API Cocoon doit être redémarrée.'
                : 'Le profil ne peut pas être chargé.'}
            </Text>
            <Text style={styles.alertText}>
              {isStaleApi
                ? 'La version en cours ne propose pas encore les routes du profil. Redémarrez l’API puis réessayez.'
                : 'Vos champs restent visibles. Réessayez après avoir vérifié votre connexion.'}
            </Text>
            <Pressable
              auditAction="profile.retry"
              accessibilityRole="button"
              onPress={() => void profile.refetch()}
              style={styles.retry}
            >
              <Text style={styles.retryText}>Réessayer</Text>
            </Pressable>
          </View>
        ) : null}
        {profile.data || fallback ? (
          <ProfileEditor
            profile={profile.data ?? fallback!}
            token={token!}
            styles={styles}
            colors={colors}
          />
        ) : null}
        <Pressable
          auditAction="profile.logout"
          accessibilityRole="button"
          accessibilityLabel="Se déconnecter de Cocoon"
          disabled={isSigningOut}
          onPress={() => void signOut()}
          style={[styles.signOut, isSigningOut && styles.disabled]}
        >
          {isSigningOut ? (
            <ActivityIndicator color={colors.berry} />
          ) : (
            <Text style={styles.signOutText}>Se déconnecter</Text>
          )}
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

function AndroidBiometricSettings({
  styles,
  colors,
}: {
  styles: ReturnType<typeof makeStyles>;
  colors: ColorTokens;
}) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([isAndroidBiometricLoginEnabled(), canUseAndroidBiometrics()])
      .then(([saved, supported]) => {
        if (active) {
          setEnabled(saved);
          setAvailable(supported);
        }
      })
      .catch(() => {
        if (active) {
          setEnabled(false);
          setError('Impossible de vérifier la biométrie de ce téléphone.');
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function changeSetting() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (enabled) {
        await disableAndroidBiometricLogin();
        setEnabled(false);
        setNotice('La session se rouvrira sans empreinte au prochain démarrage.');
      } else {
        if (!(await loadRefreshToken())) {
          throw new Error('Reconnectez-vous avec votre mot de passe avant d’activer l’empreinte.');
        }
        await enableAndroidBiometricLogin();
        setEnabled(true);
        setNotice('L’empreinte sera demandée au prochain démarrage de Cocoon.');
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Modification impossible.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.devicesCard}>
      <Text style={styles.devicesTitle}>Ouverture par empreinte</Text>
      <Text style={styles.devicesIntro}>
        Après une première connexion, rouvrez votre session sur ce téléphone avec l’empreinte.
      </Text>
      {enabled === null ? (
        <ActivityIndicator color={colors.spruce} style={styles.loader} />
      ) : !available && !enabled ? (
        <Text style={styles.help}>
          Configurez une empreinte ou une biométrie forte dans les réglages Android.
        </Text>
      ) : (
        <>
          {!available ? (
            <Text style={styles.help}>
              La biométrie configurée n’est plus disponible. Vous pouvez la désactiver ici.
            </Text>
          ) : null}
          <Pressable
            auditAction="profile.biometric.toggle"
            accessibilityRole="button"
            accessibilityState={{ selected: enabled }}
            disabled={busy}
            onPress={() => void changeSetting()}
            style={[styles.primary, busy && styles.disabled]}
          >
            <Text style={styles.primaryText}>
              {enabled
                ? 'Désactiver l’ouverture par empreinte'
                : 'Activer l’ouverture par empreinte'}
            </Text>
          </Pressable>
        </>
      )}
      {notice ? (
        <Text accessibilityRole="alert" style={styles.help}>
          {notice}
        </Text>
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function PasskeyManager({
  token,
  userId,
  styles,
  colors,
}: {
  token: string;
  userId: string;
  styles: ReturnType<typeof makeStyles>;
  colors: ColorTokens;
}) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const supported = webPasskeysSupported();
  const status = useQuery({
    queryKey: ['auth', 'passkeys', userId],
    queryFn: () => secretApi.passkeyStatus(token),
    enabled: supported,
    retry: false,
  });

  async function createPasskey() {
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await registerWebPasskey(token, password);
      setNotice('Passkey créée. Vous pouvez maintenant l’utiliser pour vous connecter.');
      void status.refetch();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Création de la passkey impossible.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function revokePasskeys() {
    if (!password || busy || !window.confirm('Supprimer toutes les passkeys de ce compte ?'))
      return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await secretApi.revokePasskeys(token, password);
      setNotice('Passkeys supprimées. La connexion par mot de passe reste disponible.');
      void status.refetch();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Suppression des passkeys impossible.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  return (
    <View style={styles.devicesCard}>
      <Text style={styles.devicesTitle}>Passkeys</Text>
      <Text style={styles.devicesIntro}>
        Créez une passkey pour vous connecter sur le web et déverrouiller l’espace protégé.
      </Text>
      {!supported ? (
        <Text style={styles.help}>Utilisez un navigateur compatible sur une page HTTPS.</Text>
      ) : status.isPending ? (
        <ActivityIndicator color={colors.spruce} style={styles.loader} />
      ) : status.isError ? (
        <>
          <Text accessibilityRole="alert" style={styles.error}>
            État des passkeys indisponible. Vérifiez la connexion.
          </Text>
          <Pressable
            auditAction="profile.passkey.retry"
            accessibilityRole="button"
            onPress={() => void status.refetch()}
            style={styles.retry}
          >
            <Text style={styles.retryText}>Réessayer</Text>
          </Pressable>
        </>
      ) : !status.data?.available ? (
        <Text style={styles.help}>
          Les passkeys ne sont pas configurées sur l’API. Définissez WEBAUTHN_ORIGIN pour ce site.
        </Text>
      ) : (
        <>
          <Text style={styles.help}>
            {status.data.has_passkeys
              ? 'Une passkey est enregistrée pour ce compte.'
              : 'Aucune passkey enregistrée. Confirmez votre mot de passe pour en créer une.'}
          </Text>
          <Text style={styles.label}>Mot de passe du compte</Text>
          <TextInput
            accessibilityLabel="Mot de passe du compte pour gérer les passkeys"
            autoComplete="current-password"
            onChangeText={setPassword}
            secureTextEntry
            style={styles.input}
            value={password}
          />
          <Pressable
            auditAction="profile.passkey.create"
            accessibilityRole="button"
            disabled={!password || busy}
            onPress={() => void createPasskey()}
            style={[styles.primary, (!password || busy) && styles.disabled]}
          >
            <Text style={styles.primaryText}>Créer une passkey</Text>
          </Pressable>
          {status.data.has_passkeys ? (
            <Pressable
              auditAction="profile.passkey.revoke"
              accessibilityRole="button"
              disabled={!password || busy}
              onPress={() => void revokePasskeys()}
              style={[styles.signOut, (!password || busy) && styles.disabled]}
            >
              <Text style={styles.signOutText}>Supprimer mes passkeys</Text>
            </Pressable>
          ) : null}
        </>
      )}
      {notice ? (
        <Text accessibilityRole="alert" style={styles.help}>
          {notice}
        </Text>
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function DeviceManager({
  token,
  devices,
  styles,
}: {
  token: string;
  devices: Device[];
  styles: ReturnType<typeof makeStyles>;
}) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const revoke = useMutation({
    mutationFn: (deviceId: string) => authApi.revokeDevice(token, deviceId),
    onSuccess: () => {
      setError(null);
      void client.invalidateQueries({ queryKey: ['auth', 'devices'] });
    },
    onError: () => setError('Cet appareil ne peut pas être révoqué pour le moment.'),
  });
  return (
    <View style={styles.devicesCard}>
      <Text style={styles.devicesTitle}>Appareils connectés</Text>
      <Text style={styles.devicesIntro}>
        Révoquez une ancienne session pour empêcher cet appareil d’accéder à votre compte.
      </Text>
      {devices.map((device) => (
        <View key={device.id} style={styles.deviceRow}>
          <View style={styles.deviceCopy}>
            <Text style={styles.deviceName}>{device.name}</Text>
            <Text style={styles.deviceMeta}>
              {device.platform} · {device.current ? 'appareil actuel' : 'session distante'}
            </Text>
          </View>
          {!device.current ? (
            <Pressable
              auditAction="profile.device.revoke"
              accessibilityRole="button"
              accessibilityLabel={`Révoquer ${device.name}`}
              disabled={revoke.isPending}
              onPress={() => revoke.mutate(device.id)}
              style={[styles.revoke, revoke.isPending && styles.disabled]}
            >
              <Text style={styles.revokeText}>Révoquer</Text>
            </Pressable>
          ) : null}
        </View>
      ))}
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function ProfileEditor({
  profile,
  token,
  styles,
  colors,
}: {
  profile: Profile;
  token: string;
  styles: ReturnType<typeof makeStyles>;
  colors: ColorTokens;
}) {
  const client = useQueryClient();
  const [name, setName] = useState(profile.display_name);
  const [birthDate, setBirthDate] = useState(profile.birth_date ?? '');
  const [height, setHeight] = useState(profile.height_cm?.toString() ?? '');
  const [weight, setWeight] = useState(profile.weight_kg?.toString() ?? '');
  const [target, setTarget] = useState(profile.target_weight_kg?.toString() ?? '');
  const [weeklyTarget, setWeeklyTarget] = useState(profile.weekly_training_target.toString());
  const [error, setError] = useState<string | null>(null);
  const parse = (value: string) => (value.trim() ? Number(value.replace(',', '.')) : null);
  const save = useMutation({
    mutationFn: () =>
      personalApi.updateProfile(token, {
        display_name: name.trim(),
        email: profile.email,
        birth_date: birthDate.trim() || null,
        height_cm: parse(height),
        weight_kg: parse(weight),
        target_weight_kg: parse(target),
        weekly_training_target: Number(weeklyTarget),
      }),
    onSuccess: () => {
      setError(null);
      void client.invalidateQueries({ queryKey: ['personal', 'profile'] });
    },
    onError: () =>
      setError('Le profil ne peut pas être enregistré tant que l’API n’est pas à jour.'),
  });
  return (
    <View style={styles.form}>
      <Field
        label="Nom affiché"
        value={name}
        onChangeText={setName}
        styles={styles}
        colors={colors}
      />
      <Text style={styles.label}>Adresse email</Text>
      <Text style={styles.readonly}>{profile.email}</Text>
      <Field
        label="Date de naissance (facultatif)"
        value={birthDate}
        onChangeText={setBirthDate}
        placeholder="AAAA-MM-JJ"
        keyboardType="numbers-and-punctuation"
        styles={styles}
        colors={colors}
      />
      <Field
        label="Taille (cm)"
        value={height}
        onChangeText={setHeight}
        placeholder="Ex. 172"
        keyboardType="decimal-pad"
        styles={styles}
        colors={colors}
      />
      <Field
        label="Poids actuel (kg)"
        value={weight}
        onChangeText={setWeight}
        placeholder="Ex. 68,5"
        keyboardType="decimal-pad"
        styles={styles}
        colors={colors}
      />
      <Field
        label="Objectif de poids (kg)"
        value={target}
        onChangeText={setTarget}
        placeholder="Ex. 64"
        keyboardType="decimal-pad"
        styles={styles}
        colors={colors}
      />
      <Field
        label="Séances par semaine"
        value={weeklyTarget}
        onChangeText={setWeeklyTarget}
        placeholder="Ex. 3"
        keyboardType="decimal-pad"
        styles={styles}
        colors={colors}
      />
      <Text style={styles.help}>
        Cocoon ne fournit pas de conseil médical. Vous pouvez modifier ou retirer ces valeurs à tout
        moment.
      </Text>
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
      <Pressable
        auditAction="profile.save"
        accessibilityRole="button"
        disabled={save.isPending}
        onPress={() => save.mutate()}
        style={[styles.primary, save.isPending && styles.disabled]}
      >
        {save.isPending ? (
          <ActivityIndicator color={colors.white} />
        ) : (
          <Text style={styles.primaryText}>Enregistrer le profil</Text>
        )}
      </Pressable>
    </View>
  );
}

function Field(props: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  keyboardType?: 'decimal-pad' | 'numbers-and-punctuation';
  styles: ReturnType<typeof makeStyles>;
  colors: ColorTokens;
}) {
  return (
    <>
      <Text style={props.styles.label}>{props.label}</Text>
      <TextInput
        accessibilityLabel={props.label}
        value={props.value}
        onChangeText={props.onChangeText}
        style={props.styles.input}
        placeholder={props.placeholder}
        placeholderTextColor={props.colors.muted}
        keyboardType={props.keyboardType}
      />
    </>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    screen: { backgroundColor: colors.linen, flex: 1 },
    content: { padding: 24, paddingBottom: 36 },
    back: { minHeight: 44, justifyContent: 'center' },
    backText: { color: colors.spruce, fontWeight: '800' },
    kicker: {
      color: colors.clay,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.4,
      marginTop: 14,
    },
    title: { color: colors.ink, fontSize: 32, fontWeight: '700', marginTop: 7 },
    intro: { color: colors.muted, fontSize: 16, lineHeight: 23, marginTop: 8 },
    themeCard: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 14,
    },
    themeTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' },
    themeSwitch: {
      backgroundColor: colors.linenMuted,
      borderRadius: 12,
      flexDirection: 'row',
      marginTop: 10,
      padding: 3,
    },
    themeOption: {
      alignItems: 'center',
      borderRadius: 9,
      flex: 1,
      minHeight: 38,
      justifyContent: 'center',
    },
    themeOptionActive: { backgroundColor: colors.white },
    themeOptionText: { color: colors.muted, fontSize: 13, fontWeight: '800' },
    themeOptionTextActive: { color: colors.spruce },
    devicesCard: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 14,
      padding: 14,
    },
    devicesTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' },
    devicesIntro: { color: colors.muted, lineHeight: 19, marginTop: 5 },
    deviceRow: {
      alignItems: 'center',
      borderTopColor: colors.border,
      borderTopWidth: 1,
      flexDirection: 'row',
      gap: 10,
      justifyContent: 'space-between',
      marginTop: 12,
      paddingTop: 12,
    },
    deviceCopy: { flex: 1 },
    deviceName: { color: colors.ink, fontWeight: '800' },
    deviceMeta: { color: colors.muted, fontSize: 12, marginTop: 3 },
    revoke: { minHeight: 38, justifyContent: 'center', paddingHorizontal: 8 },
    revokeText: { color: colors.berry, fontSize: 12, fontWeight: '800' },
    memoryButton: {
      backgroundColor: colors.white,
      borderColor: colors.spruce,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 14,
      padding: 16,
    },
    memoryButtonTitle: { color: colors.ink, fontWeight: '800' },
    memoryButtonText: { color: colors.muted, lineHeight: 20, marginTop: 5 },
    loader: { marginTop: 30 },
    alert: {
      backgroundColor: colors.berrySoft,
      borderColor: colors.berry,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 18,
      padding: 14,
    },
    alertTitle: { color: colors.ink, fontWeight: '800' },
    alertText: { color: colors.muted, lineHeight: 19, marginTop: 5 },
    retry: { alignSelf: 'flex-start', minHeight: 36, justifyContent: 'center', marginTop: 6 },
    retryText: { color: colors.spruce, fontWeight: '800' },
    form: {
      backgroundColor: colors.white,
      borderColor: colors.border,
      borderLeftColor: colors.spruce,
      borderLeftWidth: 4,
      borderRadius: 16,
      borderWidth: 1,
      marginTop: 20,
      padding: 16,
    },
    label: { color: colors.ink, fontSize: 14, fontWeight: '800', marginTop: 12 },
    input: {
      backgroundColor: colors.linen,
      borderColor: colors.border,
      borderRadius: 12,
      borderWidth: 1,
      color: colors.ink,
      fontSize: 16,
      marginTop: 7,
      minHeight: 48,
      paddingHorizontal: 12,
    },
    readonly: { color: colors.muted, marginTop: 7 },
    help: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 16 },
    error: { color: colors.berry, marginTop: 12 },
    primary: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 16,
      justifyContent: 'center',
      marginTop: 18,
      minHeight: 50,
    },
    primaryText: { color: colors.white, fontWeight: '800' },
    signOut: {
      alignItems: 'center',
      borderColor: colors.berry,
      borderRadius: 16,
      borderWidth: 1,
      justifyContent: 'center',
      marginTop: 28,
      minHeight: 50,
    },
    signOutText: { color: colors.berry, fontWeight: '800' },
    disabled: { opacity: 0.6 },
  });
}
