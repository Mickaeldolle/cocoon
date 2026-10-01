import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';
import { z } from 'zod';

import { theme } from '@/src/theme';

const schema = z.object({
  email: z.string().email('Saisissez une adresse email valide.'),
  password: z.string().min(12, 'Utilisez au moins 12 caractères.'),
  display_name: z.string().max(100, 'Utilisez au plus 100 caractères.').optional(),
});

export type Credentials = z.infer<typeof schema>;

type Props = {
  actionLabel: string;
  busy: boolean;
  error: string | null;
  showDisplayName?: boolean;
  onSubmit: (credentials: Credentials) => Promise<void>;
  onPasskey?: (email: string) => Promise<void>;
  passkeyAvailable?: boolean;
  onBiometric?: () => Promise<void>;
};

export function AuthForm({
  actionLabel,
  busy,
  error,
  showDisplayName = false,
  onSubmit,
  onPasskey,
  passkeyAvailable = false,
  onBiometric,
}: Props) {
  const [passwordVisible, setPasswordVisible] = useState(false);
  const {
    control,
    getValues,
    handleSubmit,
    formState: { errors },
  } = useForm<Credentials>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '', display_name: '' },
  });

  return (
    <View style={styles.form}>
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
      {showDisplayName ? (
        <>
          <Text style={styles.label}>Votre prénom ou nom d’usage</Text>
          <Controller
            control={control}
            name="display_name"
            render={({ field: { onChange, onBlur, value } }) => (
              <TextInput
                accessibilityLabel="Votre prénom ou nom d’usage"
                autoComplete="name"
                onBlur={onBlur}
                onChangeText={onChange}
                style={[styles.input, errors.display_name && styles.inputError]}
                value={value}
              />
            )}
          />
          {errors.display_name ? (
            <Text style={styles.fieldError}>{errors.display_name.message}</Text>
          ) : null}
        </>
      ) : null}
      <Text style={styles.label}>Adresse email</Text>
      <Controller
        control={control}
        name="email"
        render={({ field: { onChange, onBlur, value } }) => (
          <TextInput
            accessibilityLabel="Adresse email"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            onBlur={onBlur}
            onChangeText={onChange}
            placeholder="vous@exemple.fr"
            placeholderTextColor={theme.colors.muted}
            style={[styles.input, errors.email && styles.inputError]}
            value={value}
          />
        )}
      />
      {errors.email ? <Text style={styles.fieldError}>{errors.email.message}</Text> : null}

      <Text style={styles.label}>Mot de passe</Text>
      <View style={[styles.passwordRow, errors.password && styles.inputError]}>
        <Controller
          control={control}
          name="password"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              accessibilityLabel="Mot de passe"
              autoComplete="current-password"
              onBlur={onBlur}
              onChangeText={onChange}
              secureTextEntry={!passwordVisible}
              style={styles.passwordInput}
              value={value}
            />
          )}
        />
        <Pressable
          auditAction="auth.password.visibility"
          accessibilityLabel={
            passwordVisible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'
          }
          accessibilityRole="button"
          onPress={() => setPasswordVisible((visible) => !visible)}
          style={styles.revealButton}
        >
          <Text style={styles.revealText}>{passwordVisible ? 'Masquer' : 'Afficher'}</Text>
        </Pressable>
      </View>
      {errors.password ? <Text style={styles.fieldError}>{errors.password.message}</Text> : null}

      <Pressable
        auditAction="auth.submit"
        accessibilityRole="button"
        disabled={busy}
        onPress={handleSubmit(onSubmit)}
        style={({ pressed }) => [
          styles.submit,
          pressed && !busy && styles.submitPressed,
          busy && styles.submitBusy,
        ]}
      >
        {busy ? (
          <ActivityIndicator color={theme.colors.white} />
        ) : (
          <Text style={styles.submitText}>{actionLabel}</Text>
        )}
      </Pressable>
      {onBiometric ? (
        <Pressable
          auditAction="auth.biometric"
          accessibilityRole="button"
          disabled={busy}
          onPress={() => void onBiometric()}
          style={[styles.passkey, busy && styles.submitBusy]}
        >
          <Text style={styles.passkeyText}>Rouvrir avec l’empreinte</Text>
        </Pressable>
      ) : null}
      {onPasskey ? (
        passkeyAvailable ? (
          <>
            <Pressable
              auditAction="auth.passkey"
              accessibilityRole="button"
              disabled={busy}
              onPress={() => void onPasskey(getValues('email'))}
              style={[styles.passkey, busy && styles.submitBusy]}
            >
              <Text style={styles.passkeyText}>Se connecter avec une passkey</Text>
            </Pressable>
            <Text style={styles.passkeyHint}>
              Première utilisation ? Créez votre passkey depuis le profil après connexion.
            </Text>
          </>
        ) : (
          <Text style={styles.passkeyHint}>
            La passkey nécessite un navigateur compatible sur une page HTTPS.
          </Text>
        )
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: theme.spacing.compact },
  label: {
    color: theme.colors.ink,
    fontSize: 15,
    fontWeight: '600',
    marginTop: theme.spacing.compact,
  },
  input: {
    backgroundColor: theme.colors.white,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.input,
    borderWidth: 1,
    color: theme.colors.ink,
    fontSize: 16,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  inputError: { borderColor: theme.colors.berry },
  passwordRow: {
    alignItems: 'center',
    backgroundColor: theme.colors.white,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.input,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 50,
  },
  passwordInput: {
    color: theme.colors.ink,
    flex: 1,
    fontSize: 16,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  revealButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 14 },
  revealText: { color: theme.colors.spruce, fontWeight: '700' },
  submit: {
    alignItems: 'center',
    backgroundColor: theme.colors.spruce,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    marginTop: theme.spacing.content,
    minHeight: 52,
  },
  submitPressed: { backgroundColor: theme.colors.ink },
  submitBusy: { opacity: 0.7 },
  submitText: { color: theme.colors.white, fontSize: 16, fontWeight: '700' },
  passkey: {
    alignItems: 'center',
    borderColor: theme.colors.spruce,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 52,
  },
  passkeyText: { color: theme.colors.spruce, fontSize: 16, fontWeight: '700' },
  passkeyHint: { color: theme.colors.muted, fontSize: 13, lineHeight: 19 },
  error: { backgroundColor: '#FDECEE', borderRadius: 12, color: theme.colors.berry, padding: 12 },
  fieldError: { color: theme.colors.berry, fontSize: 13 },
});
