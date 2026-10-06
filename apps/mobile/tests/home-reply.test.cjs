/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const { QueryClient } = require('@tanstack/react-query');

const source = ts.transpileModule(
  readFileSync(path.join(__dirname, '../features/assistant/home-reply.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
).outputText;
const result = { message: { id: 'reply', proposals: [] }, choices: ['Continuer'] };
function setup(api) {
  const moduleRef = { exports: {} };
  vm.runInNewContext(source, {
    module: moduleRef,
    exports: moduleRef.exports,
    require: () => ({ assistantApi: api }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { gcTime: 0 } } });
  return { ...moduleRef.exports, client };
}
function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const turn = { key: 'same-turn', text: 'Bonjour', retry: false };

test('home waits for the complete response and forwards the original idempotency key once', async () => {
  const stream = deferred();
  const started = deferred();
  const calls = [];
  const { client, requestHomeReply } = setup({
    freeModels: async () => ({
      available: true,
      default_model: 'free-model',
      models: [{ id: 'free-model' }],
    }),
    streamChat: (...args) => {
      calls.push(args);
      started.resolve();
      return stream.promise;
    },
  });
  const controller = new AbortController();
  let completed = false;
  const pending = requestHomeReply(client, 'token', 'owner', turn, controller.signal).then(
    (reply) => {
      completed = true;
      return reply;
    },
  );
  await started.promise;
  assert.equal(completed, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][3], controller.signal);
  assert.equal(calls[0][4], turn.key);
  assert.equal(calls[0][6], 'free-model');
  stream.resolve(result);
  assert.equal((await pending).result, result);
  client.clear();
});

test('cancellation while loading models prevents sending the message', async () => {
  const models = deferred();
  let sends = 0;
  const { client, requestHomeReply } = setup({
    freeModels: () => models.promise,
    streamChat: () => {
      sends += 1;
    },
  });
  const controller = new AbortController();
  const pending = requestHomeReply(client, 'token', 'owner', turn, controller.signal);
  controller.abort();
  models.resolve({ available: false });
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(sends, 0);
  client.clear();
});

test('a late response after cancellation cannot be handed to the conversation', async () => {
  const stream = deferred();
  const started = deferred();
  const { client, requestHomeReply } = setup({
    freeModels: async () => ({ available: false }),
    streamChat: () => {
      started.resolve();
      return stream.promise;
    },
  });
  const controller = new AbortController();
  const pending = requestHomeReply(client, 'token', 'owner', turn, controller.signal);
  await started.promise;
  controller.abort();
  stream.resolve(result);
  await assert.rejects(pending, { name: 'AbortError' });
  client.clear();
});

test('retry keeps the same key and uses the standard configured provider without a free catalog', async () => {
  const calls = [];
  const { client, requestHomeReply } = setup({
    freeModels: async () => ({ available: false }),
    streamChat: async (...args) => {
      calls.push(args);
      return result;
    },
  });
  await requestHomeReply(
    client,
    'token',
    'owner',
    { ...turn, retry: true },
    new AbortController().signal,
  );
  assert.equal(calls[0][4], turn.key);
  assert.equal(calls[0][5], true);
  assert.equal(calls[0][6], undefined);
  client.clear();
});

test('missing free models blocks sending, and completed handoffs are scoped to their owner', async () => {
  let sends = 0;
  const { client, requestHomeReply, homeReplyKey } = setup({
    freeModels: async () => ({ available: true, default_model: null, models: [] }),
    streamChat: () => {
      sends += 1;
    },
  });
  await assert.rejects(
    requestHomeReply(client, 'token', 'owner', turn, new AbortController().signal),
    /Aucun modèle/,
  );
  assert.equal(sends, 0);
  client.setQueryData(homeReplyKey('owner', turn.key), result);
  assert.equal(client.getQueryData(homeReplyKey('other-owner', turn.key)), undefined);
  client.clear();
});
