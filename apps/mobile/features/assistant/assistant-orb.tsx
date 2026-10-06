import { lazy, Suspense } from 'react';
import type { OrbProps } from './orb-scene';
import { OrbFallback, OrbPlaceholder } from './orb-fallback';
const AssistantOrbNeural = lazy(() => import('./assistant-orb-neural'));
export function AssistantOrb(props: OrbProps) {
  const placeholder = <OrbPlaceholder size={props.size} />;
  return (
    <OrbFallback fallback={placeholder}>
      <Suspense fallback={placeholder}>
        <AssistantOrbNeural {...props} />
      </Suspense>
    </OrbFallback>
  );
}
