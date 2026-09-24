export const darkTheme = {
  colors: {
    ink: '#F4F5F7',
    spruce: '#6E7DEB',
    moss: '#454A58',
    linen: '#181A1F',
    clay: '#B8C0FF',
    berry: '#FF7B93',
    focus: '#C8CEFF',
    spruceSoft: '#292C3A',
    spruceOn: '#E4E7FF',
    mossSoft: '#22242B',
    linenMuted: '#1E2026',
    claySoft: '#343749',
    clayInk: '#D4D9FF',
    berrySoft: '#3D242D',
    border: '#383B45',
    muted: '#B1B4BE',
    white: '#24262D',
  },
  spacing: {
    screen: 24,
    content: 16,
    compact: 8,
  },
  radius: {
    input: 12,
    card: 16,
    button: 16,
  },
} as const;

export const lightTheme = {
  ...darkTheme,
  colors: {
    ink: '#202126',
    spruce: '#5968CE',
    moss: '#D8D9DF',
    linen: '#F4F4F2',
    clay: '#4B58AA',
    berry: '#C3435D',
    focus: '#3C4BB2',
    spruceSoft: '#E8EAFE',
    spruceOn: '#303C8D',
    mossSoft: '#ECECEF',
    linenMuted: '#E9E9E7',
    claySoft: '#E2E4F5',
    clayInk: '#38427E',
    berrySoft: '#FDECEE',
    border: '#D5D6DC',
    muted: '#626570',
    white: '#FFFFFF',
  },
} as const;

export type ColorTokens = { [Key in keyof typeof darkTheme.colors]: string };
export type AppTheme = Omit<typeof darkTheme, 'colors'> & { colors: ColorTokens };

// Legacy default used by screens not yet migrated to the interactive theme switch.
export const theme = darkTheme;
