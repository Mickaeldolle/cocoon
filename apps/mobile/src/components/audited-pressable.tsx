import { useRef } from 'react';
import { Pressable as NativePressable, type PressableProps } from 'react-native';

import { reportButtonPress } from '@/src/services/ui-audit';

type Props = PressableProps & {
  /** A fixed identifier from the server allowlist; never a visible label or user value. */
  auditAction: string;
  auditLongPressAction?: string;
};

export function AuditedPressable({
  auditAction,
  auditLongPressAction,
  onPress,
  onPressIn,
  onLongPress,
  ...props
}: Props) {
  const longPressed = useRef(false);

  return (
    <NativePressable
      {...props}
      onPressIn={(event) => {
        longPressed.current = false;
        onPressIn?.(event);
      }}
      onLongPress={
        onLongPress
          ? (event) => {
              longPressed.current = true;
              reportButtonPress(auditLongPressAction ?? auditAction);
              onLongPress(event);
            }
          : undefined
      }
      onPress={
        onPress
          ? (event) => {
              if (!longPressed.current) reportButtonPress(auditAction);
              onPress(event);
            }
          : undefined
      }
    />
  );
}
