import { Redirect } from 'expo-router';
import { ActivityIndicator, View } from 'react-native';

import { darkTheme, lightTheme } from '@/src/theme';
import { useSessionStore } from '@/src/stores/session-store';
import { useThemeStore } from '@/src/stores/theme-store';

export default function Index() {
  const mode = useThemeStore((state) => state.mode);
  const colors = (mode === 'light' ? lightTheme : darkTheme).colors;
  const initialized = useSessionStore((state) => state.initialized);
  const user = useSessionStore((state) => state.user);
  if (!initialized) {
    return (
      <View
        style={{
          alignItems: 'center',
          backgroundColor: colors.linen,
          flex: 1,
          justifyContent: 'center',
        }}
      >
        <ActivityIndicator color={colors.spruce} />
      </View>
    );
  }
  return <Redirect href={user ? '/home' : '/sign-in'} />;
}
