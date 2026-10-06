import type { QueryClient } from '@tanstack/react-query';
import { assistantApi, type AssistantChat } from '@/src/services/api';

export type HomeReply = {
  key: string;
  text: string;
  model?: string;
  result: AssistantChat;
};

export const homeReplyKey = (userId: string | undefined, key: string | undefined) =>
  ['assistant', 'home-reply', userId, key] as const;

function checkAborted(signal: AbortSignal) {
  if (signal.aborted) {
    const error = new Error('Génération arrêtée.');
    error.name = 'AbortError';
    throw error;
  }
}

// Resolve the same default model as the conversation, then use its existing SSE API.
export async function requestHomeReply(
  client: QueryClient,
  token: string,
  userId: string,
  turn: { key: string; text: string; retry: boolean; model?: string },
  signal: AbortSignal,
): Promise<HomeReply> {
  const models = await client.fetchQuery({
    queryKey: ['assistant', 'free-models', userId],
    queryFn: () => assistantApi.freeModels(token),
    staleTime: 300_000,
    retry: false,
  });
  checkAborted(signal);
  const model = models.available
    ? (
        models.models.find((item) => item.id === turn.model) ??
        models.models.find((item) => item.id === models.default_model)
      )?.id
    : undefined;
  if (models.available && !model) throw new Error('Aucun modèle gratuit disponible. Réessayez.');
  const result = await assistantApi.streamChat(
    token,
    turn.text,
    {},
    signal,
    turn.key,
    turn.retry,
    model,
  );
  checkAborted(signal);
  return { key: turn.key, text: turn.text, model, result };
}
