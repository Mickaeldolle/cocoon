/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

test('the shared responder recognizes three separate strokes before opening secret access', () => {
  const filename = path.join(__dirname, '..', 'src/hooks/use-secret-gesture.ts');
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  const hooks = {
    useCallback: (callback) => callback,
    useMemo: (factory) => factory(),
    useRef: (initial) => ({ current: initial }),
  };
  vm.runInNewContext(
    source,
    {
      module,
      exports: module.exports,
      require: (name) =>
        name === 'react'
          ? hooks
          : {
              PanResponder: {
                create: (config) => ({ panHandlers: config }),
              },
            },
      Date,
      Math,
    },
    { filename },
  );

  let opened = 0;
  const handlers = module.exports.useSecretGesture(() => {
    opened += 1;
  });
  const stroke = (dx, dy) => {
    const gesture = { dx, dy };
    assert.equal(handlers.onMoveShouldSetPanResponderCapture(null, gesture), true);
    handlers.onPanResponderRelease(null, gesture);
  };

  assert.equal(handlers.onMoveShouldSetPanResponderCapture(null, { dx: 0, dy: -80 }), false);
  stroke(80, 0);
  stroke(80, 0);
  assert.equal(opened, 0);
  stroke(0, -80);
  assert.equal(opened, 1);
  stroke(80, 0);
  handlers.onPanResponderRelease(null, { dx: 20, dy: 0 });
  assert.equal(opened, 1);
});
