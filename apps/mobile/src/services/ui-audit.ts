import { sendButtonPress } from '@/src/services/api';
import { useSessionStore } from '@/src/stores/session-store';

export function reportButtonPress(action: string): void {
  const token = useSessionStore.getState().accessToken;
  if (token) void sendButtonPress(token, action).catch(() => undefined);
}
