// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const prettierConfig = require('eslint-config-prettier/flat');

module.exports = defineConfig([
  {
    ignores: ['.expo/**', 'android/**', 'dist/**', 'ios/**', 'node_modules/**'],
    linterOptions: {
      reportUnusedDisableDirectives: 'warn',
    },
  },
  expoConfig,
  prettierConfig,
]);
