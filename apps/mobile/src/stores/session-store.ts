import { create } from 'zustand';

import {
  disableAndroidBiometricLogin,
  isAndroidBiometricLoginEnabled,
} from '@/src/services/android-biometric-login';
import {
  ApiError,
  authApi,
  clearRefreshToken,
  loadRefreshToken,
  saveRefreshToken,
  setAccessTokenRenewer,
  type CurrentUser,
  type TokenPair,
} from '@/src/services/api';
import { unsubscribeCurrentWebPush } from '@/src/services/notifications';

type SessionState = {
  initialized: boolean;
  accessToken: string | null;
  user: CurrentUser | null;
  sessionExpired: boolean;
  start: (tokens: TokenPair, freshLogin?: boolean) => Promise<void>;
  restore: () => Promise<void>;
  refreshUser: () => Promise<void>;
  end: () => Promise<void>;
};

let renewal: Promise<string | null> | null = null;
let lastRenewedFrom: string | null = null;

export const useSessionStore = create<SessionState>((set, get) => ({
  initialized: false,
  accessToken: null,
  user: null,
  sessionExpired: false,

  start: async (tokens, freshLogin = false) => {
    lastRenewedFrom = null;
    if (freshLogin) {
      try {
        await unsubscribeCurrentWebPush();
      } catch {
        // A stale browser subscription is also rejected when another user registers it.
      }
    }
    await saveRefreshToken(tokens.refresh_token);
    // Older API deployments still require /me; new ones return the fresh profile
    // with the tokens, avoiding a second sequential request on cold start.
    const user = tokens.user ?? (await authApi.me(tokens.access_token));
    set({ accessToken: tokens.access_token, user, initialized: true, sessionExpired: false });
  },

  restore: async () => {
    try {
      if (await isAndroidBiometricLoginEnabled()) {
        // Wait for an explicit Android biometric prompt on the sign-in screen.
        set({ initialized: true });
        return;
      }
    } catch {
      // Do not restore a session if the local lock preference cannot be read.
      set({ initialized: true });
      return;
    }
    try {
      const refreshToken = await loadRefreshToken();
      if (!refreshToken) {
        set({ initialized: true });
        return;
      }
      const tokens = await authApi.refresh(refreshToken);
      await get().start(tokens);
    } catch (error) {
      const expired = error instanceof ApiError && error.status === 401;
      if (expired) await clearRefreshToken();
      set({ accessToken: null, user: null, initialized: true, sessionExpired: expired });
    }
  },

  refreshUser: async () => {
    const accessToken = get().accessToken;
    if (!accessToken) return;
    const user = await authApi.me(accessToken);
    if (get().accessToken === accessToken) set({ user });
  },

  end: async () => {
    lastRenewedFrom = null;
    const { accessToken } = get();
    try {
      if (accessToken) await authApi.logout(accessToken);
    } finally {
      try {
        await unsubscribeCurrentWebPush();
      } catch {
        // The API already removed this device's subscription on logout.
      }
      await disableAndroidBiometricLogin();
      await clearRefreshToken();
      set({ accessToken: null, user: null, initialized: true, sessionExpired: false });
    }
  },
}));

setAccessTokenRenewer((expiredToken) => {
  const currentToken = useSessionStore.getState().accessToken;
  if (!currentToken) return Promise.resolve(null);
  if (currentToken !== expiredToken) {
    return Promise.resolve(lastRenewedFrom === expiredToken ? currentToken : null);
  }
  if (renewal) return renewal;

  renewal = (async () => {
    try {
      const refreshToken = await loadRefreshToken();
      if (!refreshToken) {
        useSessionStore.setState({ accessToken: null, user: null, sessionExpired: true });
        return null;
      }
      const tokens = await authApi.refresh(refreshToken);
      if (useSessionStore.getState().accessToken !== expiredToken) {
        return lastRenewedFrom === expiredToken ? useSessionStore.getState().accessToken : null;
      }
      await saveRefreshToken(tokens.refresh_token);
      lastRenewedFrom = expiredToken;
      useSessionStore.setState({ accessToken: tokens.access_token });
      return tokens.access_token;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (useSessionStore.getState().accessToken === expiredToken) {
          await clearRefreshToken();
          useSessionStore.setState({ accessToken: null, user: null, sessionExpired: true });
        }
        return null;
      }
      throw error;
    } finally {
      renewal = null;
    }
  })();
  return renewal;
});
