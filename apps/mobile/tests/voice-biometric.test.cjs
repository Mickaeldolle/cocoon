/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

// Native boundaries are injected; these tests run without a device or additional dependencies.
function load(relativePath, mocks = {}, globals = {}) {
  const filename = path.join(__dirname, '..', relativePath);
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(
    source,
    {
      module,
      exports: module.exports,
      require: (name) =>
        name === './personal-api'
          ? { createPersonalApi: () => ({}) }
          : name === './neural-api'
            ? { createNeuralApi: () => ({}) }
            : Object.hasOwn(mocks, name)
              ? mocks[name]
              : require(name),
      setTimeout,
      clearTimeout,
      AbortController,
      Headers,
      Error,
      URL,
      process,
      __DEV__: true,
      ...globals,
    },
    { filename },
  );
  return module.exports;
}

function apiFor(platform, File, fetch) {
  return load(
    'src/services/api.ts',
    {
      'expo-file-system': { File },
      'expo-secure-store': {},
      'expo/fetch': { fetch },
      'react-native': { Platform: { OS: platform } },
    },
    { fetch, process: { env: { EXPO_PUBLIC_API_URL: 'http://localhost:8002' } } },
  ).assistantApi;
}

test('API calls use one separator when the configured URL ends with a slash', async () => {
  const urls = [];
  const { authApi } = load(
    'src/services/api.ts',
    {
      'expo-file-system': { File: class {} },
      'expo-secure-store': {},
      'expo/fetch': { fetch: async () => assert.fail('Unexpected streaming request') },
      'react-native': { Platform: { OS: 'web' } },
    },
    {
      fetch: async (url) => {
        urls.push(url);
        return { ok: true, status: 200, json: async () => ({}) };
      },
      process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example.com/' } },
    },
  );

  await authApi.register({
    installation_id: 'test-installation',
    name: 'Browser',
    platform: 'android',
    email: 'test@example.com',
    display_name: 'Test',
    password: 'test-only-password',
  });
  assert.deepEqual(urls, ['https://api.example.com/api/auth/register']);
});

test('expired access token is renewed and the request is retried once', async () => {
  const tokens = [];
  const api = load(
    'src/services/api.ts',
    {
      'expo-file-system': { File: class {} },
      'expo-secure-store': {},
      'expo/fetch': { fetch: async () => assert.fail('Unexpected streaming request') },
      'react-native': { Platform: { OS: 'web' } },
    },
    {
      Headers,
      fetch: async (_url, options) => {
        const token = new Headers(options.headers).get('Authorization');
        tokens.push(token);
        return token === 'Bearer fresh'
          ? { ok: true, status: 200, json: async () => ({ id: 'user' }) }
          : {
              ok: false,
              status: 401,
              json: async () => ({ detail: 'Session invalide ou expirée.' }),
            };
      },
      process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example.com' } },
    },
  );
  let renewals = 0;
  api.setAccessTokenRenewer(async (expired) => {
    assert.equal(expired, 'expired');
    renewals += 1;
    return 'fresh';
  });

  assert.deepEqual(await api.authApi.me('expired'), { id: 'user' });
  assert.deepEqual(tokens, ['Bearer expired', 'Bearer fresh']);
  assert.equal(renewals, 1);
});

