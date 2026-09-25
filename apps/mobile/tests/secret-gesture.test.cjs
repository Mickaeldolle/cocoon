/* global __dirname */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function loadHook(platform) {
  const filename = path.join(__dirname, '..', 'src/hooks/use-secret-gesture.ts');
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  const effects = [];
  const listeners = new Map();
  class FakeNode {}
  class FakeElement extends FakeNode {
    constructor(interactive = false) {
      super();
      this.interactive = interactive;
      this.style = { userSelect: '' };
    }

    contains(target) {
      return target instanceof FakeNode;
    }

    closest() {
      return this.interactive ? this : null;
    }
  }
  const document = {
    addEventListener: (type, listener) => listeners.set(type, listener),
    removeEventListener: (type, listener) => {
      if (listeners.get(type) === listener) listeners.delete(type);
    },
  };
  const hooks = {
    useCallback: (callback) => callback,
    useEffect: (effect) => effects.push(effect),
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
              Platform: { OS: platform },
              PanResponder: {
                create: (config) => ({ panHandlers: config }),
              },
            },
      Date,
      document,
      Node: FakeNode,
      Element: FakeElement,
      Math,
    },
    { filename },
  );

  return {
    useSecretGesture: module.exports.useSecretGesture,
    FakeElement,
    commit: () => effects.map((effect) => effect()).filter(Boolean),
    dispatch: (type, event) => listeners.get(type)?.(event),
  };
}

test('the shared responder recognizes three separate strokes before opening secret access', () => {
  const { useSecretGesture } = loadHook('ios');
  let opened = 0;
  const handlers = useSecretGesture(() => {
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

test('web gestures work on the home area while controls and clicks are ignored', () => {
  const { useSecretGesture, FakeElement, commit, dispatch } = loadHook('web');
  let opened = 0;
  const handlers = useSecretGesture(() => {
    opened += 1;
  });
  const area = new FakeElement();
  const content = new FakeElement();
  const control = new FakeElement(true);
  handlers.ref.current = area;
  const [cleanup] = commit();
  const stroke = (startX, startY, endX, endY, target = content) => {
    dispatch('pointerdown', {
      pointerType: 'mouse', button: 0, pointerId: 1, clientX: startX, clientY: startY, target,
    });
    assert.equal(area.style.userSelect, target === control ? '' : 'none');
    dispatch('pointerup', {
      pointerId: 1, clientX: endX, clientY: endY,
    });
    assert.equal(area.style.userSelect, '');
  };
  stroke(100, 100, 110, 100);
  stroke(100, 100, 180, 100, control);
  stroke(100, 100, 180, 100);
  stroke(100, 100, 180, 100);
  assert.equal(opened, 0);
  stroke(100, 180, 100, 100);
  assert.equal(opened, 1);
  cleanup();
  dispatch('pointerdown', { pointerType: 'mouse', button: 0, pointerId: 1, clientX: 100, clientY: 100, target: content });
  assert.equal(area.style.userSelect, '');
  assert.equal(opened, 1);
});

test('touch strokes use the web capture listeners', () => {
  const { useSecretGesture, FakeElement, commit, dispatch } = loadHook('web');
  let opened = 0;
  const handlers = useSecretGesture(() => { opened += 1; });
  handlers.ref.current = new FakeElement();
  commit();
  const target = new FakeElement();
  const stroke = (x1, y1, x2, y2) => {
    dispatch('touchstart', { target, changedTouches: [{ identifier: 1, clientX: x1, clientY: y1 }] });
    dispatch('touchend', { changedTouches: [{ identifier: 1, clientX: x2, clientY: y2 }] });
  };
  stroke(100, 100, 180, 100);
  stroke(100, 100, 180, 100);
  stroke(100, 180, 100, 100);
  assert.equal(opened, 1);
});
