import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { reportButtonPress } from '@/src/services/ui-audit';
import { useRef } from 'react';
import { ActivityIndicator, StyleSheet, Text } from 'react-native';

import { darkTheme, type ColorTokens } from '@/src/theme';

type Props = {
  accessToken: string | null;
  colors: ColorTokens;
  variant?: 'home' | 'chat';
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
  variant = 'home',
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
  const chat = variant === 'chat';
  const explainVoice = () => {
    if (unavailable || sending) return;
    held.current = true;
    onError('Transcription audio indisponible.');
  };

  return (
    <Pressable
      auditAction={
        sending ? 'assistant.stop' : hasText ? 'assistant.send' : 'assistant.composer.tap_empty'
      }
      auditLongPressAction="assistant.voice.unavailable"
      accessibilityRole="button"
      accessibilityLabel={
        sending && onCancelSend
          ? 'Arrêter la génération'
          : hasText
            ? 'Envoyer le message'
            : 'Dictée indisponible'
      }
      accessibilityHint={
        hasText ? 'Un appui envoie le message.' : 'Un appui indique la disponibilité de la dictée.'
      }
      accessibilityState={{ busy: sending, disabled: unavailable }}
      accessibilityActions={[{ name: 'voice', label: 'Disponibilité de la transcription audio' }]}
      onAccessibilityAction={({ nativeEvent }) => {
        if (nativeEvent.actionName === 'voice' && !unavailable && !sending) {
          reportButtonPress('assistant.voice.unavailable');
          explainVoice();
        }
      }}
      disabled={unavailable}
      delayLongPress={350}
      onPressIn={() => {
        held.current = false;
      }}
      onLongPress={sending ? undefined : explainVoice}
      onPress={() => {
        if (held.current || unavailable) return;
        if (sending) onCancelSend?.();
        else if (hasText) onSend();
        else explainVoice();
      }}
      style={({ pressed }) => [
        styles.button,
        chat && styles.chatButton,
        chat && !hasText && !sending && styles.chatMic,
        unavailable && styles.disabled,
        pressed && !unavailable && styles.pressed,
      ]}
    >
      {sending && !onCancelSend ? (
        <ActivityIndicator color={darkTheme.colors.ink} />
      ) : (
        <Text
          style={[
            styles.icon,
            chat && (hasText || sending ? styles.chatSendIcon : styles.chatMicIcon),
          ]}
        >
          {sending ? 'stop' : chat ? (hasText ? 'send' : 'mic') : 'arrow_upward'}
        </Text>
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
    chatButton: { borderRadius: 22, height: 44, width: 44 },
    chatMic: { backgroundColor: colors.white, borderColor: colors.border, borderWidth: 1 },
    chatMicIcon: { color: colors.spruce, fontSize: 22 },
    chatSendIcon: { color: colors.linen, fontSize: 23 },
    disabled: { opacity: 0.5 },
    pressed: { opacity: 0.8 },
  });
}
