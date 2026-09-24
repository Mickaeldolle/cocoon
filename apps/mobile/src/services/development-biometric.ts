import * as Crypto from 'expo-crypto';
import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import { secretApi } from '@/src/services/api';

const developmentCredentialKey = 'cocoon.development-biometric-credential';

function isDevelopmentNativeDevice(): boolean {
  return __DEV__ && Platform.OS !== 'web';
}

export async function hasDevelopmentBiometricCredential(): Promise<boolean> {
  if (!isDevelopmentNativeDevice()) return false;
  await requireNativeBiometric();
  return true;
}

async function requireNativeBiometric(): Promise<void> {
  if (!isDevelopmentNativeDevice()) {
    throw new Error('La biométrie de développement nécessite un appareil mobile.');
  }
  if (
    !(await LocalAuthentication.hasHardwareAsync()) ||
    !(await LocalAuthentication.isEnrolledAsync())
  ) {
    throw new Error('Aucune empreinte ou méthode biométrique n’est configurée sur cet appareil.');
  }
  const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
  if (
    Platform.OS === 'ios' &&
    Constants.executionEnvironment === ExecutionEnvironment.StoreClient &&
    types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION) &&
    !types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)
  ) {
    throw new Error(
      'Face ID nécessite une version installée de Cocoon et ne fonctionne pas dans Expo Go. Utilisez votre mot de passe.',
    );
  }
  if (
    Platform.OS === 'android' &&
    (await LocalAuthentication.getEnrolledLevelAsync()) !==
      LocalAuthentication.SecurityLevel.BIOMETRIC_STRONG
  ) {
    throw new Error(
      'Configurez une empreinte ou une biométrie forte sur cet appareil, ou utilisez votre mot de passe.',
    );
  }
}

export async function authenticateDevelopmentBiometric(
  accessToken: string,
  userId: string,
): Promise<string> {
  await requireNativeBiometric();
  const result = await LocalAuthentication.authenticateAsync({
    biometricsSecurityLevel: 'strong',
    cancelLabel: 'Annuler',
    disableDeviceFallback: true,
    fallbackLabel: '',
    promptMessage: 'Déverrouiller Cocoon',
    requireConfirmation: true,
  });
  if (!result.success) {
    const messages: Record<string, string> = {
      user_cancel: 'Vérification annulée. Vous pouvez réessayer ou utiliser votre mot de passe.',
      app_cancel: 'Vérification interrompue. Réessayez.',
      system_cancel: 'Vérification interrompue par le téléphone. Réessayez.',
      lockout:
        'Biométrie temporairement bloquée. Déverrouillez votre téléphone ou utilisez votre mot de passe.',
      not_enrolled: 'Configurez la biométrie dans les réglages du téléphone.',
      not_available: 'La biométrie est indisponible. Utilisez votre mot de passe.',
      authentication_failed:
        'Empreinte ou visage non reconnu. Réessayez ou utilisez votre mot de passe.',
      passcode_not_set: 'Configurez un code de verrouillage sur votre téléphone.',
    };
    throw new Error(
      messages[result.error] ??
        'La vérification biométrique a échoué. Réessayez ou utilisez votre mot de passe.',
    );
  }
  const key = `${developmentCredentialKey}.${userId}`;
  let credential = await SecureStore.getItemAsync(key);
  if (!credential) {
    credential = Crypto.randomUUID();
    await secretApi.enrollDevelopmentBiometric(accessToken, credential);
    await SecureStore.setItemAsync(key, credential);
  }
  return credential;
}
