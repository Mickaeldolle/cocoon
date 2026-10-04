# Architecture — état actuel

## Décisions

Le projet est un monolithe modulaire. `apps/api` porte les règles d’autorisation et l’accès aux données ; `apps/mobile` ne reçoit que les données auxquelles la session autorisée a accès. Le client n’est jamais un filtre de sécurité.

```text
Application Expo (iOS / Android)
            │ HTTPS / WSS
            ▼
          Caddy
            ▼
       FastAPI (REST)
       ├── PostgreSQL : utilisateurs, appareils, sessions
       └── Redis : base pour cache, temps réel et futures tâches
```

## Authentification standard

Un compte possède un email unique et un mot de passe haché avec Argon2. Chaque connexion crée une session liée à un appareil. L’API émet :

- un access token signé, de courte durée, utilisable uniquement avec le scope `normal` ;
- un refresh token aléatoire, haché en base et renouvelé à chaque rafraîchissement.

La session est vérifiée par l’API à chaque endpoint protégé et peut donc être révoquée lors de la déconnexion. Le mobile ne conserve durablement que le refresh token dans Expo SecureStore ; le token d’accès reste en mémoire.

## Accès renforcé aux discussions cachées

La séquence mobile `→ → ↑` n’est qu’un déclencheur discret : elle ouvre une réauthentification par mot de passe. Après vérification, l’API crée dans `secret_access_sessions` un jeton opaque, haché en base, valable cinq minutes et lié à la session normale et à son appareil.

Les routes `/api/secret/*` exigent à la fois le token normal et l’en-tête `X-Cocoon-Secret-Access`. Le jeton secret n’est jamais stocké durablement dans le mobile ; l’application le supprime, avec le cache de ses requêtes, au verrouillage manuel, en arrière-plan, à expiration ou à la perte de session. Les routes de messagerie standard continuent d’ignorer ces conversations.

Une Passkey native vérifiable par le serveur n’est pas encore disponible : elle remplacera la saisie du mot de passe une fois le pont Expo approprié intégré. Une biométrie locale seule ne peut pas autoriser l’API.

## Espaces familiaux

Un utilisateur peut appartenir à plusieurs espaces via `family_space_members`. La liste et le détail sont toujours joints à l’adhésion du demandeur. Un espace non accessible retourne `404`, afin de ne pas confirmer son existence. Seuls `OWNER` et `ADMIN` peuvent ajouter un membre ; l’adhésion du créateur est `OWNER` dès la transaction de création.

## Limites explicites du jalon

L’API de messagerie normale est présente : conversations, messages et WebSocket authentifié. Les conversations dont l’adhésion est `is_hidden` sont filtrées par l’API standard. Les messages de la zone renforcée ne produisent volontairement ni notification ni diffusion temps réel à ce jalon, afin de ne pas révéler leur existence.

La passkey WebAuthn du navigateur permet de renouveler l’accès renforcé après inscription explicite par mot de passe. L’API conserve la clé publique et un compteur de signature, vérifie un défi à usage unique lié à la session ainsi que l’origine web fixée par `WEBAUTHN_ORIGIN`. Les passkeys natives, les notifications et le temps réel secret restent à concevoir. Le détail de l’avancement est maintenu dans [`TASKS.md`](../TASKS.md).
