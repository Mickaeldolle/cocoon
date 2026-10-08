import { AuditedPressable as Pressable } from '@/src/components/audited-pressable';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { authApi, type Device } from '@/src/services/api';
import type { ProfileStyles } from './styles';

export function DeviceManager({
  token,
  devices,
  styles,
}: {
  token: string;
  devices: Device[];
  styles: ProfileStyles;
}) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const revoke = useMutation({
    mutationFn: (deviceId: string) => authApi.revokeDevice(token, deviceId),
    onSuccess: () => {
      setError(null);
      void client.invalidateQueries({ queryKey: ['auth', 'devices'] });
    },
    onError: () => setError('Cet appareil ne peut pas être révoqué pour le moment.'),
  });
  return (
    <View style={styles.devicesCard}>
      <Text style={styles.devicesTitle}>Appareils connectés</Text>
      <Text style={styles.devicesIntro}>
        Révoquez une ancienne session pour empêcher cet appareil d’accéder à votre compte.
      </Text>
      {devices.map((device) => (
        <View key={device.id} style={styles.deviceRow}>
          <View style={styles.deviceCopy}>
            <Text style={styles.deviceName}>{device.name}</Text>
            <Text style={styles.deviceMeta}>
              {device.platform} · {device.current ? 'appareil actuel' : 'session distante'}
            </Text>
          </View>
          {!device.current ? (
            <Pressable
              auditAction="profile.device.revoke"
              accessibilityRole="button"
              accessibilityLabel={`Révoquer ${device.name}`}
              disabled={revoke.isPending}
              onPress={() => revoke.mutate(device.id)}
              style={[styles.revoke, revoke.isPending && styles.disabled]}
            >
              <Text style={styles.revokeText}>Révoquer</Text>
            </Pressable>
          ) : null}
        </View>
      ))}
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}
