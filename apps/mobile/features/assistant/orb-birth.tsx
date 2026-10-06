import { useEffect, useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  interpolate,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { AssistantOrb } from './assistant-orb';
import { ElectricField } from './electric-field';

const SEED_DURATION_MS = 2000;
const CHARGE_DURATION_MS = 4000;
const GROW_DURATION_MS = 4000;
const BIRTH_DURATION_MS = SEED_DURATION_MS + CHARGE_DURATION_MS + GROW_DURATION_MS;
export function OrbBirth({ size, onComplete }: { size: number; onComplete: () => void }) {
  const reducedMotion = useReducedMotion();
  const progress = useSharedValue(reducedMotion ? 1 : 0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    progress.value = withTiming(1, {
      duration: reducedMotion ? 0 : BIRTH_DURATION_MS,
      easing: Easing.linear,
    });
    let interval: ReturnType<typeof setInterval> | undefined;
    let chargeStart: ReturnType<typeof setTimeout> | undefined;
    if (!reducedMotion) {
      chargeStart = setTimeout(() => {
        setTick(1);
        interval = setInterval(() => setTick((current) => current + 1), 100);
      }, SEED_DURATION_MS);
    }
    const timeout = setTimeout(
      () => {
        if (interval) clearInterval(interval);
        onComplete();
      },
      reducedMotion ? 0 : BIRTH_DURATION_MS,
    );
    return () => {
      if (chargeStart) clearTimeout(chargeStart);
      if (interval) clearInterval(interval);
      clearTimeout(timeout);
      cancelAnimation(progress);
    };
  }, [onComplete, progress, reducedMotion]);

  const orbMotion = useAnimatedStyle(() => {
    const time = progress.value;
    const growth = Math.max(0, Math.min(1, (time - 0.6) / 0.4));
    const eased = growth * growth * (3 - 2 * growth);
    const scale =
      time < 0.6 ? interpolate(time, [0, 0.2, 0.6], [0.1, 0.12, 0.16]) : 0.16 + 0.84 * eased;
    return {
      opacity: interpolate(time, [0, 0.18, 0.23, 0.6, 1], [0.12, 0.2, 0.85, 1, 1]),
      transform: [{ scale }],
    };
  });
  const seedMotion = useAnimatedStyle(() => ({
    opacity: interpolate(progress.value, [0, 0.2, 0.6, 1], [0.45, 0.75, 0.65, 0.12]),
  }));
  const electricity = useAnimatedStyle(() => ({
    opacity: interpolate(progress.value, [0, 0.2, 0.25, 0.6, 0.8, 1], [0, 0, 1, 1, 0.6, 0]),
  }));

  return (
    <View
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={{ width: size, height: size }}
    >
      <Animated.View style={[StyleSheet.absoluteFill, orbMotion]}>
        <Animated.View
          style={[
            styles.seed,
            {
              left: size * 0.175,
              top: size * 0.175,
              width: size * 0.65,
              height: size * 0.65,
            },
            seedMotion,
          ]}
        />
        <AssistantOrb size={size} active enabled />
      </Animated.View>
      {!reducedMotion && tick > 0 ? (
        <Animated.View style={[StyleSheet.absoluteFill, electricity]}>
          <ElectricField size={size} tick={tick} />
        </Animated.View>
      ) : null}
    </View>
  );
}

const seedGradient =
  'radial-gradient(circle at 42% 36%, #D4C8FF 0%, #7652D8 30%, #3E276E 68%, #241D3D 100%)';
const styles = StyleSheet.create({
  seed: {
    position: 'absolute',
    borderRadius: 999,
    borderColor: '#B8A2FF',
    borderWidth: 2,
    backgroundColor: '#6344B8',
    boxShadow: '0 0 26px rgba(150, 114, 255, 0.55)',
    ...(Platform.OS === 'web'
      ? { backgroundImage: seedGradient }
      : { experimental_backgroundImage: seedGradient }),
  },
});
