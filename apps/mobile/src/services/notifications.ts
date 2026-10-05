import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { authApi, type Consent } from '@/src/services/api';

export type PersonalNotificationRoute = '/dashboard/tasks' | '/notifications' | '/home';

/** Map server-owned target types to a small allowlisted set of app routes. */
export function routeForPersonalNotification(
  data: Record<string, unknown>,
): PersonalNotificationRoute {
  if (data.kind === 'assistant_update') return '/home';
  return data.target_type === 'personal_task' && typeof data.target_id === 'string'
    ? '/dashboard/tasks'
    : '/notifications';
}

type NotificationsModule = typeof import('expo-notifications');
export type PersonalNotificationPermission = 'granted' | 'prompt' | 'denied' | 'unsupported';
export type HomePushAction = 'register' | 'offer' | 'blocked' | 'skip';
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

export async function personalNotificationPermission(): Promise<PersonalNotificationPermission> {
  if (Platform.OS === 'web') {
    if (
      typeof window === 'undefined' ||
      !window.isSecureContext ||
      !('serviceWorker' in navigator) ||
      !('PushManager' in window) ||
      !('Notification' in window)
    ) {
      return 'unsupported';
    }
    return Notification.permission === 'default' ? 'prompt' : Notification.permission;
  }
  const notifications = await loadNotifications();
  if (!notifications) return 'unsupported';
  const permission = await notifications.getPermissionsAsync();
  if (permission.status === 'granted') return 'granted';
  return permission.status === 'undetermined' && permission.canAskAgain ? 'prompt' : 'denied';
}

export function homePushAction(
  consents: Pick<Consent, 'policy_key' | 'revoked_at'>[],
  permission: PersonalNotificationPermission,
  platform: string,
): HomePushAction {
  if (consents.some((item) => item.policy_key === 'notifications.push' && item.revoked_at)) {
    return 'skip';
  }
  if (permission === 'unsupported') return 'skip';
  if (permission === 'denied') return 'blocked';
  if (permission === 'prompt' && platform === 'web') return 'offer';
  return 'register';
}

export async function registerForPersonalNotifications(accessToken: string): Promise<void> {
  if (Platform.OS === 'web') {
    if (
      typeof window === 'undefined' ||
      !window.isSecureContext ||
      !('serviceWorker' in navigator) ||
      !('PushManager' in window) ||
      !('Notification' in window)
    ) {
      throw new Error('Les notifications web nécessitent HTTPS et un navigateur compatible.');
    }
    const permission =
      Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
    if (permission !== 'granted') {
      throw new Error('Autorisez les notifications dans les réglages du navigateur.');
    }
    const { public_key: publicKey } = await authApi.webPushPublicKey(accessToken);
    const base64 = publicKey.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='));
    const key = new Uint8Array(decoded.length);
    for (let index = 0; index < decoded.length; index += 1) key[index] = decoded.charCodeAt(index);
    const registration = await navigator.serviceWorker.register('/sw.js');
    let subscription = await registration.pushManager.getSubscription();
    const previousKey = subscription?.options.applicationServerKey;
    if (
      subscription &&
      (!previousKey ||
        previousKey.byteLength !== key.byteLength ||
        new Uint8Array(previousKey).some((value, index) => value !== key[index]))
    ) {
      await subscription.unsubscribe();
      subscription = null;
    }
    subscription ??= await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    });
    const serialized = subscription.toJSON();
    if (!serialized.endpoint || !serialized.keys?.p256dh || !serialized.keys.auth) {
      throw new Error('Le navigateur n’a pas créé un abonnement de notification valide.');
    }
    await authApi.grantConsent(accessToken, 'notifications.push');
    await authApi.registerWebPush(accessToken, {
      endpoint: serialized.endpoint,
      p256dh: serialized.keys.p256dh,
      auth: serialized.keys.auth,
    });
    return;
  }
  const Notifications = await loadNotifications();
  if (!Notifications) {
    throw new Error(
      'Les notifications push nécessitent un development build ; Expo Go ne les prend pas en charge sur Android.',
    );
  }

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('personal-reminders', {
      name: 'Rappels personnels',
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 250],
      sound: undefined,
    });
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

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) {
    throw new Error('Le projet Expo n’est pas configuré pour les notifications.');
  }
  const pushToken = await Notifications.getExpoPushTokenAsync({ projectId });
  await authApi.grantConsent(accessToken, 'notifications.push');
  await authApi.registerPushToken(accessToken, pushToken.data);
}

export async function unsubscribeCurrentWebPush(): Promise<void> {
  if (Platform.OS !== 'web' || typeof navigator === 'undefined' || !('serviceWorker' in navigator))
    return;
  const registration = await navigator.serviceWorker.getRegistration('/');
  const subscription = await registration?.pushManager.getSubscription();
  await subscription?.unsubscribe();
}
