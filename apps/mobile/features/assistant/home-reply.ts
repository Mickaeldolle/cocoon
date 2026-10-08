import type { QueryClient } from '@tanstack/react-query';
import { assistantApi, type AssistantChat, type AssistantFreeModels } from '@/src/services/api';

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

// The configured server model can answer before the optional free-model catalog loads.
export async function requestHomeReply(
  client: QueryClient,
  token: string,
  userId: string,
  turn: { key: string; text: string; retry: boolean; model?: string },
  signal: AbortSignal,
): Promise<HomeReply> {
  checkAborted(signal);
  const models = client.getQueryData<AssistantFreeModels>(['assistant', 'free-models', userId]);
  const model =
    turn.model ??
    (models?.available
      ? models.models.find((item) => item.id === models.default_model)?.id
      : undefined);
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
