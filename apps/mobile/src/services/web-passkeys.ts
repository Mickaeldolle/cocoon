import { Platform } from 'react-native';

import { secretApi, type SecretAccess } from '@/src/services/api';

type CredentialDescriptorJSON = {
  id: string;
  type: PublicKeyCredentialType;
  transports?: AuthenticatorTransport[];
};
type CreationOptionsJSON = Omit<
  PublicKeyCredentialCreationOptions,
  'challenge' | 'user' | 'excludeCredentials'
> & {
  challenge: string;
  user: Omit<PublicKeyCredentialUserEntity, 'id'> & { id: string };
  excludeCredentials?: CredentialDescriptorJSON[];
};
type RequestOptionsJSON = Omit<
  PublicKeyCredentialRequestOptions,
  'challenge' | 'allowCredentials'
> & {
  challenge: string;
  allowCredentials?: CredentialDescriptorJSON[];
};

function fromBase64url(value: string): Uint8Array<ArrayBuffer> {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
  const decoded = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='));
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) bytes[index] = decoded.charCodeAt(index);
  return bytes;
}

function toBase64url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function requireWebAuthn(): void {
  if (
    Platform.OS !== 'web' ||
    typeof window === 'undefined' ||
    !window.isSecureContext ||
    typeof PublicKeyCredential === 'undefined' ||
    !navigator.credentials
  ) {
    throw new Error('Les passkeys nécessitent un navigateur compatible et une connexion HTTPS.');
  }
}

export function webPasskeysSupported(): boolean {
  try {
    requireWebAuthn();
    return true;
  } catch {
    return false;
  }
}

export async function registerWebPasskey(
  accessToken: string,
  password: string,
): Promise<SecretAccess> {
  requireWebAuthn();
  const ceremony = await secretApi.passkeyRegistrationOptions(accessToken, password);
  const options = ceremony.options as CreationOptionsJSON;
  const publicKey: PublicKeyCredentialCreationOptions = {
    ...options,
    challenge: fromBase64url(options.challenge),
    user: { ...options.user, id: fromBase64url(options.user.id) },
    excludeCredentials: options.excludeCredentials?.map((item) => ({
      ...item,
      id: fromBase64url(item.id),
    })),
  };
  const credential = (await navigator.credentials.create({
    publicKey,
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error('Création de la passkey annulée.');
  const response = credential.response as AuthenticatorAttestationResponse;
  return secretApi.verifyPasskeyRegistration(accessToken, ceremony.challenge_id, {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    response: {
      attestationObject: toBase64url(response.attestationObject),
      clientDataJSON: toBase64url(response.clientDataJSON),
      transports: response.getTransports?.() ?? [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  });
}

export async function unlockWithWebPasskey(accessToken: string): Promise<SecretAccess> {
  requireWebAuthn();
  const ceremony = await secretApi.passkeyUnlockOptions(accessToken);
  const options = ceremony.options as RequestOptionsJSON;
  const publicKey: PublicKeyCredentialRequestOptions = {
    ...options,
    challenge: fromBase64url(options.challenge),
    allowCredentials: options.allowCredentials?.map((item) => ({
      ...item,
      id: fromBase64url(item.id),
    })),
  };
  const credential = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null;
  if (!credential) throw new Error('Vérification par passkey annulée.');
  const response = credential.response as AuthenticatorAssertionResponse;
  return secretApi.verifyPasskeyUnlock(accessToken, ceremony.challenge_id, {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: toBase64url(response.authenticatorData),
      clientDataJSON: toBase64url(response.clientDataJSON),
      signature: toBase64url(response.signature),
      userHandle: response.userHandle ? toBase64url(response.userHandle) : null,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  });
}
