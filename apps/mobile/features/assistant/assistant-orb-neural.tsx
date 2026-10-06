import { Canvas, Fill, Shader, Skia } from '@shopify/react-native-skia';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { AppState } from 'react-native';
import {
  useDerivedValue,
  useFrameCallback,
  useReducedMotion,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { OrbScene, type OrbProps } from './orb-scene';
import { OrbPlaceholder } from './orb-fallback';
import { neuralOrbShader } from './neural-orb-shader';

const effect = Skia.RuntimeEffect.Make(neuralOrbShader);
function NeuralCore({ size, active, enabled }: Required<OrbProps>) {
  const reducedMotion = useReducedMotion();
  const [focused, setFocused] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const time = useSharedValue(0);
  const energy = useSharedValue(0);
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );
  useEffect(() => {
    const listener = AppState.addEventListener('change', (state) =>
      setForeground(state === 'active'),
    );
    return () => listener.remove();
  }, []);
  useEffect(() => {
    energy.value = withTiming(active && enabled && !reducedMotion ? 1 : 0, { duration: 500 });
  }, [active, enabled, reducedMotion, energy]);
  const frame = useFrameCallback(({ timeSincePreviousFrame }) => {
    // Cap the step so resuming never jumps the sphere ahead.
    time.value += (Math.min(timeSincePreviousFrame ?? 0, 48) / 1000) * (0.6 + energy.value * 1.2);
  }, false);
  useEffect(() => {
    frame.setActive(focused && foreground && enabled && !reducedMotion);
    return () => frame.setActive(false);
  }, [frame, focused, foreground, enabled, reducedMotion]);
  const uniforms = useDerivedValue(() => ({ size, time: time.value, energy: energy.value }));
  if (!effect) return null;
  return (
    <Canvas style={{ width: size, height: size }}>
      <Fill>
        <Shader source={effect} uniforms={uniforms} />
      </Fill>
    </Canvas>
  );
}

export default function AssistantOrbNeural({
  size = 320,
  active = false,
  enabled = true,
}: OrbProps) {
  if (!effect) return <OrbPlaceholder size={size} />;
  return (
    <OrbScene
      size={size}
      active={active}
      enabled={enabled}
      core={<NeuralCore size={size} active={active} enabled={enabled} />}
    />
  );
}
