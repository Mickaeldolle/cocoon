/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

test('an assistant route binds its initial draft to the first account after session restore', () => {
  const filename = path.join(__dirname, '../app/assistant.tsx');
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  const moduleRef = { exports: {} };
  let account = null;
  let routeOwner;
  let initialized = false;
  vm.runInNewContext(source, {
    module: moduleRef,
    exports: moduleRef.exports,
    require: (name) => {
      if (name === 'react') {
        return {
          useState: (initial) => {
            if (!initialized) {
              routeOwner = initial;
              initialized = true;
            }
            return [routeOwner, (value) => (routeOwner = value)];
          },
        };
      }
      if (name === 'react/jsx-runtime') {
        return { jsx: (type, props, key) => ({ type, props, key }) };
      }
      if (name === 'react-native-markdown-display') {
        return {
          __esModule: true,
          default: () => null,
          MarkdownIt: () => ({ disable: () => ({}) }),
        };
      }
      if (name === '@/src/stores/session-store') {
        return { useSessionStore: (selector) => selector({ user: account }) };
      }
      return {};
    },
  });
  const screen = moduleRef.exports.default;

  assert.equal(screen(), null); // The direct link mounted before session restoration.
  account = { id: 'account-a' };
  assert.equal(screen(), null); // React schedules the guarded render update.
  const first = screen();
  assert.equal(first.key, 'account-a');
  assert.equal(first.props.initialAllowed, true);

  account = null;
  assert.equal(screen(), null);
  account = { id: 'account-b' };
  const second = screen();
  assert.equal(second.key, 'account-b');
  assert.equal(second.props.initialAllowed, false);
});
