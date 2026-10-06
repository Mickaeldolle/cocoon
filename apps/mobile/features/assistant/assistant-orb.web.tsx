import { WithSkiaWeb } from '@shopify/react-native-skia/lib/module/web';
import type { OrbProps } from './orb-scene';

import { OrbFallback, OrbPlaceholder } from './orb-fallback';

const loadOrb = () => import('./assistant-orb-neural');
const webOptions = { locateFile: () => '/canvaskit.wasm' };
export function AssistantOrb(props: OrbProps) {
  const placeholder = <OrbPlaceholder size={props.size} />;
  return (
    <OrbFallback fallback={placeholder}>
      <WithSkiaWeb
        getComponent={loadOrb}
        componentProps={props}
        opts={webOptions}
        fallback={placeholder}
      />
    </OrbFallback>
  );
}
