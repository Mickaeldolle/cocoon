import { create } from 'zustand';

import {
  authApi,
  clearRefreshToken,
  loadRefreshToken,
  saveRefreshToken,
  type CurrentUser,
  type TokenPair,
} from '@/src/services/api';

type SessionState = {
  initialized: boolean;
  accessToken: string | null;
  user: CurrentUser | null;
  start: (tokens: TokenPair) => Promise<void>;
  restore: () => Promise<void>;
  end: () => Promise<void>;
};

export const useSessionStore = create<SessionState>((set, get) => ({
  initialized: false,
  accessToken: null,
  user: null,

  start: async (tokens) => {
    await saveRefreshToken(tokens.refresh_token);
    const user = await authApi.me(tokens.access_token);
    set({ accessToken: tokens.access_token, user, initialized: true });
  },

  restore: async () => {
    try {
      const refreshToken = await loadRefreshToken();
      if (!refreshToken) {
        set({ initialized: true });
        return;
      }
      const tokens = await authApi.refresh(refreshToken);
      await get().start(tokens);
    } catch {
      await clearRefreshToken();
      set({ accessToken: null, user: null, initialized: true });
    }
  },

  end: async () => {
    const { accessToken } = get();
    try {
      if (accessToken) await authApi.logout(accessToken);
    } finally {
      await clearRefreshToken();
      set({ accessToken: null, user: null, initialized: true });
    }
  },
}));