test('assistant stream renews an expired token without changing the message key', async () => {
  const requests = [];
  const api = load(
    'src/services/api.ts',
    {
      'expo-file-system': { File: class {} },
      'expo-secure-store': {},
      'expo/fetch': {
        fetch: async (url, options) => {
          requests.push({ url, headers: new Headers(options.headers), body: options.body });
          if (requests.length === 1) {
            return {
              status: 401,
              json: async () => ({ detail: 'Session invalide ou expirée.' }),
            };
          }
          const chunks = [new TextEncoder().encode('event: complete\ndata: {"id":"reply-1"}\n\n')];
          return {
            ok: true,
            status: 200,
            body: {
              getReader: () => ({
                read: async () =>
                  chunks.length ? { value: chunks.shift(), done: false } : { done: true },
              }),
            },
          };
        },
      },
      'react-native': { Platform: { OS: 'web' } },
    },
    {
      fetch: async () => assert.fail('Unexpected JSON request'),
      TextDecoder,
      process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example.com' } },
    },
  );
  let renewals = 0;
  api.setAccessTokenRenewer(async (expired) => {
    assert.equal(expired, 'expired');
    renewals += 1;
    return 'fresh';
  });

  const reply = await api.assistantApi.streamChat('expired', 'Bonjour', {}, undefined, 'message-1');
  assert.equal(reply.id, 'reply-1');
  assert.equal(renewals, 1);
  assert.equal(requests.length, 2);
  assert.ok(requests.every(({ url }) => url.endsWith('/api/assistant/chat/stream')));
  assert.ok(
    requests.every(({ headers }) => headers.get('X-Assistant-Idempotency-Key') === 'message-1'),
  );
  assert.deepEqual(
    requests.map(({ headers }) => headers.get('Authorization')),
    ['Bearer expired', 'Bearer fresh'],
  );
  assert.equal(requests[0].body, requests[1].body);
});

test('passkey login challenge does not require an email address', async () => {
  let body;
  const { authApi } = load(
    'src/services/api.ts',
    {
      'expo-file-system': { File: class {} },
      'expo-secure-store': {},
      'expo/fetch': { fetch: async () => assert.fail('Unexpected streaming request') },
      'react-native': { Platform: { OS: 'web' } },
    },
    {
      fetch: async (_url, options) => {
        body = options.body;
        return { ok: true, status: 200, json: async () => ({ challenge_id: 'test' }) };
      },
      process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example.com' } },
    },
  );
  await authApi.passkeyLoginOptions();
  assert.equal(body, '{}');
});

test('native audio is read through File and only API URLs use fetch', async () => {
  const urls = [];
  const bytes = new Uint8Array([1, 2, 3]).buffer;
  class File {
    exists = true;
    size = 3;
    constructor(uri) {
      assert.equal(uri, 'file:///voice.m4a');
    }
    async arrayBuffer() {
      return bytes;
    }
  }
  const api = apiFor('android', File, async (url, options) => {
    urls.push(url);
    if (url.endsWith('/transcriptions')) {
      assert.equal(options.body, bytes);
      assert.equal(new Headers(options.headers).get('Content-Type'), 'audio/mp4');
    }
    return { ok: true, status: 200, json: async () => ({ text: 'Bonjour' }) };
  });
  assert.equal(
    (await api.transcribeVoice('token', 'file:///voice.m4a', 'audio/mp4')).text,
    'Bonjour',
  );
  assert.equal(urls.length, 2);
  assert.ok(urls.every((url) => url.startsWith('http://localhost:8002/api/')));
});

test('missing native recording never grants consent or sends audio', async () => {
  const api = apiFor(
    'ios',
    class {
      exists = false;
    },
    () => assert.fail('Unexpected network'),
  );
  await assert.rejects(api.transcribeVoice('token', 'file:///missing', 'audio/mp4'), /introuvable/);
});

test('oversized native recording is rejected before reading into memory', async () => {
  const api = apiFor(
    'android',
    class {
      exists = true;
      size = 9 * 1024 * 1024;
      arrayBuffer() {
        assert.fail('Unexpected read');
      }
    },
    () => assert.fail('Unexpected network'),
  );
  await assert.rejects(api.transcribeVoice('token', 'file:///large', 'audio/mp4'), /long/);
});

