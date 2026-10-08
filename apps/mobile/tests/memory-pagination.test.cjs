/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

test('personal memories request successive API pages with the authenticated token', async () => {
  const personalFilename = path.join(__dirname, '..', 'src/services/personal-api.ts');
  const personalSource = ts.transpileModule(readFileSync(personalFilename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const personalModule = { exports: {} };
  vm.runInNewContext(
    personalSource,
    {
      module: personalModule,
      exports: personalModule.exports,
    },
    { filename: personalFilename },
  );
  const filename = path.join(__dirname, '..', 'src/services/api.ts');
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const requests = [];
  const moduleRef = { exports: {} };
  const fetch = async (url, options) => {
    requests.push({ url, authorization: new Headers(options.headers).get('Authorization') });
    const offset = Number(new URL(url).searchParams.get('offset'));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        memories: [{ id: String(offset) }],
        next_offset: offset < 100 ? offset + 50 : null,
      }),
    };
  };
  vm.runInNewContext(
    source,
    {
      module: moduleRef,
      exports: moduleRef.exports,
      require: (name) => {
        if (name === './personal-api') return personalModule.exports;
        if (name === './neural-api') return { createNeuralApi: () => ({}) };
        if (name === 'expo-file-system') return { File: class {} };
        if (name === 'expo-secure-store') return {};
        if (name === 'expo/fetch') return { fetch };
        if (name === 'react-native') return { Platform: { OS: 'web' } };
        return require(name);
      },
      fetch,
      AbortController,
      setTimeout,
      clearTimeout,
      Headers,
      URL,
      process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example.test' } },
      __DEV__: true,
    },
    { filename },
  );

  const { personalApi } = moduleRef.exports;
  const first = await personalApi.listMemories('token', 50);
  const second = await personalApi.listMemories('token', 50, first.next_offset);
  const third = await personalApi.listMemories('token', 50, second.next_offset);

  assert.equal(third.next_offset, null);
  assert.deepEqual(
    requests.map(({ url }) => new URL(url).searchParams.get('offset')),
    ['0', '50', '100'],
  );
  assert.ok(requests.every(({ authorization }) => authorization === 'Bearer token'));
});
