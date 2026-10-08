import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { AppState, StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useFrameCallback,
  useReducedMotion,
  useSharedValue,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

import { assistantVisual } from '@/src/theme';

export type OrbProps = { size?: number; active?: boolean; enabled?: boolean };

const stars = Array.from({ length: 48 }, (_, index) => {
  const angle = index * 2.399963;
  const radius = 0.37 + ((index * 17) % 19) / 165;
  return {
    x: 0.5 + Math.cos(angle) * radius,
    y: 0.5 + Math.sin(angle) * radius * 0.86,
    size: index % 7 === 0 ? 3.3 : index % 3 === 0 ? 2.2 : 1.5,
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
  const drift = Math.min(1, size / 220);
  const motion = useAnimatedStyle(() => {
    const wave = Math.sin(pulse.value * Math.PI * 2 + star.phase);
    return {
      opacity: 0.38 + (wave + 1) * (0.21 + energy.value * 0.09),
      transform: [
        { translateX: wave * (2 + energy.value * 10) * drift },
        {
          translateY:
            Math.cos(pulse.value * Math.PI * 2 + star.phase) * (3 + energy.value * 12) * drift,
        },
        { scale: 1 + energy.value * 0.45 },
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
          width: star.size * (size < 100 ? 0.55 : 1),
          height: star.size * (size < 100 ? 0.55 : 1),
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
  const frame = useFrameCallback(({ timeSincePreviousFrame }) => {
    const seconds = Math.min(timeSincePreviousFrame ?? 0, 48) / 1000;
    orbit.value = (orbit.value + seconds * (6 + energy.value * 24)) % 360;
    pulse.value = (pulse.value + seconds * (0.1 + energy.value * 0.24)) % 1;
  }, false);
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
    energy.value = withTiming(running && active ? 1 : 0, {
      duration: reducedMotion ? 0 : 450,
      easing: Easing.inOut(Easing.sin),
    });
    frame.setActive(running);
    return () => frame.setActive(false);
  }, [active, enabled, focused, foreground, reducedMotion, energy, frame]);
  const sphere = useAnimatedStyle(() => ({
    transform: [
      { translateY: Math.sin(pulse.value * Math.PI * 2) * size * 0.018 },
      { scale: 1 + Math.sin(pulse.value * Math.PI * 2) * 0.012 + energy.value * 0.055 },
      { rotate: `${Math.sin(pulse.value * Math.PI * 2) * (2 + energy.value * 4)}deg` },
    ],
  }));
  const constellation = useAnimatedStyle(() => ({
    transform: [{ rotate: `${orbit.value}deg` }, { scale: 1 - energy.value * 0.07 }],
  }));
  const outerStars = useAnimatedStyle(() => ({
    transform: [{ rotate: `${-orbit.value * 0.7}deg` }, { scale: 1 + energy.value * 0.05 }],
  }));
  const glow = useAnimatedStyle(() => ({
    opacity: 0.48 + Math.sin(pulse.value * Math.PI * 2) * 0.08 + energy.value * 0.23,
  }));
  const visibleStars = size < 100 ? stars.slice(0, 20) : stars;
  const innerStars = Math.ceil(visibleStars.length * 0.65);
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
        {visibleStars.slice(0, innerStars).map((star, index) => (
          <Star key={index} star={star} size={size} pulse={pulse} energy={energy} />
        ))}
      </Animated.View>
      <Animated.View style={[StyleSheet.absoluteFill, sphere]}>{core}</Animated.View>
      <Animated.View style={[StyleSheet.absoluteFill, outerStars]}>
        {visibleStars.slice(innerStars).map((star, index) => (
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