function biometric(platform = 'android', overrides = {}) {
  const stored = new Map();
  const enrolled = [];
  const auth = {
    hasHardwareAsync: async () => true,
    isEnrolledAsync: async () => true,
    supportedAuthenticationTypesAsync: async () => [1],
    getEnrolledLevelAsync: async () => 3,
    AuthenticationType: { FINGERPRINT: 1, FACIAL_RECOGNITION: 2 },
    SecurityLevel: { BIOMETRIC_STRONG: 3 },
    authenticateAsync: async () => ({ success: true }),
    ...overrides,
  };
  const service = load('src/services/development-biometric.ts', {
    'expo-crypto': { randomUUID: () => `credential-${stored.size}` },
    'expo-constants': {
      __esModule: true,
      default: { executionEnvironment: 'store' },
      ExecutionEnvironment: { StoreClient: 'store' },
    },
    'expo-local-authentication': auth,
    'expo-secure-store': {
      getItemAsync: async (key) => stored.get(key),
      setItemAsync: async (key, value) => stored.set(key, value),
    },
    'react-native': { Platform: { OS: platform } },
    '@/src/services/api': {
      secretApi: { enrollDevelopmentBiometric: async (...args) => enrolled.push(args) },
    },
  });
  return { service, stored, enrolled };
}

test('Face ID in Expo Go explains installed-build requirement', async () => {
  const { service } = biometric('ios', { supportedAuthenticationTypesAsync: async () => [2] });
  await assert.rejects(service.hasDevelopmentBiometricCredential(), /Face ID.*Expo Go/);
});

test('weak Android biometric is rejected without reducing security level', async () => {
  const { service } = biometric('android', { getEnrolledLevelAsync: async () => 2 });
  await assert.rejects(service.hasDevelopmentBiometricCredential(), /biométrie forte/);
});

test('biometric cancellation never enrolls or reads a credential', async () => {
  const { service, enrolled, stored } = biometric('android', {
    authenticateAsync: async () => ({ success: false, error: 'user_cancel' }),
  });
  await assert.rejects(service.authenticateDevelopmentBiometric('token', 'user'), /annulée/);
  assert.equal(enrolled.length, 0);
  assert.equal(stored.size, 0);
});

test('credentials remain separate per account and existing account reuses its credential', async () => {
  const { service, enrolled } = biometric();
  const first = await service.authenticateDevelopmentBiometric('token1', 'user1');
  const second = await service.authenticateDevelopmentBiometric('token2', 'user2');
  assert.notEqual(first, second);
  assert.equal(await service.authenticateDevelopmentBiometric('token1', 'user1'), first);
  assert.equal(enrolled.length, 2);
});

function androidBiometricLogin(overrides = {}) {
  const stored = new Map();
  const auth = {
    hasHardwareAsync: async () => true,
    isEnrolledAsync: async () => true,
    getEnrolledLevelAsync: async () => 3,
    SecurityLevel: { BIOMETRIC_STRONG: 3 },
    authenticateAsync: async () => ({ success: true }),
    ...overrides,
  };
  const service = load('src/services/android-biometric-login.ts', {
    'expo-local-authentication': auth,
    'expo-secure-store': {
      getItemAsync: async (key) => stored.get(key) ?? null,
      setItemAsync: async (key, value) => stored.set(key, value),
      deleteItemAsync: async (key) => stored.delete(key),
    },
    'react-native': { Platform: { OS: 'android' } },
  });
  return { service, stored };
}

test('Android session reopen is enabled only after a strong biometric succeeds', async () => {
  const { service } = androidBiometricLogin();
  assert.equal(await service.isAndroidBiometricLoginEnabled(), false);
  await service.enableAndroidBiometricLogin();
  assert.equal(await service.isAndroidBiometricLoginEnabled(), true);
  await service.disableAndroidBiometricLogin();
  assert.equal(await service.isAndroidBiometricLoginEnabled(), false);
});

