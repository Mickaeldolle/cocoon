import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { AppState, StyleSheet, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

import { assistantVisual } from '@/src/theme';

export type OrbProps = { size?: number; active?: boolean; enabled?: boolean };

const stars = Array.from({ length: 36 }, (_, index) => {
  const angle = index * 2.399963;
  const radius = 0.32 + ((index * 17) % 19) / 115;
  return {
    x: 0.5 + Math.cos(angle) * radius,
    y: 0.5 + Math.sin(angle) * radius * 0.86,
    size: index % 7 === 0 ? 3 : index % 3 === 0 ? 2 : 1.5,
    phase: angle,
    color: index % 3 === 0 ? assistantVisual.ice : assistantVisual.violet,
  };
});

function Star({
  star,
  size,
  pulse,
  energy,
}: {
  star: (typeof stars)[number];
  size: number;
  pulse: SharedValue<number>;
  energy: SharedValue<number>;
}) {
  const motion = useAnimatedStyle(() => {
    const wave = Math.sin(pulse.value * Math.PI * 2 + star.phase);
    return {
      opacity: 0.45 + (wave + 1) * 0.22,
      transform: [
        { translateX: wave * (2 + energy.value * 5) },
        { translateY: Math.cos(pulse.value * Math.PI * 2 + star.phase) * (3 + energy.value * 7) },
        { scale: 1 + energy.value * 0.25 },
      ],
    };
  });
  return (
    <Animated.View
      style={[
        styles.star,
        {
          left: star.x * size,
          top: star.y * size,
          width: star.size,
          height: star.size,
          backgroundColor: star.color,
          boxShadow: `0 0 7px ${star.color}`,
        },
        motion,
      ]}
    />
  );
}

/** One shared assistant presence. Only transforms/opacity animate on the UI thread. */
export function OrbScene({
  size = 320,
  active = false,
  enabled = true,
  core,
}: OrbProps & { core: ReactNode }) {
  const reducedMotion = useReducedMotion();
  const [focused, setFocused] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const orbit = useSharedValue(0);
  const pulse = useSharedValue(0);
  const energy = useSharedValue(0);
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) =>
      setForeground(state === 'active'),
    );
    return () => subscription.remove();
  }, []);
  useEffect(() => {
    const running = focused && foreground && enabled && !reducedMotion;
    energy.value = withTiming(active && !reducedMotion ? 1 : 0, { duration: 350 });
    if (running) {
      // A full revolution repeats without a visual seam, even after a speed change.
      orbit.value = withRepeat(
        withTiming(orbit.value + 360, {
          duration: active ? 12000 : 60000,
          easing: Easing.linear,
        }),
        -1,
      );
      pulse.value = withRepeat(
        withSequence(
          withTiming(1, { duration: active ? 1400 : 5000, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: active ? 1400 : 5000, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
      );
    }
    return () => {
      cancelAnimation(orbit);
      cancelAnimation(pulse);
      cancelAnimation(energy);
    };
  }, [active, enabled, focused, foreground, reducedMotion, orbit, pulse, energy]);
  const sphere = useAnimatedStyle(() => ({
    transform: [
      { translateY: Math.sin(pulse.value * Math.PI * 2) * size * 0.018 },
      { scale: 1 + pulse.value * 0.025 + energy.value * 0.04 },
      { rotate: `${Math.sin(pulse.value * Math.PI * 2) * (2 + energy.value * 4)}deg` },
    ],
  }));
  const constellation = useAnimatedStyle(() => ({
    transform: [{ rotate: `${orbit.value}deg` }, { scale: 1 - energy.value * 0.07 }],
  }));
  const outerStars = useAnimatedStyle(() => ({
    transform: [{ rotate: `${-orbit.value * 0.7}deg` }, { scale: 1 + energy.value * 0.05 }],
  }));
  const glow = useAnimatedStyle(() => ({ opacity: 0.45 + pulse.value * 0.2 + energy.value * 0.2 }));
  return (
    <View
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={{ width: size, height: size }}
    >
      <Animated.View
        style={[
          styles.glow,
          { left: size * 0.24, top: size * 0.24, width: size * 0.52, height: size * 0.52 },
          glow,
        ]}
      />
      <Animated.View style={[StyleSheet.absoluteFill, constellation]}>
        {stars.slice(0, 24).map((star, index) => (
          <Star key={index} star={star} size={size} pulse={pulse} energy={energy} />
        ))}
      </Animated.View>
      <Animated.View style={[StyleSheet.absoluteFill, sphere]}>{core}</Animated.View>
      <Animated.View style={[StyleSheet.absoluteFill, outerStars]}>
        {stars.slice(24).map((star, index) => (
          <Star key={index} star={star} size={size} pulse={pulse} energy={energy} />
        ))}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  star: { position: 'absolute', borderRadius: 4 },
  glow: {
    position: 'absolute',
    borderRadius: 999,
    backgroundColor: assistantVisual.glow,
    boxShadow: `0 0 65px 30px ${assistantVisual.glow}`,
  },
});
