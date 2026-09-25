import * as SecureStore from 'expo-secure-store';
import { File } from 'expo-file-system';
import { fetch as expoFetch } from 'expo/fetch';
import { Platform } from 'react-native';

const refreshTokenKey = 'cocoon.refresh-token';
const apiUrl = process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, '');

if (!apiUrl) {
  throw new Error('EXPO_PUBLIC_API_URL doit être défini pour appeler l’API Cocoon.');
}

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
};

export type SecretAccess = {
  secret_access_token: string;
  expires_at: string;
};

export type SecretPasskeyStatus = { available: boolean; has_passkeys: boolean };
export type SecretPasskeyCeremony = {
  challenge_id: string;
  options: Record<string, unknown>;
};

export type CurrentUser = {
  id: string;
  email: string;
  display_name: string;
  is_superadmin: boolean;
  created_at: string;
};

export type DeviceInput = {
  installation_id: string;
  name: string;
  platform: 'ios' | 'android';
};

export type Device = {
  id: string;
  name: string;
  platform: string;
  created_at: string;
  last_seen_at: string;
  current: boolean;
};

export type Consent = {
  id: string;
  policy_key: string;
  policy_version: number;
  source: string;
  granted_at: string;
  revoked_at: string | null;
  active: boolean;
};

export type FamilyRole = 'OWNER' | 'ADMIN' | 'MEMBER';

export type FamilySpace = {
  id: string;
  name: string;
  description: string | null;
  avatar_key: string | null;
  created_at: string;
  updated_at: string;
  role: FamilyRole;
};

export type Conversation = {
  id: string;
  name: string | null;
  created_at: string;
  updated_at: string;
  membership_status: 'pending' | 'accepted' | 'declined';
};

export type Message = {
  id: string;
  sender_id: string;
  body: string;
  created_at: string;
  read_by_count: number;
};

export type AssistantTag = 'school' | 'work' | 'errands' | 'family';
export type AssistantKind = 'task' | 'reminder' | 'note';

export type AssistantOrganization = {
  kind: AssistantKind;
  title: string;
  summary: string;
  tags: AssistantTag[];
  reminder_date: string | null;
  mode: 'rules' | 'llm';
};

export type AssistantProposalKind =
  | 'task'
  | 'grocery_item'
  | 'training'
  | 'note'
  | 'calendar_event'
  | 'recurring_reminder'
  | 'deadline_reminder';
export type AssistantProposalStatus = 'pending' | 'confirmed' | 'cancelled' | 'expired' | 'failed';

export type AssistantProposal = {
  id: string;
  kind: AssistantProposalKind;
  payload: Record<string, unknown>;
  payload_version: number;
  status: AssistantProposalStatus;
  created_at: string;
};

export type AssistantMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  proposals: AssistantProposal[];
};

export type AssistantHistory = { messages: AssistantMessage[] };
export type AssistantTurn = { message: AssistantMessage; mode: 'rules' | 'llm' };
export type AssistantChat = {
  message: AssistantMessage;
  choices: string[];
  remembered: string[];
  mode: 'llm';
  runtime: 'local';
};
export type AssistantStreamHandlers = {
  onDelta?: (text: string) => void;
};
export type VoiceTranscription = { text: string };
export type CalendarEvent = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  source: string;
};
export type AssistantBriefing = {
  heading: string;
  summary: string;
  tasks: string[];
  generated_at: string;
};
export type DailyBriefSettings = {
  timezone: string;
  delivery_time: string;
  enabled: boolean;
  daily_notification_quota: number;
};
export type PersonalNotification = {
  id: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  provider_status: 'pending' | 'accepted' | 'delivered' | 'retrying' | 'failed' | 'receipt_failed';
  sent_at: string | null;
  read_at: string | null;
  created_at: string;
};
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

export type MealPlanEntry = {
  day: string;
  name: string;
  description: string;
  uses: string[];
  missing_items: string[];
};

export type GroceryMealPlan = {
  meals: MealPlanEntry[];
  mode: 'rules' | 'llm';
};

export type Profile = {
  display_name: string;
  email: string;
  birth_date: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  target_weight_kg: number | null;
  weekly_training_target: number;
};

