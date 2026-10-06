import { Component, type ReactNode } from 'react';
import { View } from 'react-native';

/** Reserve the decorative area while the graphics engine loads or is unavailable. */
export function OrbPlaceholder({ size = 320 }: { size?: number }) {
  return <View accessible={false} pointerEvents="none" style={{ width: size, height: size }} />;
}

/** Decorative rendering must never prevent using the assistant. */
export class OrbFallback extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