test('Android cancellation or weak biometrics cannot enable session reopening', async () => {
  const cancelled = androidBiometricLogin({
    authenticateAsync: async () => ({ success: false, error: 'user_cancel' }),
  });
  await assert.rejects(cancelled.service.enableAndroidBiometricLogin(), /annulée/);
  assert.equal(await cancelled.service.isAndroidBiometricLoginEnabled(), false);
  const weak = androidBiometricLogin({ getEnrolledLevelAsync: async () => 2 });
  await assert.rejects(weak.service.enableAndroidBiometricLogin(), /biométrie forte/);
  assert.equal(await weak.service.isAndroidBiometricLoginEnabled(), false);
});

test('Expo Go Android uses the development biometric path; installed Android uses the protected path', () => {
  const { secretBiometricMode } = load('src/services/secret-biometric-mode.ts');
  assert.equal(secretBiometricMode('android', true), 'development');
  assert.equal(secretBiometricMode('android', false), 'android');
  assert.equal(secretBiometricMode('web', true), 'none');
});

test('secret biometric credential is protected on device and enrolled after password proof', async () => {
  const stored = new Map();
  const calls = [];
  const service = load('src/services/android-secret-biometric.ts', {
    'expo-crypto': { getRandomBytesAsync: async () => new Uint8Array(32).fill(7) },
    'expo-secure-store': {
      getItemAsync: async (key, options) => {
        calls.push(['read', key, options?.requireAuthentication ?? false]);
        return stored.get(key) ?? null;
      },
      setItemAsync: async (key, value, options) => {
        calls.push(['write', key, options?.requireAuthentication ?? false]);
        stored.set(key, value);
      },
      deleteItemAsync: async (key) => stored.delete(key),
    },
    'react-native': { Platform: { OS: 'android' } },
    '@/src/services/android-biometric-login': { canUseAndroidBiometrics: async () => true },
    '@/src/services/api': {
      ApiError: class ApiError extends Error {},
      secretApi: {
        enrollAndroidBiometric: async (...args) => calls.push(['enroll', ...args]),
        unlockWithAndroidBiometric: async (...args) => {
          calls.push(['unlock', ...args]);
          return { secret_access_token: 'secret' };
        },
      },
    },
  });
  assert.equal(await service.hasAndroidSecretBiometric('user'), false);
  await service.enrollAndroidSecretBiometric('access', 'user', 'password');
  assert.equal(await service.hasAndroidSecretBiometric('user'), true);
  assert.ok(
    calls.some(
      ([kind, key, protectedByBiometrics]) =>
        kind === 'write' &&
        key === 'cocoon.secret-biometric-credential.user' &&
        protectedByBiometrics,
    ),
  );
  assert.ok(
    calls.some(
      ([kind, token, password]) =>
        kind === 'enroll' && token === 'access' && password === 'password',
    ),
  );
  assert.equal(
    (await service.unlockWithAndroidSecretBiometric('access', 'user')).secret_access_token,
    'secret',
  );
  assert.ok(
    calls.some(
      ([kind, key, protectedByBiometrics]) =>
        kind === 'read' &&
        key === 'cocoon.secret-biometric-credential.user' &&
        protectedByBiometrics,
    ),
  );
});

test('secret biometric cancellation never sends a credential to the API', async () => {
  let sent = false;
  const service = load('src/services/android-secret-biometric.ts', {
    'expo-crypto': {},
    'expo-secure-store': {
      getItemAsync: async () => {
        throw new Error('cancelled');
      },
    },
    'react-native': { Platform: { OS: 'android' } },
    '@/src/services/android-biometric-login': { canUseAndroidBiometrics: async () => true },
    '@/src/services/api': {
      ApiError: class ApiError extends Error {},
      secretApi: {
        unlockWithAndroidBiometric: async () => {
          sent = true;
        },
      },
    },
  });
  await assert.rejects(service.unlockWithAndroidSecretBiometric('access', 'user'), /annulée/);
  assert.equal(sent, false);
});

