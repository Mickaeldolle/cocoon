import { Platform } from 'react-native';

type InstallPromptEvent = Event & {
  prompt: () => Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

export type PwaInstallOffer = 'prompt' | 'ios' | 'unavailable';

let deferredPrompt: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notifyListeners() {
  listeners.forEach((listener) => listener());
}

if (Platform.OS === 'web' && typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event as InstallPromptEvent;
    notifyListeners();
  });
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    notifyListeners();
  });
}

export function subscribeToPwaInstallOffer(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function pwaInstallOffer(): PwaInstallOffer {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'unavailable';
  if (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone
  ) {
    return 'unavailable';
  }
  if (deferredPrompt) return 'prompt';
  const appleMobile =
    /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const safari =
    /Safari/.test(navigator.userAgent) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
  return appleMobile && safari ? 'ios' : 'unavailable';
}

export async function promptPwaInstall(): Promise<'accepted' | 'dismissed'> {
  const event = deferredPrompt;
  if (!event) throw new Error('La proposition d’installation n’est plus disponible.');
  deferredPrompt = null;
  notifyListeners();
  const result = await event.prompt();
  return result.outcome;
}
