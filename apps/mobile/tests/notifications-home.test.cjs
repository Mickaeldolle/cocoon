/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const filename = path.join(__dirname, '..', 'src/services/notifications.ts');
const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
}).outputText;
const moduleRef = { exports: {} };
vm.runInNewContext(source, {
  module: moduleRef,
  exports: moduleRef.exports,
  require: (name) => {
    if (name === 'expo-constants')
      return { __esModule: true, default: { appOwnership: 'standalone' } };
    if (name === 'react-native') return { Platform: { OS: 'web' } };
    if (name === '@/src/services/api') return { authApi: {} };
    throw new Error(`Unexpected module: ${name}`);
  },
});

const { homePushAction } = moduleRef.exports;

test('home never reactivates a push consent the user revoked', () => {
  const revoked = [{ policy_key: 'notifications.push', revoked_at: '2026-10-05T00:00:00Z' }];
  assert.equal(homePushAction(revoked, 'granted', 'web'), 'skip');
  assert.equal(homePushAction(revoked, 'prompt', 'android'), 'skip');
});

test('home requires Cocoon consent before enrolling a device', () => {
  const active = [{ policy_key: 'notifications.push', revoked_at: null }];
  assert.equal(homePushAction([], 'granted', 'web'), 'offer');
  assert.equal(homePushAction([], 'prompt', 'android'), 'offer');
  assert.equal(homePushAction([], 'prompt', 'web'), 'offer');
  assert.equal(homePushAction(active, 'granted', 'web'), 'register');
  assert.equal(homePushAction(active, 'prompt', 'android'), 'register');
  assert.equal(homePushAction(active, 'prompt', 'web'), 'offer');
  assert.equal(homePushAction([], 'denied', 'web'), 'blocked');
  assert.equal(homePushAction([], 'unsupported', 'android'), 'skip');
});