test('session bootstrap waits for biometric confirmation before refreshing', async () => {
  let refreshRead = false;
  let state;
  const store = load('src/stores/session-store.ts', {
    zustand: {
      create: (initialize) => {
        state = initialize(
          (change) => Object.assign(state, change),
          () => state,
        );
        return state;
      },
    },
    '@/src/services/android-biometric-login': {
      isAndroidBiometricLoginEnabled: async () => true,
      disableAndroidBiometricLogin: async () => undefined,
    },
    '@/src/services/notifications': {
      unsubscribeCurrentWebPush: async () => undefined,
    },
    '@/src/services/api': {
      loadRefreshToken: async () => {
        refreshRead = true;
        return 'refresh-token';
      },
      clearRefreshToken: async () => undefined,
      setAccessTokenRenewer: () => undefined,
    },
  }).useSessionStore;
  await store.restore();
  assert.equal(refreshRead, false);
  assert.equal(store.initialized, true);
  assert.equal(store.accessToken, null);
});

test('session restore uses the fresh token profile and supports older API responses', async () => {
  for (const withProfile of [true, false]) {
    let state;
    let meCalls = 0;
    let saved = null;
    const profile = { id: 'user', enable_assistant: false, is_superadmin: false };
    const store = load('src/stores/session-store.ts', {
      zustand: {
        create: (initialize) => {
          state = initialize(
            (change) => Object.assign(state, change),
            () => state,
          );
          return state;
        },
      },
      '@/src/services/android-biometric-login': {
        isAndroidBiometricLoginEnabled: async () => false,
      },
      '@/src/services/notifications': {
        unsubscribeCurrentWebPush: async () => undefined,
      },
      '@/src/services/api': {
        ApiError: class ApiError extends Error {},
        loadRefreshToken: async () => 'old-refresh',
        saveRefreshToken: async (token) => {
          saved = token;
        },
        setAccessTokenRenewer: () => undefined,
        authApi: {
          refresh: async () => ({
            access_token: 'new-access',
            refresh_token: 'new-refresh',
            ...(withProfile ? { user: profile } : {}),
          }),
          me: async () => {
            meCalls += 1;
            return profile;
          },
        },
      },
    }).useSessionStore;
    await store.restore();
    assert.equal(saved, 'new-refresh');
    assert.equal(store.initialized, true);
    assert.equal(store.user, profile);
    assert.equal(store.accessToken, 'new-access');
    assert.equal(meCalls, withProfile ? 0 : 1);
  }
});

test('a delayed session restore cannot replace a newer login', async () => {
  let state;
  let releaseRestore;
  let refreshStarted;
  const started = new Promise((resolve) => (refreshStarted = resolve));
  const restored = new Promise((resolve) => (releaseRestore = resolve));
  let savedToken = 'old-refresh';
  const store = load('src/stores/session-store.ts', {
    zustand: {
      create: (initialize) => {
        state = initialize(
          (change) => Object.assign(state, change),
          () => state,
        );
        return state;
      },
    },
    '@/src/services/android-biometric-login': {
      isAndroidBiometricLoginEnabled: async () => false,
    },
    '@/src/services/notifications': { unsubscribeCurrentWebPush: async () => undefined },
    '@/src/services/api': {
      ApiError: class ApiError extends Error {},
      loadRefreshToken: async () => 'old-refresh',
      saveRefreshToken: async (value) => (savedToken = value),
      setAccessTokenRenewer: () => undefined,
      authApi: {
        refresh: async () => {
          refreshStarted();
          return restored;
        },
      },
    },
  }).useSessionStore;

  const restoring = store.restore();
  await started;
  await store.start({
    access_token: 'access-b',
    refresh_token: 'refresh-b',
    user: { id: 'account-b' },
  });
  releaseRestore({
    access_token: 'access-a',
    refresh_token: 'refresh-a',
    user: { id: 'account-a' },
  });
  await restoring;
  assert.equal(store.user.id, 'account-b');
  assert.equal(store.accessToken, 'access-b');
  assert.equal(savedToken, 'refresh-b');
});

