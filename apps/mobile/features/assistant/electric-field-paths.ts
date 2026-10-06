const TAU = Math.PI * 2;

export type PlasmaArc = { path: string; strength: number; branch: boolean };

function randomGenerator(seed: number): () => number {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function point(size: number, radius: number, angle: number) {
  return {
    x: size * (0.5 + Math.cos(angle) * radius),
    y: size * (0.5 + Math.sin(angle) * radius),
  };
}

function toPath(points: { x: number; y: number }[]): string {
  return points
    .map(({ x, y }, index) => `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(' ');
}

/** Short-lived plasma filaments radiate from the small core and split irregularly. */
export function plasmaArcs(size: number, tick: number): PlasmaArc[] {
  const random = randomGenerator(tick * 7907 + 13);
  const slowRandom = randomGenerator(Math.floor(tick / 7) * 104729 + 97);
  const arcs: PlasmaArc[] = [];
  const count = 1 + Math.floor(slowRandom() * 3);
  const directions: number[] = [];
  for (let index = 0; index < count; index += 1) {
    let direction = (index / count) * TAU;
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const candidate = slowRandom() * TAU;
      const separated = directions.every((previous) => {
        const distance = Math.abs(candidate - previous);
        return Math.min(distance, TAU - distance) > 0.55;
      });
      if (separated) {
        direction = candidate;
        break;
      }
    }
    directions.push(direction);
    const baseAngle = direction + Math.sin(tick * 0.14 + index * 2.1) * 0.12;
    const bend = (random() - 0.5) * 1.0;
    const reach = 0.34 + random() * 0.13;
    const points = Array.from({ length: 11 }, (_, step) => {
      const fraction = step / 10;
      const angle = baseAngle + bend * fraction * fraction + (random() - 0.5) * 0.18 * fraction;
      return point(size, 0.055 + (reach - 0.055) * fraction, angle);
    });
    const strength = 0.48 + random() * 0.52;
    arcs.push({ path: toPath(points), strength, branch: false });

    if (random() < 0.55) {
      const fork = points[5];
      const direction = baseAngle + bend * 0.5 + (random() > 0.5 ? 1 : -1) * 0.3;
      const branchPoints = [fork];
      for (let step = 1; step <= 5; step += 1) {
        const fraction = step / 5;
        branchPoints.push(
          point(
            size,
            0.055 + (reach - 0.055) * (0.5 + fraction * 0.45),
            direction + (random() - 0.5) * 0.16 * fraction,
          ),
        );
      }
      arcs.push({ path: toPath(branchPoints), strength: strength * 0.48, branch: true });
    }
  }
  return arcs;
}
