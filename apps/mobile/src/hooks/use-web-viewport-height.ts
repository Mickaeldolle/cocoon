import { useEffect } from 'react';
import { Platform } from 'react-native';

export function useWebViewportHeight(): void {
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;

    const viewport = window.visualViewport;
    const updateHeight = () => {
      const height = viewport?.height ?? window.innerHeight;
      if (height > 0) {
        document.documentElement.style.setProperty(
          '--cocoon-viewport-height',
          `${Math.ceil(height)}px`,
        );
      }
    };

    updateHeight();
    window.addEventListener('resize', updateHeight);
    viewport?.addEventListener('resize', updateHeight);
    return () => {
      window.removeEventListener('resize', updateHeight);
      viewport?.removeEventListener('resize', updateHeight);
      document.documentElement.style.removeProperty('--cocoon-viewport-height');
    };
  }, []);
}
