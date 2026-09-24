import { useRef } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { darkTheme, type ColorTokens } from '@/src/theme';

type Props = {
  accessToken: string | null;
  colors: ColorTokens;
  disabled?: boolean;
  sending?: boolean;
  hasText: boolean;
  onSend: () => void;
  onCancelSend?: () => void;
  onError: (message: string) => void;
};

/** One control: send on tap; explain unavailable transcription on hold without opening the mic. */
export function VoiceCapture({
  accessToken,
  colors,
  disabled = false,
  sending = false,
  hasText,
  onSend,
  onCancelSend,
  onError,
}: Props) {
  const held = useRef(false);
  const styles = makeStyles(colors);
  const unavailable = disabled || !accessToken || (sending && !onCancelSend);
  const explainVoice = () => {
    if (unavailable || sending) return;
    held.current = true;
    onError('Transcription audio indisponible.');
  };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={sending && onCancelSend ? 'Arrêter la génération' : 'Envoyer le texte'}
      accessibilityHint="Un appui envoie le texte. La transcription audio est actuellement indisponible."
      accessibilityState={{ busy: sending, disabled: unavailable }}
      accessibilityActions={[{ name: 'voice', label: 'Disponibilité de la transcription audio' }]}
      onAccessibilityAction={({ nativeEvent }) => {
        if (nativeEvent.actionName === 'voice') explainVoice();
      }}
      disabled={unavailable}
      delayLongPress={350}
      onPressIn={() => {
        held.current = false;
      }}
      onLongPress={explainVoice}
      onPress={() => {
        if (held.current || unavailable) return;
        if (sending) onCancelSend?.();
        else if (hasText) onSend();
      }}
      style={({ pressed }) => [
        styles.button,
        unavailable && styles.disabled,
        pressed && !unavailable && styles.pressed,
      ]}
    >
      {sending && !onCancelSend ? (
        <ActivityIndicator color={darkTheme.colors.ink} />
      ) : (
        <Text style={styles.icon}>{sending ? 'stop' : 'arrow_upward'}</Text>
      )}
    </Pressable>
  );
}

function makeStyles(colors: ColorTokens) {
  return StyleSheet.create({
    button: {
      alignItems: 'center',
      backgroundColor: colors.spruce,
      borderRadius: 24,
      height: 48,
      width: 48,
      flexShrink: 0,
      justifyContent: 'center',
    },
    icon: { color: darkTheme.colors.ink, fontFamily: 'MaterialSymbols_400Regular', fontSize: 24 },
    disabled: { opacity: 0.5 },
    pressed: { opacity: 0.8 },
  });
}
