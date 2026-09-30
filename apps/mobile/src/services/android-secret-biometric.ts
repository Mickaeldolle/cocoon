import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import { ApiError, secretApi, type SecretAccess } from '@/src/services/api';
import { canUseAndroidBiometrics } from '@/src/services/android-biometric-login';

const markerPrefix = 'cocoon.secret-biometric-enabled.';
const credentialPrefix = 'cocoon.secret-biometric-credential.';

function keys(userId: string) {
  return { marker: `${markerPrefix}${userId}`, credential: `${credentialPrefix}${userId}` };
}

export async function hasAndroidSecretBiometric(userId: string): Promise<boolean> {
  if (Platform.OS !== 'android' || !(await canUseAndroidBiometrics())) return false;
  return (await SecureStore.getItemAsync(keys(userId).marker)) === 'enabled';
}

export async function enrollAndroidSecretBiometric(
  accessToken: string,
  userId: string,
  password: string,
): Promise<void> {
  if (!(await canUseAndroidBiometrics())) return;
  const bytes = await Crypto.getRandomBytesAsync(32);
  const credential = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  await secretApi.enrollAndroidBiometric(accessToken, password, credential);
  const names = keys(userId);
  await SecureStore.setItemAsync(names.credential, credential, {
    requireAuthentication: true,
    authenticationPrompt: 'Activer la biométrie pour les messages cachés',
  });
  await SecureStore.setItemAsync(names.marker, 'enabled');
}

export async function unlockWithAndroidSecretBiometric(
  accessToken: string,
  userId: string,
): Promise<SecretAccess> {
  const names = keys(userId);
  let credential: string | null;
  try {
    credential = await SecureStore.getItemAsync(names.credential, {
      requireAuthentication: true,
      authenticationPrompt: 'Déverrouiller les messages cachés',
    });
  } catch {
    throw new Error(
      'Vérification biométrique annulée ou indisponible. Utilisez votre mot de passe.',
    );
  }
  if (!credential) {
    await SecureStore.deleteItemAsync(names.marker);
    throw new Error('La biométrie doit être réactivée. Utilisez votre mot de passe.');
  }
  try {
    return await secretApi.unlockWithAndroidBiometric(accessToken, credential);
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 401) {
      await SecureStore.deleteItemAsync(names.marker);
      throw new Error('La biométrie doit être réactivée. Utilisez votre mot de passe.');
    }
    throw caught;
  }
}
