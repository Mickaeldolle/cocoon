import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const pendingCaptureKey = 'cocoon.pending-capture.v1';

export type PendingCapture = {
  ownerId: string;
  text: string;
  timezone: string;
  idempotencyKey: string;
  runId: string | null;
  createdAt: string;
};

async function readValue(): Promise<string | null> {
  if (Platform.OS === 'web') return window.localStorage.getItem(pendingCaptureKey);
  return SecureStore.getItemAsync(pendingCaptureKey);
}

async function writeValue(value: string): Promise<void> {
  if (Platform.OS === 'web') {
    window.localStorage.setItem(pendingCaptureKey, value);
    return;
  }
  await SecureStore.setItemAsync(pendingCaptureKey, value);
}

export async function loadPendingCapture(ownerId: string): Promise<PendingCapture | null> {
  const raw = await readValue();
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingCapture>;
    if (
      value.ownerId !== ownerId ||
      typeof value.text !== 'string' ||
      typeof value.timezone !== 'string' ||
      typeof value.idempotencyKey !== 'string' ||
      typeof value.createdAt !== 'string'
    ) {
      return null;
    }
    return {
      ownerId: value.ownerId,
      text: value.text,
      timezone: value.timezone,
      idempotencyKey: value.idempotencyKey,
      runId: typeof value.runId === 'string' ? value.runId : null,
      createdAt: value.createdAt,
    };
  } catch {
    return null;
  }
}

export async function savePendingCapture(value: PendingCapture): Promise<void> {
  await writeValue(JSON.stringify(value));
}

export async function updatePendingCaptureRunId(
  ownerId: string,
  idempotencyKey: string,
  runId: string,
): Promise<void> {
  const current = await loadPendingCapture(ownerId);
  if (!current || current.idempotencyKey !== idempotencyKey) return;
  await savePendingCapture({ ...current, runId });
}

export async function clearPendingCapture(ownerId: string, idempotencyKey?: string): Promise<void> {
  const current = await loadPendingCapture(ownerId);
  if (!current || (idempotencyKey && current.idempotencyKey !== idempotencyKey)) return;
  if (Platform.OS === 'web') {
    window.localStorage.removeItem(pendingCaptureKey);
    return;
  }
  await SecureStore.deleteItemAsync(pendingCaptureKey);
}
