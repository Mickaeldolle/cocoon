import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MaterialSymbols_400Regular } from '@expo-google-fonts/material-symbols/400Regular';
import { useFonts } from '@expo-google-fonts/material-symbols/useFonts';
import { Stack } from 'expo-router';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useThemeStore } from '@/src/stores/theme-store';
import { secretApi } from '@/src/services/api';
import {
  routeForPersonalNotification,
  subscribeToPersonalNotificationResponses,
} from '@/src/services/notifications';
import { useSecretAccessStore } from '@/src/stores/secret-access-store';
import { useSessionStore } from '@/src/stores/session-store';

export default function RootLayout() {
  const [queryClient] = useState(() => new QueryClient());
  useFonts({ MaterialSymbols_400Regular });
  const restoreTheme = useThemeStore((state) => state.restore);
  const accessToken = useSessionStore((state) => state.accessToken);
  const userId = useSessionStore((state) => state.user?.id ?? null);
  const secretToken = useSecretAccessStore((state) => state.token);
  const secretExpiresAt = useSecretAccessStore((state) => state.expiresAt);
  const clearSecretAccess = useSecretAccessStore((state) => state.clear);
  const previousUserId = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    void restoreTheme();
  }, [restoreTheme]);
  useEffect(() => {
    let disposed = false;
    let unsubscribe: () => void = () => undefined;
    void subscribeToPersonalNotificationResponses((data) => {
      router.push(routeForPersonalNotification(data));
    }).then((remove) => {
      if (disposed) remove();
      else unsubscribe = remove;
    });
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);
  useEffect(() => {
    if (previousUserId.current !== undefined && previousUserId.current !== userId) {
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== 'secret',
      });
    }
    previousUserId.current = userId;
  }, [queryClient, userId]);
  useEffect(() => {
    const lock = () => {
      if (accessToken && secretToken)
        void secretApi.lock(accessToken, secretToken).catch(() => undefined);
      clearSecretAccess();
      queryClient.removeQueries({ queryKey: ['secret'] });
      router.replace('/home');
    };
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'active' && secretToken) lock();
    });
    return () => subscription.remove();
  }, [accessToken, clearSecretAccess, queryClient, secretToken]);
  useEffect(() => {
    if (!secretToken || !secretExpiresAt) return;
    const delay = Math.max(new Date(secretExpiresAt).getTime() - Date.now(), 0);
    const timeout = setTimeout(() => {
      clearSecretAccess();
      queryClient.removeQueries({ queryKey: ['secret'] });
      router.replace('/home');
    }, delay);
    return () => clearTimeout(timeout);
  }, [clearSecretAccess, queryClient, secretExpiresAt, secretToken]);
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <Stack screenOptions={{ headerShown: false }} />
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
