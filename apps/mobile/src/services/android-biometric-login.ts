import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const preferenceKey = 'cocoon.android-biometric-login';

export async function isAndroidBiometricLoginEnabled(): Promise<boolean> {
  return Platform.OS === 'android' && (await SecureStore.getItemAsync(preferenceKey)) === 'enabled';
}

export async function canUseAndroidBiometrics(): Promise<boolean> {
  return (
    Platform.OS === 'android' &&
    (await LocalAuthentication.hasHardwareAsync()) &&
    (await LocalAuthentication.isEnrolledAsync()) &&
    (await LocalAuthentication.getEnrolledLevelAsync()) ===
      LocalAuthentication.SecurityLevel.BIOMETRIC_STRONG
  );
}

export async function authenticateAndroidBiometricLogin(): Promise<void> {
  if (!(await canUseAndroidBiometrics())) {
    throw new Error('Configurez une empreinte ou une biométrie forte sur ce téléphone.');
  }
  const result = await LocalAuthentication.authenticateAsync({
    biometricsSecurityLevel: 'strong',
    cancelLabel: 'Annuler',
    disableDeviceFallback: true,
    promptMessage: 'Rouvrir ma session Cocoon',
  });
  if (result.success) return;
  if (result.error === 'user_cancel' || result.error === 'system_cancel') {
    throw new Error('Vérification annulée. Votre session reste disponible.');
  }
  if (result.error === 'lockout') {
    throw new Error('La biométrie est temporairement bloquée. Utilisez votre mot de passe.');
  }
  throw new Error('Vérification biométrique impossible. Réessayez ou utilisez votre mot de passe.');
}

export async function enableAndroidBiometricLogin(): Promise<void> {
  await authenticateAndroidBiometricLogin();
  await SecureStore.setItemAsync(preferenceKey, 'enabled');
}

export async function disableAndroidBiometricLogin(): Promise<void> {
  if (Platform.OS === 'android') await SecureStore.deleteItemAsync(preferenceKey);
}