test('a delayed logout cannot erase a newer login', async () => {
  let state;
  let releaseLogout;
  let logoutStarted;
  const started = new Promise((resolve) => (logoutStarted = resolve));
  const loggedOut = new Promise((resolve) => (releaseLogout = resolve));
  let storedToken = 'refresh-a';
  const store = load('src/stores/session-store.ts', {
    zustand: {
      create: (initialize) => {
        state = initialize(
          (change) => Object.assign(state, change),
          () => state,
        );
        return state;
      },
    },
    '@/src/services/android-biometric-login': {
      disableAndroidBiometricLogin: async () => undefined,
    },
    '@/src/services/notifications': { unsubscribeCurrentWebPush: async () => undefined },
    '@/src/services/api': {
      clearRefreshToken: async () => (storedToken = null),
      saveRefreshToken: async (value) => (storedToken = value),
      setAccessTokenRenewer: () => undefined,
      authApi: {
        logout: async () => {
          logoutStarted();
          await loggedOut;
        },
      },
    },
  }).useSessionStore;
  state.accessToken = 'access-a';
  state.user = { id: 'account-a' };

  const signingOut = store.end();
  await started;
  await store.start({
    access_token: 'access-b',
    refresh_token: 'refresh-b',
    user: { id: 'account-b' },
  });
  releaseLogout();
  await signingOut;
  assert.equal(store.user.id, 'account-b');
  assert.equal(store.accessToken, 'access-b');
  assert.equal(storedToken, 'refresh-b');
});

test('expired refresh token clears the session for login and passkey recovery', async () => {
  let state;
  let cleared = false;
  class ApiError extends Error {
    status = 401;
  }
  const store = load('src/stores/session-store.ts', {
    zustand: {
      create: (initialize) => {
        state = initialize(
          (change) => Object.assign(state, change),
          () => state,
        );
        return state;
      },
    },
    '@/src/services/android-biometric-login': {
      isAndroidBiometricLoginEnabled: async () => false,
    },
    '@/src/services/notifications': {
      unsubscribeCurrentWebPush: async () => undefined,
    },
    '@/src/services/api': {
      ApiError,
      loadRefreshToken: async () => 'expired-refresh',
      clearRefreshToken: async () => {
        cleared = true;
      },
      authApi: {
        refresh: async () => {
          throw new ApiError('expired');
        },
      },
      setAccessTokenRenewer: () => undefined,
    },
  }).useSessionStore;

  await store.restore();
  assert.equal(cleared, true);
  assert.equal(store.initialized, true);
  assert.equal(store.user, null);
  assert.equal(store.sessionExpired, true);
});

test('concurrent expired requests share one refresh token rotation', async () => {
  let renewer;
  let refreshes = 0;
  const store = load('src/stores/session-store.ts', {
    zustand: {
      create: (initialize) => {
        const state = {};
        Object.assign(
          state,
          initialize(
            (change) => Object.assign(state, change),
            () => state,
          ),
        );
        state.getState = () => state;
        state.setState = (change) => Object.assign(state, change);
        return state;
      },
    },
    '@/src/services/android-biometric-login': {},
    '@/src/services/notifications': {
      unsubscribeCurrentWebPush: async () => undefined,
    },
    '@/src/services/api': {
      ApiError: class ApiError extends Error {},
      setAccessTokenRenewer: (callback) => {
        renewer = callback;
      },
      loadRefreshToken: async () => 'refresh-old',
      saveRefreshToken: async () => undefined,
      authApi: {
        refresh: async () => {
          refreshes += 1;
          await new Promise((resolve) => setTimeout(resolve, 1));
          return { access_token: 'fresh', refresh_token: 'refresh-fresh' };
        },
      },
    },
  }).useSessionStore;
  store.setState({ accessToken: 'expired' });

  assert.deepEqual(await Promise.all([renewer('expired'), renewer('expired')]), ['fresh', 'fresh']);
  assert.equal(refreshes, 1);
  assert.equal(store.accessToken, 'fresh');
  assert.equal(await renewer('token-from-another-session'), null);
});

