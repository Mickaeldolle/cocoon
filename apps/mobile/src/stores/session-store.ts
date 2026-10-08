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
  deferredNotificationAccountId: string | null;
  start: (tokens: TokenPair, freshLogin?: boolean) => Promise<void>;
  restore: () => Promise<void>;
  refreshUser: () => Promise<void>;
  end: () => Promise<void>;
};

let sessionGeneration = 0;
let tokenStorageWork: Promise<void> = Promise.resolve();
let renewal: { generation: number; promise: Promise<string | null> } | null = null;
let lastRenewedFrom: string | null = null;

function changeRefreshToken(generation: number, change: () => Promise<void>): Promise<void> {
  const work = tokenStorageWork
    .catch(() => undefined)
    .then(async () => {
      if (generation === sessionGeneration) await change();
    });
  tokenStorageWork = work;
  return work;
}

export const useSessionStore = create<SessionState>((set, get) => {
  const adoptTokens = async (tokens: TokenPair, freshLogin: boolean, generation: number) => {
    lastRenewedFrom = null;
    if (freshLogin) {
      try {
        await unsubscribeCurrentWebPush(() => generation === sessionGeneration);
      } catch {
        // A stale browser subscription is also rejected when another user registers it.
      }
    }
    if (generation !== sessionGeneration) return;
    // Older API deployments still require /me; new ones return the fresh profile.
    const user = tokens.user ?? (await authApi.me(tokens.access_token));
    if (generation !== sessionGeneration) return;
    await changeRefreshToken(generation, () => saveRefreshToken(tokens.refresh_token));
    if (generation !== sessionGeneration) return;
    set({
      accessToken: tokens.access_token,
      user,
      initialized: true,
      sessionExpired: false,
      deferredNotificationAccountId: null,
    });
  };

  return {
    initialized: false,
    accessToken: null,
    user: null,
    sessionExpired: false,
    deferredNotificationAccountId: null,

    start: async (tokens, freshLogin = false) => {
      const generation = ++sessionGeneration;
      await adoptTokens(tokens, freshLogin, generation);
    },

    restore: async () => {
      const generation = ++sessionGeneration;
      try {
        if (await isAndroidBiometricLoginEnabled()) {
          // Wait for an explicit Android biometric prompt on the sign-in screen.
          if (generation === sessionGeneration) set({ initialized: true });
          return;
        }
      } catch {
        // Do not restore a session if the local lock preference cannot be read.
        if (generation === sessionGeneration) set({ initialized: true });
        return;
      }
      if (generation !== sessionGeneration) return;
      try {
        const refreshToken = await loadRefreshToken();
        if (generation !== sessionGeneration) return;
        if (!refreshToken) {
          set({ initialized: true });
          return;
        }
        const tokens = await authApi.refresh(refreshToken);
        if (generation !== sessionGeneration) return;
        await adoptTokens(tokens, false, generation);
      } catch (error) {
        if (generation !== sessionGeneration) return;
        const expired = error instanceof ApiError && error.status === 401;
        if (expired) await changeRefreshToken(generation, clearRefreshToken);
        if (generation !== sessionGeneration) return;
        set({ accessToken: null, user: null, initialized: true, sessionExpired: expired });
      }
    },

    refreshUser: async () => {
      const generation = sessionGeneration;
      const accessToken = get().accessToken;
      if (!accessToken) return;
      const user = await authApi.me(accessToken);
      if (generation === sessionGeneration && get().accessToken === accessToken) set({ user });
    },

    end: async () => {
      const generation = ++sessionGeneration;
      lastRenewedFrom = null;
      const { accessToken } = get();
      set({
        accessToken: null,
        user: null,
        initialized: true,
        sessionExpired: false,
        deferredNotificationAccountId: null,
      });
      try {
        if (accessToken) await authApi.logout(accessToken);
      } finally {
        if (generation === sessionGeneration) {
          try {
            await unsubscribeCurrentWebPush(() => generation === sessionGeneration);
          } catch {
            // The API already removed this device's subscription on logout.
          }
          if (generation === sessionGeneration) await disableAndroidBiometricLogin();
          if (generation === sessionGeneration) {
            await changeRefreshToken(generation, clearRefreshToken);
          }
        }
      }
    },
  };
});

setAccessTokenRenewer((expiredToken) => {
  const generation = sessionGeneration;
  const currentToken = useSessionStore.getState().accessToken;
  if (!currentToken) return Promise.resolve(null);
  if (currentToken !== expiredToken) {
    return Promise.resolve(lastRenewedFrom === expiredToken ? currentToken : null);
  }
  if (renewal?.generation === generation) return renewal.promise;

  const promise = (async () => {
    try {
      const refreshToken = await loadRefreshToken();
      if (generation !== sessionGeneration) return null;
      if (!refreshToken) {
        useSessionStore.setState({ accessToken: null, user: null, sessionExpired: true });
        return null;
      }
      const tokens = await authApi.refresh(refreshToken);
      if (generation !== sessionGeneration) return null;
      if (useSessionStore.getState().accessToken !== expiredToken) {
        return lastRenewedFrom === expiredToken ? useSessionStore.getState().accessToken : null;
      }
      await changeRefreshToken(generation, () => saveRefreshToken(tokens.refresh_token));
      if (generation !== sessionGeneration) return null;
      lastRenewedFrom = expiredToken;
      useSessionStore.setState({ accessToken: tokens.access_token });
      return tokens.access_token;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (
          generation === sessionGeneration &&
          useSessionStore.getState().accessToken === expiredToken
        ) {
          await changeRefreshToken(generation, clearRefreshToken);
          if (generation !== sessionGeneration) return null;
          useSessionStore.setState({ accessToken: null, user: null, sessionExpired: true });
        }
        return null;
      }
      throw error;
    } finally {
      if (renewal?.generation === generation) renewal = null;
    }
  })();
  renewal = { generation, promise };
  return promise;
});
