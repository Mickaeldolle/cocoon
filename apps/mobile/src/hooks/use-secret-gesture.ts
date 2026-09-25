import { useCallback, useEffect, useMemo, useRef } from 'react';
import { PanResponder, Platform, type View } from 'react-native';

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
  const areaRef = useRef<View>(null);

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

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const area = areaRef.current as unknown as HTMLElement | null;
    if (!area) return;

    let mouseStart: { x: number; y: number; pointerId: number } | null = null;
    let touchStart: { x: number; y: number; identifier: number } | null = null;
    let previousUserSelect: string | null = null;
    const restoreSelection = () => {
      if (previousUserSelect === null) return;
      area.style.userSelect = previousUserSelect;
      previousUserSelect = null;
    };
    const inGestureArea = (target: EventTarget | null) =>
      target instanceof Node &&
      area.contains(target) &&
      !(target instanceof Element &&
        target.closest('input, textarea, button, [role="button"], [contenteditable="true"]'));
    const onPointerDown = (event: globalThis.PointerEvent) => {
      if (event.pointerType !== 'mouse' || event.button !== 0 || !inGestureArea(event.target))
        return;
      previousUserSelect = area.style.userSelect;
      area.style.userSelect = 'none';
      mouseStart = { x: event.clientX, y: event.clientY, pointerId: event.pointerId };
    };
    const onPointerUp = (event: globalThis.PointerEvent) => {
      const start = mouseStart;
      mouseStart = null;
      restoreSelection();
      if (!start || event.pointerId !== start.pointerId) return;
      record(
        directionFromDelta(event.clientX - start.x, event.clientY - start.y, recognitionDistance),
      );
    };
    const onTouchStart = (event: TouchEvent) => {
      if (!inGestureArea(event.target)) return;
      const touch = event.changedTouches[0];
      if (touch) touchStart = { x: touch.clientX, y: touch.clientY, identifier: touch.identifier };
    };
    const onTouchEnd = (event: TouchEvent) => {
      const start = touchStart;
      touchStart = null;
      if (!start) return;
      const touch = Array.from(event.changedTouches).find((item) => item.identifier === start.identifier);
      if (touch)
        record(directionFromDelta(touch.clientX - start.x, touch.clientY - start.y, recognitionDistance));
    };
    const onPointerCancel = () => {
      mouseStart = null;
      restoreSelection();
    };
    const onTouchCancel = () => {
      touchStart = null;
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    document.addEventListener('pointerup', onPointerUp, true);
    document.addEventListener('pointercancel', onPointerCancel, true);
    document.addEventListener('touchstart', onTouchStart, true);
    document.addEventListener('touchend', onTouchEnd, true);
    document.addEventListener('touchcancel', onTouchCancel, true);
    return () => {
      restoreSelection();
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('pointerup', onPointerUp, true);
      document.removeEventListener('pointercancel', onPointerCancel, true);
      document.removeEventListener('touchstart', onTouchStart, true);
      document.removeEventListener('touchend', onTouchEnd, true);
      document.removeEventListener('touchcancel', onTouchCancel, true);
    };
  }, [record]);

  return Platform.OS === 'web'
    ? { ref: areaRef }
    : { ...panResponder.panHandlers, ref: areaRef };
}
