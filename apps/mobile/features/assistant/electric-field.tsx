import { Canvas, Path } from '@shopify/react-native-skia';
import { useMemo } from 'react';

import { plasmaArcs } from './electric-field-paths';

export function ElectricField({ size, tick }: { size: number; tick: number }) {
  const arcs = useMemo(() => plasmaArcs(size, tick), [size, tick]);
  return (
    <Canvas style={{ width: size, height: size }}>
      {arcs.map((arc, index) => (
        <Path
          key={`glow-${index}`}
          path={arc.path}
          color="#6559F7"
          opacity={arc.strength * 0.22}
          style="stroke"
          strokeCap="round"
          strokeJoin="round"
          strokeWidth={arc.branch ? 3.5 : 7}
        />
      ))}
      {arcs.map((arc, index) => (
        <Path
          key={`body-${index}`}
          path={arc.path}
          color="#80AEFF"
          opacity={arc.strength * 0.62}
          style="stroke"
          strokeCap="round"
          strokeJoin="round"
          strokeWidth={arc.branch ? 1 : 2}
        />
      ))}
      {arcs.map((arc, index) => (
        <Path
          key={`core-${index}`}
          path={arc.path}
          color="#E8F4FF"
          opacity={arc.strength}
          style="stroke"
          strokeCap="round"
          strokeJoin="round"
          strokeWidth={arc.branch ? 0.45 : 0.8}
        />
      ))}
    </Canvas>
  );
}
