import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { create } from 'zustand';

export type ThemeMode = 'dark' | 'light';
const themeKey = 'cocoon.theme-mode';

type ThemeState = {
  initialized: boolean;
  mode: ThemeMode;
  restore: () => Promise<void>;
  setMode: (mode: ThemeMode) => Promise<void>;
};

async function loadMode(): Promise<ThemeMode | null> {
  const value =
    Platform.OS === 'web'
      ? window.localStorage.getItem(themeKey)
      : await SecureStore.getItemAsync(themeKey);
  return value === 'light' || value === 'dark' ? value : null;
}

async function saveMode(mode: ThemeMode): Promise<void> {
  if (Platform.OS === 'web') {
    window.localStorage.setItem(themeKey, mode);
    return;
  }
  await SecureStore.setItemAsync(themeKey, mode);
}

export const useThemeStore = create<ThemeState>((set) => ({
  initialized: false,
  mode: 'dark',
  restore: async () => {
    try {
      const mode = await loadMode();
      set({ mode: mode ?? 'dark' });
    } catch {
      // A theme preference must never prevent Cocoon from opening.
    } finally {
      set({ initialized: true });
    }
  },
  setMode: async (mode) => {
    set({ mode });
    try {
      await saveMode(mode);
    } catch {
      // Keep the in-memory choice when device storage is temporarily unavailable.
    }
  },
}));
