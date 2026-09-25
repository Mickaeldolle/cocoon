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
      require: (name) => (Object.hasOwn(mocks, name) ? mocks[name] : require(name)),
      setTimeout,
      clearTimeout,
      AbortController,
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
      assert.equal(options.headers['Content-Type'], 'audio/mp4');
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

test('one button: short tap sends; hold only reports unavailable transcription', () => {
  const calls = [];
  const { VoiceCapture } = load('features/assistant/voice-capture.tsx', {
    react: { useRef: (current) => ({ current }) },
    'react-native': {
      Pressable: 'button',
      Text: 'span',
      ActivityIndicator: 'progress',
      StyleSheet: { create: (styles) => styles },
    },
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
