import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { authApi } from '@/src/services/api';

export type PersonalNotificationRoute = '/dashboard/tasks' | '/notifications';

/** Map server-owned target types to a small allowlisted set of app routes. */
export function routeForPersonalNotification(
  data: Record<string, unknown>,
): PersonalNotificationRoute {
  return data.target_type === 'personal_task' && typeof data.target_id === 'string'
    ? '/dashboard/tasks'
    : '/notifications';
}

type NotificationsModule = typeof import('expo-notifications');
let notificationsModule: NotificationsModule | null = null;
let handlerConfigured = false;

function isExpoGo(): boolean {
  return Constants.appOwnership === 'expo';
}

async function loadNotifications(): Promise<NotificationsModule | null> {
  if (isExpoGo()) return null;
  if (!notificationsModule) {
    notificationsModule = await import('expo-notifications');
  }
  if (!handlerConfigured) {
    notificationsModule.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
    handlerConfigured = true;
  }
  return notificationsModule;
}

export async function subscribeToPersonalNotificationResponses(
  onResponse: (data: Record<string, unknown>) => void,
): Promise<() => void> {
  const notifications = await loadNotifications();
  if (!notifications) return () => undefined;
  const subscription = notifications.addNotificationResponseReceivedListener((response) => {
    const data = response.notification.request.content.data;
    if (data && typeof data === 'object') onResponse(data as Record<string, unknown>);
  });
  return () => subscription.remove();
}

export async function registerForPersonalNotifications(accessToken: string): Promise<void> {
  const Notifications = await loadNotifications();
  if (!Notifications) {
    throw new Error(
      'Les notifications push nécessitent un development build ; Expo Go ne les prend pas en charge sur Android.',
    );
  }
  if (Platform.OS === 'web') {
    throw new Error('Les notifications sont disponibles dans le build mobile Cocoon.');
  }

  const current = await Notifications.getPermissionsAsync();
  const permissions =
    current.status === 'granted'
      ? current
      : await Notifications.requestPermissionsAsync({
          ios: { allowAlert: true, allowBadge: false, allowSound: false },
        });
  if (permissions.status !== 'granted') {
    throw new Error('La permission de notification est refusée. Activez-la dans les réglages.');
  }

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('personal-reminders', {
      name: 'Rappels personnels',
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 250],
      sound: undefined,
    });
  }

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) {
    throw new Error('Le projet Expo n’est pas configuré pour les notifications.');
  }
  const pushToken = await Notifications.getExpoPushTokenAsync({ projectId });
  await authApi.grantConsent(accessToken, 'notifications.push');
  await authApi.registerPushToken(accessToken, pushToken.data);
}
