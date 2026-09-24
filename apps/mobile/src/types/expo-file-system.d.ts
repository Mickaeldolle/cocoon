declare module 'expo-file-system/legacy' {
  export function deleteAsync(
    fileUri: string,
    options?: { idempotent?: boolean },
  ): Promise<void>;
}
