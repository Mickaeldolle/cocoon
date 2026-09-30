export function secretBiometricMode(
  platform: string,
  development: boolean,
): 'development' | 'android' | 'none' {
  if (development && platform !== 'web') return 'development';
  if (platform === 'android') return 'android';
  return 'none';
}
