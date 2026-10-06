import { useMemo } from 'react';

import { plasmaArcs } from './electric-field-paths';

export function ElectricField({ size, tick }: { size: number; tick: number }) {
  const arcs = useMemo(() => plasmaArcs(size, tick), [size, tick]);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {arcs.map((arc, index) => (
        <path
          key={`glow-${index}`}
          d={arc.path}
          fill="none"
          stroke="#6559F7"
          strokeOpacity={arc.strength * 0.22}
          strokeWidth={arc.branch ? 3.5 : 7}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {arcs.map((arc, index) => (
        <path
          key={`body-${index}`}
          d={arc.path}
          fill="none"
          stroke="#80AEFF"
          strokeOpacity={arc.strength * 0.62}
          strokeWidth={arc.branch ? 1 : 2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {arcs.map((arc, index) => (
        <path
          key={`core-${index}`}
          d={arc.path}
          fill="none"
          stroke="#E8F4FF"
          strokeOpacity={arc.strength}
          strokeWidth={arc.branch ? 0.45 : 0.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}