export type PersonalMemory = {
  id: string;
  capture_id: string;
  source_run_id: string | null;
  source_message_id: string | null;
  summary: string;
  reason: string;
  kind: string;
  layer: string;
  memory_type: string;
  owner_type: string;
  scope_type: string;
  scope_id: string | null;
  source_type: string;
  confidence: number;
  valid_from: string | null;
  valid_until: string | null;
  supersedes_id: string | null;
  created_at: string;
};

export type PersonalTask = {
  id: string;
  title: string;
  detail: string | null;
  due_date: string | null;
  completed: boolean;
  created_at: string;
};

export type PersonalProject = {
  id: string;
  name: string;
  description: string | null;
  status: 'active' | 'paused' | 'completed';
  created_at: string;
  updated_at: string;
};

export type GroceryItem = {
  id: string;
  label: string;
  checked: boolean;
  created_at: string;
};

export type TrainingSession = {
  id: string;
  label: string;
  training_type: 'renforcement' | 'course' | 'mobilite';
  timing: string;
  completed: boolean;
  created_at: string;
};

export type WeightCheckIn = {
  id: string;
  weight_kg: number;
  recorded_on: string;
  created_at: string;
};

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, options: RequestInit = {}, timeoutMs = 12_000): Promise<T> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener('abort', abortFromCaller, { once: true });
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError(
        0,
        'Le service Cocoon ne répond pas. Vérifiez la connexion puis réessayez.',
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === 'object' && body && 'detail' in body
        ? String(body.detail)
        : 'Une erreur est survenue.';
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

function withAccessToken(accessToken: string, options: RequestInit = {}): RequestInit {
  return {
    ...options,
    headers: { Authorization: `Bearer ${accessToken}`, ...options.headers },
  };
}

export const authApi = {
  register: (payload: DeviceInput & { email: string; display_name: string; password: string }) =>
    call<TokenPair>('/api/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload: DeviceInput & { email: string; password: string }) =>
    call<TokenPair>('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  refresh: (refreshToken: string) =>
    call<TokenPair>('/api/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),
  me: (accessToken: string) =>
    call<CurrentUser>('/api/auth/me', { headers: { Authorization: `Bearer ${accessToken}` } }),
  logout: (accessToken: string) =>
    call<void>('/api/auth/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    }),
  registerPushToken: (accessToken: string, pushToken: string) =>
    call<void>(
      '/api/auth/push-token',
      withAccessToken(accessToken, {
        method: 'PUT',
        body: JSON.stringify({ push_token: pushToken }),
      }),
    ),
  grantConsent: (accessToken: string, policyKey: string, policyVersion = 1) =>
    call<Consent>(
      `/api/auth/consents/${encodeURIComponent(policyKey)}`,
      withAccessToken(accessToken, {
        method: 'PUT',
        body: JSON.stringify({ policy_version: policyVersion, source: 'mobile' }),
      }),
    ),
  revokeConsent: (accessToken: string, policyKey: string) =>
    call<Consent>(
      `/api/auth/consents/${encodeURIComponent(policyKey)}`,
      withAccessToken(accessToken, { method: 'DELETE' }),
    ),
  listDevices: (accessToken: string) =>
    call<Device[]>('/api/auth/devices', withAccessToken(accessToken)),
  revokeDevice: (accessToken: string, deviceId: string) =>
    call<void>(`/api/auth/devices/${deviceId}`, withAccessToken(accessToken, { method: 'DELETE' })),
};

export const familySpacesApi = {
  list: (accessToken: string) =>
    call<FamilySpace[]>('/api/family-spaces', withAccessToken(accessToken)),
  get: (accessToken: string, spaceId: string) =>
    call<FamilySpace>(`/api/family-spaces/${spaceId}`, withAccessToken(accessToken)),
  create: (accessToken: string, payload: { name: string; description?: string }) =>
    call<FamilySpace>(
      '/api/family-spaces',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
  addMember: (accessToken: string, spaceId: string, email: string, role: FamilyRole) =>
    call<void>(
      `/api/family-spaces/${spaceId}/members`,
      withAccessToken(accessToken, {
        method: 'POST',
        body: JSON.stringify({ email, role }),
      }),
    ),
};

export const conversationsApi = {
  list: (accessToken: string) =>
    call<Conversation[]>('/api/conversations', withAccessToken(accessToken)),
  get: (accessToken: string, conversationId: string) =>
    call<Conversation>(`/api/conversations/${conversationId}`, withAccessToken(accessToken)),
  create: (accessToken: string, payload: { name?: string; invitee: string }) =>
    call<Conversation>(
      '/api/conversations',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
  accept: (accessToken: string, conversationId: string) =>
    call<Conversation>(
      `/api/conversations/${conversationId}/accept`,
      withAccessToken(accessToken, { method: 'POST' }),
    ),
  decline: (accessToken: string, conversationId: string) =>
    call<Conversation>(
      `/api/conversations/${conversationId}/decline`,
      withAccessToken(accessToken, { method: 'POST' }),
    ),
  listMessages: (accessToken: string, conversationId: string) =>
    call<Message[]>(`/api/conversations/${conversationId}/messages`, withAccessToken(accessToken)),
  sendMessage: (accessToken: string, conversationId: string, body: string) =>
    call<Message>(
      `/api/conversations/${conversationId}/messages`,
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify({ body }) }),
    ),
  issueRealtimeTicket: (accessToken: string) =>
    call<{ ticket: string }>(
      '/api/realtime/ticket',
      withAccessToken(accessToken, { method: 'POST' }),
    ),
};

function withSecretAccess(
  accessToken: string,
  secretAccessToken: string,
  options: RequestInit = {},
): RequestInit {
  return withAccessToken(accessToken, {
    ...options,
    headers: { 'X-Cocoon-Secret-Access': secretAccessToken, ...options.headers },
  });
}

export const secretApi = {
  unlock: (accessToken: string, password: string) =>
    call<SecretAccess>(
      '/api/secret/unlock',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify({ password }) }),
    ),
  passkeyStatus: (accessToken: string) =>
    call<SecretPasskeyStatus>('/api/secret/passkeys/status', withAccessToken(accessToken)),
  passkeyRegistrationOptions: (accessToken: string, password: string) =>
    call<SecretPasskeyCeremony>(
      '/api/secret/passkeys/register/options',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify({ password }) }),
    ),
  verifyPasskeyRegistration: (
    accessToken: string,
    challengeId: string,
    credential: Record<string, unknown>,
  ) =>
    call<SecretAccess>(
      '/api/secret/passkeys/register/verify',
      withAccessToken(accessToken, {
        method: 'POST',
        body: JSON.stringify({ challenge_id: challengeId, credential }),
      }),
    ),
  passkeyUnlockOptions: (accessToken: string) =>
    call<SecretPasskeyCeremony>(
      '/api/secret/passkeys/unlock/options',
      withAccessToken(accessToken, { method: 'POST' }),
    ),
  verifyPasskeyUnlock: (
    accessToken: string,
    challengeId: string,
    credential: Record<string, unknown>,
  ) =>
    call<SecretAccess>(
      '/api/secret/passkeys/unlock/verify',
      withAccessToken(accessToken, {
        method: 'POST',
        body: JSON.stringify({ challenge_id: challengeId, credential }),
      }),
    ),
  revokePasskeys: (accessToken: string, password: string) =>
    call<void>(
      '/api/secret/passkeys',
      withAccessToken(accessToken, { method: 'DELETE', body: JSON.stringify({ password }) }),
    ),
  lock: (accessToken: string, secretAccessToken: string) =>
    call<void>(
      '/api/secret/lock',
      withSecretAccess(accessToken, secretAccessToken, { method: 'POST' }),
    ),
  enrollDevelopmentBiometric: (accessToken: string, credential: string) =>
    call<void>(
      '/api/secret/development-biometric/enroll',
      withAccessToken(accessToken, {
        method: 'POST',
        body: JSON.stringify({ credential }),
      }),
    ),
  unlockWithDevelopmentBiometric: (accessToken: string, credential: string) =>
    call<SecretAccess>(
      '/api/secret/development-biometric/unlock',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify({ credential }) }),
    ),
  listConversations: (accessToken: string, secretAccessToken: string) =>
    call<Conversation[]>(
      '/api/secret/conversations',
      withSecretAccess(accessToken, secretAccessToken),
    ),
  createConversation: (
    accessToken: string,
    secretAccessToken: string,
    payload: { name?: string; invitee: string },
  ) =>
    call<Conversation>(
      '/api/secret/conversations',
      withSecretAccess(accessToken, secretAccessToken, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    ),
  acceptInvitation: (accessToken: string, secretAccessToken: string, conversationId: string) =>
    call<Conversation>(
      `/api/secret/conversations/${conversationId}/accept`,
      withSecretAccess(accessToken, secretAccessToken, { method: 'POST' }),
    ),
  declineInvitation: (accessToken: string, secretAccessToken: string, conversationId: string) =>
    call<Conversation>(
      `/api/secret/conversations/${conversationId}/decline`,
      withSecretAccess(accessToken, secretAccessToken, { method: 'POST' }),
    ),
  getConversation: (accessToken: string, secretAccessToken: string, conversationId: string) =>
    call<Conversation>(
      `/api/secret/conversations/${conversationId}`,
      withSecretAccess(accessToken, secretAccessToken),
    ),
  listMessages: (accessToken: string, secretAccessToken: string, conversationId: string) =>
    call<Message[]>(
      `/api/secret/conversations/${conversationId}/messages`,
      withSecretAccess(accessToken, secretAccessToken),
    ),
  sendMessage: (
    accessToken: string,
    secretAccessToken: string,
    conversationId: string,
    body: string,
  ) =>
    call<Message>(
      `/api/secret/conversations/${conversationId}/messages`,
      withSecretAccess(accessToken, secretAccessToken, {
        method: 'POST',
        body: JSON.stringify({ body }),
      }),
    ),
};