test('a delayed token renewal cannot replace a newer login', async () => {
  let renewer;
  let releaseRefresh;
  let refreshStarted;
  let storedToken = 'refresh-a';
  const started = new Promise((resolve) => (refreshStarted = resolve));
  const refreshed = new Promise((resolve) => (releaseRefresh = resolve));
  const store = load('src/stores/session-store.ts', {
    zustand: {
      create: (initialize) => {
        const state = {};
        Object.assign(
          state,
          initialize(
            (change) => Object.assign(state, change),
            () => state,
          ),
        );
        state.getState = () => state;
        state.setState = (change) => Object.assign(state, change);
        return state;
      },
    },
    '@/src/services/android-biometric-login': {},
    '@/src/services/notifications': { unsubscribeCurrentWebPush: async () => undefined },
    '@/src/services/api': {
      ApiError: class ApiError extends Error {},
      setAccessTokenRenewer: (callback) => (renewer = callback),
      loadRefreshToken: async () => storedToken,
      saveRefreshToken: async (value) => (storedToken = value),
      authApi: {
        refresh: async () => {
          refreshStarted();
          return refreshed;
        },
      },
    },
  }).useSessionStore;
  store.setState({ accessToken: 'access-a', user: { id: 'account-a' } });

  const oldRenewal = renewer('access-a');
  await started;
  await store.start({
    access_token: 'access-b',
    refresh_token: 'refresh-b',
    user: { id: 'account-b' },
  });
  releaseRefresh({ access_token: 'access-a-new', refresh_token: 'refresh-a-new' });
  assert.equal(await oldRenewal, null);
  assert.equal(store.user.id, 'account-b');
  assert.equal(store.accessToken, 'access-b');
  assert.equal(storedToken, 'refresh-b');
});

test('a stale logout cannot unsubscribe a new web push subscription', async () => {
  let releaseRegistration;
  const registrationReady = new Promise((resolve) => (releaseRegistration = resolve));
  let unsubscribed = false;
  const { unsubscribeCurrentWebPush } = load(
    'src/services/notifications.ts',
    {
      'expo-constants': { appOwnership: 'standalone' },
      'react-native': { Platform: { OS: 'web' } },
      '@/src/services/api': {},
    },
    {
      navigator: {
        serviceWorker: {
          getRegistration: async () => {
            await registrationReady;
            return {
              pushManager: {
                getSubscription: async () => ({ unsubscribe: async () => (unsubscribed = true) }),
              },
            };
          },
        },
      },
    },
  );
  let current = true;
  const oldLogout = unsubscribeCurrentWebPush(() => current);
  current = false;
  releaseRegistration();
  await oldLogout;
  assert.equal(unsubscribed, false);
});

test('one button: short tap sends; hold only reports unavailable transcription', () => {
  const calls = [];
  const { VoiceCapture } = load('features/assistant/voice-capture.tsx', {
    react: { useRef: (current) => ({ current }) },
    'react-native': {
      Text: 'span',
      ActivityIndicator: 'progress',
      StyleSheet: { create: (styles) => styles },
    },
    '@/src/components/audited-pressable': { AuditedPressable: 'button' },
    '@/src/services/ui-audit': { reportButtonPress: () => undefined },
    '@/src/theme': { darkTheme: { colors: { ink: '#fff' } } },
  });
  const button = VoiceCapture({
    accessToken: 'token',
    colors: {},
    hasText: true,
    onSend: () => calls.push('send'),
    onError: (message) => calls.push(message),
  });
  assert.equal(button.type, 'button');
  button.props.onPressIn();
  button.props.onPress();
  assert.deepEqual(calls, ['send']);
  calls.length = 0;
  button.props.onPressIn();
  button.props.onLongPress();
  button.props.onPress();
  assert.deepEqual(calls, ['Transcription audio indisponible.']);
});
