import { create } from 'zustand';

import type { SecretAccess } from '@/src/services/api';

type SecretAccessState = {
  token: string | null;
  expiresAt: string | null;
  grant: (access: SecretAccess) => void;
  clear: () => void;
};

// Deliberately memory-only: this token must disappear when the app process stops.
export const useSecretAccessStore = create<SecretAccessState>((set) => ({
  token: null,
  expiresAt: null,
  grant: (access) => set({ token: access.secret_access_token, expiresAt: access.expires_at }),
  clear: () => set({ token: null, expiresAt: null }),
}));
