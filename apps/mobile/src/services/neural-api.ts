// Capture and neural endpoints share the HTTP client and session renewal in api.ts.
type Request = <T>(path: string, options?: RequestInit) => Promise<T>;
type AuthorizedOptions = (accessToken: string, options?: RequestInit) => RequestInit;
type StreamRequest = (path: string, options: RequestInit, accessToken: string) => Promise<Response>;
type ApiErrorConstructor = new (status: number, message: string) => Error & { status: number };

export type NeuralProposal = {
  id: string;
  capability: string;
  payload: Record<string, unknown>;
  payload_version: number;
  reason: string;
  status: string;
  confirmed_at?: string | null;
};
export type CaptureResult = {
  id: string;
  run_id: string;
  summary: string;
  clarification: string | null;
  proposals: NeuralProposal[];
  mode: 'rules' | 'llm';
};
export type CaptureProgress = { stage: string; text: string };
export type CaptureRunEvent = {
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};
export type CaptureRun = {
  id: string;
  capture_id: string;
  status: string;
  attempt: number;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
  events: CaptureRunEvent[];
};
export type CaptureStreamHandlers = {
  onRunId?: (runId: string) => void;
  onProgress?: (event: CaptureProgress) => void;
  onFragment?: (text: string) => void;
};
export type HomeSignal = {
  id: string;
  kind: 'now' | 'review' | 'confirm';
  title: string;
  reason: string;
  source: string;
  proposal_id: string | null;
  payload_version: number | null;
};

export function createNeuralApi(
  call: Request,
  withAccessToken: AuthorizedOptions,
  streamRequest: StreamRequest,
  ApiError: ApiErrorConstructor,
) {
  return {
    capture: (accessToken: string, text: string, timezone: string, idempotencyKey?: string) =>
      call<CaptureResult>(
        '/api/captures',
        withAccessToken(accessToken, {
          method: 'POST',
          body: JSON.stringify({ text, timezone }),
          headers: idempotencyKey ? { 'X-Capture-Idempotency-Key': idempotencyKey } : undefined,
        }),
      ),
    queueCapture: (accessToken: string, text: string, timezone: string, idempotencyKey?: string) =>
      call<CaptureRun>(
        '/api/captures/queue',
        withAccessToken(accessToken, {
          method: 'POST',
          body: JSON.stringify({ text, timezone }),
          headers: idempotencyKey ? { 'X-Capture-Idempotency-Key': idempotencyKey } : undefined,
        }),
      ),
    streamCapture: async (
      accessToken: string,
      text: string,
      timezone: string,
      handlers: CaptureStreamHandlers = {},
      signal?: AbortSignal,
      options: { idempotencyKey?: string; lastEventId?: number } = {},
    ): Promise<CaptureResult> => {
      const effectiveIdempotencyKey =
        options.idempotencyKey ?? `mobile-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      let cursor = options.lastEventId ?? 0;
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const response = await streamRequest(
            '/api/captures/stream',
            {
              method: 'POST',
              signal,
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${accessToken}`,
                'X-Capture-Idempotency-Key': effectiveIdempotencyKey,
                ...(cursor > 0 ? { 'Last-Event-ID': String(cursor) } : {}),
              },
              body: JSON.stringify({ text, timezone }),
            },
            accessToken,
          );
          if (!response.ok || !response.body) {
            const body: unknown = await response.json().catch(() => null);
            const detail =
              typeof body === 'object' && body && 'detail' in body
                ? String(body.detail)
                : 'La capture ne peut pas être traitée pour le moment.';
            throw new ApiError(response.status, detail);
          }
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let completed: CaptureResult | null = null;
          const consume = (block: string) => {
            const id = block.match(/^id:\s*(\d+)$/m);
            if (id) cursor = Number(id[1]);
            const event = block.match(/^event:\s*(\w+)\ndata:\s*([\s\S]+)$/m);
            if (!event) return;
            const data = JSON.parse(event[2]) as Record<string, unknown>;
            if (typeof data.run_id === 'string') handlers.onRunId?.(data.run_id);
            if (
              event[1] === 'progress' &&
              typeof data.stage === 'string' &&
              typeof data.text === 'string'
            ) {
              handlers.onProgress?.({ stage: data.stage, text: data.text });
            } else if (event[1] === 'fragment' && typeof data.text === 'string') {
              handlers.onFragment?.(data.text);
            } else if (event[1] === 'run_event' && typeof data.event_type === 'string') {
              const progressText: Record<string, string> = {
                capture_persisted: 'Capture enregistrée',
                understand_started: 'Je comprends votre demande',
                completed: 'Je prépare vos choix',
              };
              const progress = progressText[data.event_type];
              if (progress) handlers.onProgress?.({ stage: data.event_type, text: progress });
            } else if (event[1] === 'complete') {
              completed = data as unknown as CaptureResult;
            } else if (event[1] === 'error') {
              throw new ApiError(502, String(data.detail || 'La capture a échoué.'));
            }
          };
          while (true) {
            const chunk = await reader.read();
            buffer += decoder.decode(chunk.value, { stream: !chunk.done });
            const blocks = buffer.split('\n\n');
            buffer = blocks.pop() ?? '';
            blocks.forEach(consume);
            if (chunk.done) break;
          }
          if (completed) return completed;
          throw new ApiError(502, 'La capture n’a pas fourni de résultat exploitable.');
        } catch (error) {
          if (signal?.aborted) throw error;
          lastError = error;
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) throw error;
        }
      }
      throw lastError instanceof Error
        ? lastError
        : new ApiError(502, 'La capture n’a pas pu être reprise.');
    },
    home: (accessToken: string) =>
      call<{ signals: HomeSignal[] }>('/api/home', withAccessToken(accessToken)),
    getRun: (accessToken: string, runId: string) =>
      call<CaptureRun>(`/api/runs/${runId}`, withAccessToken(accessToken)),
    cancelRun: (accessToken: string, runId: string) =>
      call<CaptureRun>(
        `/api/runs/${runId}/cancel`,
        withAccessToken(accessToken, { method: 'POST' }),
      ),
    confirm: (accessToken: string, proposalId: string, payloadVersion?: number) =>
      call<NeuralProposal>(
        `/api/neural-proposals/${proposalId}/confirm`,
        withAccessToken(accessToken, {
          method: 'POST',
          headers: payloadVersion ? { 'X-Proposal-Version': String(payloadVersion) } : undefined,
        }),
      ),
    cancel: (accessToken: string, proposalId: string) =>
      call<NeuralProposal>(
        `/api/neural-proposals/${proposalId}/cancel`,
        withAccessToken(accessToken, { method: 'POST' }),
      ),
  };
}
