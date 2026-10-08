// Personal data contracts and endpoints. The shared HTTP client and token renewal
// remain in api.ts; callers keep importing personalApi from that public facade.
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
  observed_at: string | null;
  state: 'active' | 'stale' | 'dismissed';
  entity: string | null;
  attribute: string | null;
  value: string | null;
  origin: string | null;
};

export type PersonalMemoryPage = {
  memories: PersonalMemory[];
  next_offset: number | null;
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

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;
type AuthorizedOptions = (accessToken: string, options?: RequestInit) => RequestInit;

export function createPersonalApi(call: Request, withAccessToken: AuthorizedOptions) {
  return {
    getProfile: (accessToken: string) =>
      call<Profile>('/api/personal/profile', withAccessToken(accessToken)),
    updateProfile: (accessToken: string, payload: Profile) =>
      call<Profile>(
        '/api/personal/profile',
        withAccessToken(accessToken, { method: 'PUT', body: JSON.stringify(payload) }),
      ),
    listMemories: (accessToken: string, limit = 50, offset = 0) =>
      call<PersonalMemoryPage>(
        `/api/memories?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`,
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
    createTask: (
      accessToken: string,
      payload: Pick<PersonalTask, 'title' | 'detail' | 'due_date'>,
    ) =>
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
}
