/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const filename = path.join(__dirname, '..', 'src/services/pwa-install.ts');
const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function load({ platform = 'web', userAgent = 'Chrome', installed = false } = {}) {
  const events = new Map();
  const window = {
    addEventListener: (name, callback) => events.set(name, callback),
    matchMedia: () => ({ matches: installed }),
  };
  const navigator = { userAgent, maxTouchPoints: 0 };
  const moduleRef = { exports: {} };
  vm.runInNewContext(source, {
    module: moduleRef,
    exports: moduleRef.exports,
    require: () => ({ Platform: { OS: platform } }),
    window,
    navigator,
  });
  return { api: moduleRef.exports, events };
}

test('offers the browser installation only after it becomes available', async () => {
  const { api, events } = load();
  assert.equal(api.pwaInstallOffer(), 'unavailable');
  let prevented = false;
  let prompts = 0;
  events.get('beforeinstallprompt')({
    preventDefault: () => {
      prevented = true;
    },
    prompt: async () => {
      prompts += 1;
      return { outcome: 'accepted' };
    },
  });
  assert.equal(prevented, true);
  assert.equal(api.pwaInstallOffer(), 'prompt');
  assert.equal(await api.promptPwaInstall(), 'accepted');
  assert.equal(prompts, 1);
  assert.equal(api.pwaInstallOffer(), 'unavailable');
  await assert.rejects(api.promptPwaInstall());
});

test('already installed and native apps do not offer installation', () => {
  assert.equal(load({ installed: true }).api.pwaInstallOffer(), 'unavailable');
  assert.equal(load({ platform: 'android' }).api.pwaInstallOffer(), 'unavailable');
});

test('Safari on iPhone gets manual guidance', () => {
  const safari = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Safari/604.1';
  assert.equal(load({ userAgent: safari }).api.pwaInstallOffer(), 'ios');
});
