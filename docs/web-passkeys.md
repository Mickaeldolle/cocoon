# Passkeys WebAuthn pour la connexion et l’espace protégé

Le site Expo Web peut demander une passkey pour se connecter au compte, puis une nouvelle vérification pour ouvrir l’espace protégé. Selon le navigateur et l’appareil, la vérification locale peut utiliser une empreinte, le visage, un code ou une clé de sécurité. La biométrie elle-même n’est jamais envoyée à Cocoon.

## Déploiement

1. Déployer la nouvelle version de l’API avec `apps/api/uv.lock`. Exécuter ensuite les migrations jusqu’à `20260928_32` sur la **base réellement utilisée par l’API** avec `uv run alembic upgrade head`, puis contrôler `uv run alembic current`. Vercel n’exécute pas Alembic automatiquement.
2. Dans les variables du projet **API** Vercel, définir `WEBAUTHN_ORIGIN=https://cocoon-sigma-six.vercel.app`. C’est l’origine exacte du site, sans chemin ni `/` final, et non l’URL de l’API. Garder `CORS_ORIGINS` autorisant cette même origine. Redéployer l’API après la modification.
3. Déployer la nouvelle version du site web. Ouvrir le site à cette adresse HTTPS exacte. Une preview Vercel sur une autre origine n’est pas autorisée par cette configuration.

L’identifiant WebAuthn est ici `cocoon-sigma-six.vercel.app`. Une passkey enregistrée pour ce domaine ne suit pas automatiquement un futur domaine personnalisé : décider d’un domaine stable avant de proposer l’inscription à tous les utilisateurs, ou prévoir une nouvelle inscription après changement de domaine.

## Utilisation

Après connexion par mot de passe, ouvrir **Profil > Passkeys**, saisir le mot de passe et choisir **Créer une passkey**. Accepter la demande du navigateur. Une passkey déjà créée depuis l’écran de déverrouillage protégé est aussi utilisable pour la connexion au compte.

Sur `/sign-in`, saisir l’adresse email puis choisir **Se connecter avec une passkey**. Le mot de passe reste disponible. Pour l’espace protégé, effectuer le geste d’accès puis choisir **Déverrouiller avec une passkey** : une seconde vérification est exigée et le jeton renforcé reste limité à cinq minutes.

Pour révoquer les passkeys du compte, utiliser **Profil > Passkeys > Supprimer mes passkeys** après saisie du mot de passe. La confirmation supprime toutes les clés du compte et invalide ses jetons d’accès secret en cours. Les sessions normales déjà ouvertes doivent être révoquées séparément depuis la liste des appareils.

Le navigateur ne peut pas imposer l’empreinte digitale : le système d’exploitation choisit la méthode locale. Les passkeys sont actuellement réservées au **web** ; l’adaptateur biométrique Expo natif reste limité au développement.

## Contrôles

- Sur `GET /api/secret/passkeys/status`, `available` doit être `true` quand `WEBAUTHN_ORIGIN` est correctement défini. Après inscription, `has_passkeys` doit être `true` pour le compte connecté.
- Vérifier que `/sign-in` échange une assertion valide contre une session normale, et qu’un défi rejoué ou lié à une autre origine est refusé.
- Vérifier qu’une passkey ouvre `/api/secret/conversations`, que le jeton précédent est révoqué au nouveau déverrouillage et qu’un défi réutilisé, expiré ou provenant d’une autre origine est refusé.
- Vérifier aussi la connexion et le déverrouillage par mot de passe sur le web et sur l’application native.
