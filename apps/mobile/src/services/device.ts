import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { DeviceInput } from '@/src/services/api';

const installationIdKey = 'cocoon.installation-id';

export async function getDevice(): Promise<DeviceInput> {
  let installationId =
    Platform.OS === 'web'
      ? window.localStorage.getItem(installationIdKey)
      : await SecureStore.getItemAsync(installationIdKey);
  if (!installationId) {
    installationId = Crypto.randomUUID();
    if (Platform.OS === 'web') {
      window.localStorage.setItem(installationIdKey, installationId);
    } else {
      await SecureStore.setItemAsync(installationIdKey, installationId);
    }
  }

  return {
    installation_id: installationId,
    name: Platform.OS === 'ios' ? 'Appareil iOS' : 'Appareil Android',
    platform: Platform.OS === 'ios' ? 'ios' : 'android',
  };
}
