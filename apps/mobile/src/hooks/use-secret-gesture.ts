import { useCallback, useMemo, useRef } from 'react';
import { PanResponder } from 'react-native';

type Direction = 'right' | 'up';

const expected: readonly Direction[] = ['right', 'right', 'up'];
const recognitionDistance = 64;
const captureDistance = 24;
const sequenceWindowMs = 3_000;

function directionFromDelta(
  deltaX: number,
  deltaY: number,
  minimumDistance: number,
): Direction | null {
  const absoluteX = Math.abs(deltaX);
  const absoluteY = Math.abs(deltaY);
  if (absoluteX >= minimumDistance && absoluteX > absoluteY * 1.25) {
    return deltaX > 0 ? 'right' : null;
  }
  if (absoluteY >= minimumDistance && absoluteY > absoluteX * 1.25 && deltaY < 0) {
    return 'up';
  }
  return null;
}

/** Recognises → → ↑ with the responder shared by native and web. */
export function useSecretGesture(onRecognized: () => void) {
  const index = useRef(0);
  const startedAt = useRef<number | null>(null);

  const reset = useCallback(() => {
    index.current = 0;
    startedAt.current = null;
  }, []);

  const record = useCallback(
    (direction: Direction | null) => {
      const now = Date.now();
      if (
        !direction ||
        (startedAt.current !== null && now - startedAt.current > sequenceWindowMs)
      ) {
        reset();
        return;
      }
      if (direction !== expected[index.current]) {
        reset();
        return;
      }
      if (index.current === 0) startedAt.current = now;
      index.current += 1;
      if (index.current === expected.length) {
        reset();
        onRecognized();
      }
    },
    [onRecognized, reset],
  );

  // PanResponder.create retains these callbacks; it does not run them during render.
  /* eslint-disable react-hooks/refs, react-hooks/purity -- Gesture callbacks run after render. */
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponderCapture: (_, gesture) => {
          const direction = directionFromDelta(gesture.dx, gesture.dy, captureDistance);
          if (!direction) return false;
          if (startedAt.current !== null && Date.now() - startedAt.current > sequenceWindowMs) {
            reset();
          }
          if (direction !== expected[index.current]) {
            reset();
            return false;
          }
          return true;
        },
        onPanResponderRelease: (_, gesture) =>
          record(directionFromDelta(gesture.dx, gesture.dy, recognitionDistance)),
        onPanResponderTerminate: reset,
        onStartShouldSetPanResponder: () => false,
      }),
    [record, reset],
  );
  /* eslint-enable react-hooks/refs, react-hooks/purity */

  return panResponder.panHandlers;
}
