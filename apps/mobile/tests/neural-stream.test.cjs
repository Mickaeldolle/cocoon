/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function loadNeuralApi(fetch) {
  const filename = path.join(__dirname, '..', 'src/services/neural-api.ts');
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(
    source,
    {
      module,
      exports: module.exports,
      require,
      TextDecoder,
      Date,
      Math,
      Error,
    },
    { filename },
  );
  class ApiError extends Error {
    constructor(status, message) {
      super(message);
      this.status = status;
    }
  }
  return module.exports.createNeuralApi(
    async () => {
      throw new Error('Le transport JSON ne doit pas être appelé.');
    },
    (token, options = {}) => ({ ...options, headers: { Authorization: `Bearer ${token}` } }),
    (route, options) => fetch(`https://api.example.test${route}`, options),
    ApiError,
  );
}

function streamResponse(text) {
  const chunks = [new TextEncoder().encode(text)];
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => (chunks.length ? { value: chunks.shift(), done: false } : { done: true }),
      }),
    },
  };
}

test('capture stream resumes after a cut with the same key and the last event cursor', async () => {
  const requests = [];
  const api = loadNeuralApi(async (url, options) => {
    requests.push({ url, options });
    return requests.length === 1
      ? streamResponse('id: 7\nevent: progress\ndata: {"stage":"understand","text":"En cours"}\n\n')
      : streamResponse('id: 8\nevent: complete\ndata: {"id":"capture-1","run_id":"run-1"}\n\n');
  });
  const progress = [];
  const result = await api.streamCapture(
    'token',
    'Retenir ma décision',
    'Europe/Paris',
    { onProgress: (event) => progress.push(event.text) },
    undefined,
    { idempotencyKey: 'request-1' },
  );

  assert.equal(result.id, 'capture-1');
  assert.deepEqual(progress, ['En cours']);
  assert.equal(requests.length, 2);
  assert.ok(requests.every(({ url }) => url === 'https://api.example.test/api/captures/stream'));
  assert.ok(
    requests.every(({ options }) => options.headers['X-Capture-Idempotency-Key'] === 'request-1'),
  );
  assert.ok(requests.every(({ options }) => options.headers.Authorization === 'Bearer token'));
  assert.equal(requests[0].options.headers['Last-Event-ID'], undefined);
  assert.equal(requests[1].options.headers['Last-Event-ID'], '7');
});