export const assistantApi = {
  chat: (accessToken: string, text: string, idempotencyKey?: string) =>
    call<AssistantChat>(
      '/api/assistant/chat',
      withAccessToken(accessToken, {
        method: 'POST',
        body: JSON.stringify({ text }),
        headers: idempotencyKey ? { 'X-Assistant-Idempotency-Key': idempotencyKey } : undefined,
      }),
      315_000,
    ),
  streamChat: async (
    accessToken: string,
    text: string,
    handlers: AssistantStreamHandlers = {},
    signal?: AbortSignal,
    idempotencyKey?: string,
  ): Promise<AssistantChat> => {
    const response = await expoFetch(`${apiUrl}/api/assistant/chat/stream`, {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        ...(idempotencyKey ? { 'X-Assistant-Idempotency-Key': idempotencyKey } : {}),
      },
      body: JSON.stringify({ text }),
    });
    if (!response.ok || !response.body) {
      const body: unknown = await response.json().catch(() => null);
      const detail =
        typeof body === 'object' && body && 'detail' in body
          ? String(body.detail)
          : 'La conversation ne peut pas être traitée pour le moment.';
      throw new ApiError(response.status, detail);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let completed: AssistantChat | null = null;
    const consume = (block: string) => {
      const event = block.match(/^event:\s*(\w+)\ndata:\s*([\s\S]+)$/m);
      if (!event) return;
      const data = JSON.parse(event[2]) as Record<string, unknown>;
      if (event[1] === 'delta' && typeof data.text === 'string') {
        handlers.onDelta?.(data.text);
      } else if (event[1] === 'complete') {
        completed = data as unknown as AssistantChat;
      } else if (event[1] === 'error') {
        throw new ApiError(
          typeof data.status === 'number' ? data.status : 502,
          String(data.detail || 'Le flux assistant a échoué.'),
        );
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
    if (buffer.trim()) consume(buffer.trim());
    if (!completed) throw new ApiError(502, 'Le flux assistant n’a pas fourni de résultat.');
    return completed;
  },
  turn: (accessToken: string, text: string) =>
    call<AssistantTurn>(
      '/api/assistant/turn',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify({ text }) }),
      195_000,
    ),
  transcribeVoice: async (
    accessToken: string,
    recordingUri: string,
    contentType: string,
    signal?: AbortSignal,
  ) => {
    const supportedTypes = new Set(['audio/mp4', 'audio/m4a', 'audio/webm', 'audio/wav']);
    if (!supportedTypes.has(contentType)) {
      throw new ApiError(415, 'Ce format audio n’est pas pris en charge.');
    }
    let bytes: ArrayBuffer;
    if (Platform.OS === 'web') {
      const recording = await fetch(recordingUri, { signal });
      if (!recording.ok)
        throw new ApiError(0, 'L’enregistrement vocal est introuvable. Réessayez.');
      bytes = await recording.arrayBuffer();
    } else {
      const recording = new File(recordingUri);
      if (!recording.exists)
        throw new ApiError(0, 'L’enregistrement vocal est introuvable. Réessayez.');
      if (recording.size > 8 * 1024 * 1024)
        throw new ApiError(413, 'L’enregistrement est trop long.');
      bytes = await recording.arrayBuffer();
    }
    if (bytes.byteLength === 0) {
      throw new ApiError(422, 'Audio vide.');
    }
    if (bytes.byteLength > 8 * 1024 * 1024) {
      throw new ApiError(
        413,
        'L’enregistrement est trop long. Réessayez avec un message plus court.',
      );
    }
    if (signal?.aborted) throw new Error('Dictée annulée.');
    await authApi.grantConsent(accessToken, 'assistant.voice');
    if (signal?.aborted) throw new Error('Dictée annulée.');
    return call<VoiceTranscription>(
      '/api/assistant/voice/transcriptions',
      withAccessToken(accessToken, {
        method: 'POST',
        headers: { 'Content-Type': contentType },
        body: bytes,
        signal,
      }),
      120_000,
    );
  },
  history: (accessToken: string) =>
    call<AssistantHistory>('/api/assistant/history', withAccessToken(accessToken)),
  calendarEvents: (accessToken: string, startsAfter?: string, endsBefore?: string) => {
    const query = new URLSearchParams();
    if (startsAfter) query.set('starts_after', startsAfter);
    if (endsBefore) query.set('ends_before', endsBefore);
    const suffix = query.size ? `?${query}` : '';
    return call<{ events: CalendarEvent[] }>(
      `/api/assistant/calendar/events${suffix}`,
      withAccessToken(accessToken),
    );
  },
  confirmProposal: (accessToken: string, proposalId: string, payloadVersion?: number) =>
    call<AssistantProposal>(
      `/api/assistant/proposals/${proposalId}/confirm`,
      withAccessToken(accessToken, {
        method: 'POST',
        headers: payloadVersion ? { 'X-Proposal-Version': String(payloadVersion) } : undefined,
      }),
    ),
  cancelProposal: (accessToken: string, proposalId: string) =>
    call<AssistantProposal>(
      `/api/assistant/proposals/${proposalId}/cancel`,
      withAccessToken(accessToken, { method: 'POST' }),
    ),
  briefing: (accessToken: string) =>
    call<AssistantBriefing>('/api/assistant/briefing', withAccessToken(accessToken)),
  getBriefSettings: (accessToken: string) =>
    call<DailyBriefSettings>('/api/assistant/brief-settings', withAccessToken(accessToken)),
  updateBriefSettings: (accessToken: string, payload: DailyBriefSettings) =>
    call<DailyBriefSettings>(
      '/api/assistant/brief-settings',
      withAccessToken(accessToken, { method: 'PUT', body: JSON.stringify(payload) }),
    ),
  listNotifications: (accessToken: string) =>
    call<PersonalNotification[]>('/api/assistant/notifications', withAccessToken(accessToken)),
  markNotificationRead: (accessToken: string, notificationId: string) =>
    call<PersonalNotification>(
      `/api/assistant/notifications/${notificationId}/read`,
      withAccessToken(accessToken, { method: 'POST' }),
    ),
  organize: (
    accessToken: string,
    payload: { thought: string; tags: AssistantTag[]; reference_date: string },
  ) =>
    call<AssistantOrganization>(
      '/api/assistant/organize',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
  planMeals: (accessToken: string, payload: { grocery_items: string[] }) =>
    call<GroceryMealPlan>(
      '/api/assistant/meal-plan',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
};

export const neuralApi = {
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
        const response = await expoFetch(`${apiUrl}/api/captures/stream`, {
          method: 'POST',
          signal,
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
            'X-Capture-Idempotency-Key': effectiveIdempotencyKey,
            ...(cursor > 0 ? { 'Last-Event-ID': String(cursor) } : {}),
          },
          body: JSON.stringify({ text, timezone }),
        });
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
    call<CaptureRun>(`/api/runs/${runId}/cancel`, withAccessToken(accessToken, { method: 'POST' })),
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

export const personalApi = {
  getProfile: (accessToken: string) =>
    call<Profile>('/api/personal/profile', withAccessToken(accessToken)),
  updateProfile: (accessToken: string, payload: Profile) =>
    call<Profile>(
      '/api/personal/profile',
      withAccessToken(accessToken, { method: 'PUT', body: JSON.stringify(payload) }),
    ),
  listMemories: (accessToken: string, limit = 50) =>
    call<{ memories: PersonalMemory[] }>(
      `/api/memories?limit=${encodeURIComponent(String(limit))}`,
      withAccessToken(accessToken),
    ),
  updateMemory: (
    accessToken: string,
    id: string,
    payload: { summary: string; memory_type?: string; layer?: string; confidence: number },
  ) =>
    call<PersonalMemory>(
      `/api/memories/${id}`,
      withAccessToken(accessToken, { method: 'PATCH', body: JSON.stringify(payload) }),
    ),
  forgetMemory: (accessToken: string, id: string) =>
    call<{ id: string; state: 'active' | 'stale' | 'dismissed' }>(
      `/api/memories/${id}`,
      withAccessToken(accessToken, { method: 'DELETE' }),
    ),
  listTasks: (accessToken: string) =>
    call<PersonalTask[]>('/api/personal/tasks', withAccessToken(accessToken)),
  createTask: (accessToken: string, payload: Pick<PersonalTask, 'title' | 'detail' | 'due_date'>) =>
    call<PersonalTask>(
      '/api/personal/tasks',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
  updateTask: (accessToken: string, id: string, completed: boolean) =>
    call<PersonalTask>(
      `/api/personal/tasks/${id}`,
      withAccessToken(accessToken, { method: 'PATCH', body: JSON.stringify({ completed }) }),
    ),
  listProjects: (accessToken: string) =>
    call<PersonalProject[]>('/api/personal/projects', withAccessToken(accessToken)),
  createProject: (accessToken: string, payload: Pick<PersonalProject, 'name' | 'description'>) =>
    call<PersonalProject>(
      '/api/personal/projects',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
  updateProject: (
    accessToken: string,
    id: string,
    payload: Partial<Pick<PersonalProject, 'name' | 'description' | 'status'>>,
  ) =>
    call<PersonalProject>(
      `/api/personal/projects/${id}`,
      withAccessToken(accessToken, { method: 'PATCH', body: JSON.stringify(payload) }),
    ),
  listGroceries: (accessToken: string) =>
    call<GroceryItem[]>('/api/personal/groceries', withAccessToken(accessToken)),
  createGrocery: (accessToken: string, label: string) =>
    call<GroceryItem>(
      '/api/personal/groceries',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify({ label }) }),
    ),
  updateGrocery: (accessToken: string, id: string, checked: boolean) =>
    call<GroceryItem>(
      `/api/personal/groceries/${id}`,
      withAccessToken(accessToken, { method: 'PATCH', body: JSON.stringify({ checked }) }),
    ),
  listTrainings: (accessToken: string) =>
    call<TrainingSession[]>('/api/personal/trainings', withAccessToken(accessToken)),
  createTraining: (
    accessToken: string,
    payload: Pick<TrainingSession, 'label' | 'training_type' | 'timing'>,
  ) =>
    call<TrainingSession>(
      '/api/personal/trainings',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
  updateTraining: (accessToken: string, id: string, completed: boolean) =>
    call<TrainingSession>(
      `/api/personal/trainings/${id}`,
      withAccessToken(accessToken, { method: 'PATCH', body: JSON.stringify({ completed }) }),
    ),
  listWeightCheckIns: (accessToken: string) =>
    call<WeightCheckIn[]>('/api/personal/weight-check-ins', withAccessToken(accessToken)),
  createWeightCheckIn: (
    accessToken: string,
    payload: { weight_kg: number; recorded_on?: string },
  ) =>
    call<WeightCheckIn>(
      '/api/personal/weight-check-ins',
      withAccessToken(accessToken, { method: 'POST', body: JSON.stringify(payload) }),
    ),
};

export async function saveRefreshToken(token: string): Promise<void> {
  if (Platform.OS === 'web') {
    window.localStorage.setItem(refreshTokenKey, token);
    return;
  }
  await SecureStore.setItemAsync(refreshTokenKey, token);
}

export async function loadRefreshToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    return window.localStorage.getItem(refreshTokenKey);
  }
  return SecureStore.getItemAsync(refreshTokenKey);
}

export async function clearRefreshToken(): Promise<void> {
  if (Platform.OS === 'web') {
    window.localStorage.removeItem(refreshTokenKey);
    return;
  }
  await SecureStore.deleteItemAsync(refreshTokenKey);
}

export { ApiError };
