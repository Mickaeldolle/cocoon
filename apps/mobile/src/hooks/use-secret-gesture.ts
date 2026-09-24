import { useCallback, useMemo, useRef } from 'react';
import { PanResponder, Platform } from 'react-native';

type Direction = 'right' | 'up';

type PointerEventLike = {
  nativeEvent?: { pageX?: number; pageY?: number };
  pageX?: number;
  pageY?: number;
};

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

function pointFrom(event: PointerEventLike) {
  const source = event.nativeEvent ?? event;
  return { x: source.pageX ?? 0, y: source.pageY ?? 0 };
}

/** Recognises → → ↑ using the native responder, while preserving ordinary vertical scrolling. */
export function useSecretGesture(onRecognized: () => void) {
  const index = useRef(0);
  const startedAt = useRef<number | null>(null);
  const browserStart = useRef<{ x: number; y: number } | null>(null);

  const reset = useCallback(() => {
    index.current = 0;
    startedAt.current = null;
    browserStart.current = null;
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

  const onPointerDown = useCallback((event: PointerEventLike) => {
    browserStart.current = pointFrom(event);
  }, []);

  const onPointerUp = useCallback(
    (event: PointerEventLike) => {
      const start = browserStart.current;
      browserStart.current = null;
      if (!start) return;
      const end = pointFrom(event);
      record(directionFromDelta(end.x - start.x, end.y - start.y, recognitionDistance));
    },
    [record],
  );

  if (Platform.OS === 'web') return { onPointerDown, onPointerUp };
  return panResponder.panHandlers;
}
