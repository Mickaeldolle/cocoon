# Suivi de développement — Cocoon

Ce fichier est la source de suivi opérationnelle du projet. Une tâche n'est cochée qu'après implémentation, tests pertinents exécutés et revue des règles de sécurité applicables.

Légende : `[x]` livré, `[ ]` à faire, `[~]` en cours ou partiellement livré.

## Prochaine étape recommandée

Lancer Hermes en mode dashboard/serve local, renseigner sa passerelle côté API puis valider sur un
development build la boucle **assistant personnel mobile** : reprise de session, réponse réelle,
choix `::ask` et mémoire du profil privé. Les fonctionnalités cachées restent exclues de toute
donnée transmise au modèle jusqu'à leur revue sécurité.

- [x] Ajouter le client API et les requêtes TanStack Query pour les espaces familiaux.
- [x] Créer les écrans : liste, création et détail d'un espace familial.
- [x] Permettre à un `OWNER` ou `ADMIN` d'ajouter un membre depuis le mobile.
- [ ] Ajouter les tests API d'autorisation correspondants et exécuter la suite complète.

## Phase 1 — Fondations

- [x] Monorepo Expo + FastAPI.
- [x] PostgreSQL, Redis et Docker Compose.
- [x] Migrations Alembic.
- [x] Configuration par variables d'environnement.
- [x] Authentification standard : inscription, connexion, rafraîchissement et déconnexion.
- [x] Sessions liées aux appareils, refresh tokens hachés et révocables.
- [x] Stockage du refresh token dans Expo SecureStore.
- [x] Restaurer une session avec un délai réseau borné afin qu’une API inaccessible ne bloque jamais l’écran de démarrage.
- [x] Parcours mobile d'inscription et de connexion.
- [x] Tests de base de l'authentification.

## Phase 2 — Espaces familiaux et contenu

- [x] Modèles `FamilySpace` et adhésions.
- [x] Rôles `OWNER`, `ADMIN` et `MEMBER`.
- [x] API : lister, créer, consulter un espace et ajouter un membre.
- [x] Tests d'invisibilité d'un espace hors adhésion.
- [x] Client API mobile et cache TanStack Query des espaces.
- [x] Écran mobile de liste des espaces.
- [x] Écran mobile de création et détail d'un espace.
- [x] Gestion mobile des membres autorisés.
- [ ] Modèles et API de publications texte.
- [ ] Fil d'actualité et création de publication dans le mobile.
- [ ] Commentaires et réactions.
- [ ] Abstraction de stockage objet compatible S3.
- [ ] Import sécurisé d'images, vidéos et documents.
- [ ] URLs temporaires et contrôle d'accès aux médias/documents.

## Phase 3 — Messagerie normale

- [x] Modèles `Conversation`, `ConversationMember` et `Message`.
- [x] API REST : liste, création, détail, historique et envoi de message.
- [x] WebSocket authentifié par ticket à usage unique.
- [x] Diffusion temps réel de nouveaux messages aux membres.
- [x] Filtrage serveur des conversations dont l'adhésion est cachée.
- [x] Test d'absence d'exposition standard d'une conversation cachée.
- [x] Client API mobile, cache et écrans de conversations.
- [x] Composer et affichage des messages dans le mobile.
- [ ] Reconnexion WebSocket, gestion des erreurs et mise à jour du cache.
- [ ] Accusés de lecture et `last_read_at`.
- [ ] Pièces jointes, avec les contrôles d'accès définis au plan.
- [ ] Tests dédiés aux conversations, messages, lecture et WebSocket.

## Phase 4 — Messagerie cachée (bloquée jusqu'à revue sécurité)

- [x] Champ `ConversationMember.is_hidden` et absence d'endpoint utilisateur de modification.
- [x] Filtrage de l'API standard des conversations cachées.
- [ ] Définir et faire valider le threat model et le protocole de step-up.
- [ ] Geste de découverte, sans rôle d'authentification.
- [ ] Enrôlement et vérification Passkey côté serveur.
- [x] Jeton secret opaque court, séparé des tokens normaux et lié à la session normale.
- [x] Endpoints `/api/secret/*` avec contrôle serveur du jeton normal et de l’accès renforcé.
- [x] Parcours biométrique natif limité au développement Expo Go, associé à la session déjà connectée et désactivé hors développement.
- [x] Déconnexion/verrouillage automatique en arrière-plan, à expiration et purge mémoire/cache secret.
- [~] Passkey native vérifiable par le serveur (le step-up mot de passe est en place ; un pont Expo Passkey reste requis).
- [ ] Protection de l'aperçu multitâche iOS et Android.
- [ ] Notifications génériques par destinataire pour les conversations cachées.
- [ ] Tests d'autorisation REST, WebSocket, recherche et pièces jointes.
- [ ] Revue sécurité indépendante avant mise à disposition.

## Phases ultérieures

- [~] Module de capture universelle : capture brute persistée avant analyse, progression SSE, réponse courte et jusqu’à trois choix exclusifs (tâche, tâche avec rappel, pensée) avec confirmation idempotente ; la validation Expo Go sur appareils réels et les sources calendrier/voix/image/document restent à faire.

- [~] Notifications : outbox et worker serveur, réglage du brief quotidien et endpoint de token d’appareil ; l’enregistrement du token depuis un development build et la validation iOS/Android restent à effectuer.
- [~] Assistant IA personnel : client Expo natif, historique privé, provider OpenAI-compatible et adaptateur Hermes Gateway actifs ; un profil Hermes opaque et une session durable sont liés à chaque compte, les directives `::ask` deviennent jusqu’à trois choix mobiles et aucun repli générique n’est produit. La connexion réelle à un serveur Hermes, le streaming des deltas, la validation sur appareil et les actions confirmables restent à effectuer.
- [~] Mémoire et actions temporelles : échéances uniques (garantie) et périodiques (contrôle, révision), détection de conflits agenda et notification durable ; règles métier officielles, interface de gestion et validation mobile restent à faire.
- [~] Voix Assistant : capture courte avec permission explicite, transcription modifiable via un provider STT privé configurable, réponse synthétisée interruptible ; effacement explicite du cache, choix définitif du moteur et tests iOS/Android restent à réaliser.
- [ ] Ingestion e-mail consentie : connecteur OAuth en lecture seule, synchronisation incrémentale, filtrage d’événements et « paquets d’actions » (agenda, préparation, rappels multiples) confirmables ; aucune conservation ou transmission large des e-mails et aucune action automatique.
- [~] Courses et santé : listes nommées, articles persistés, suivi d’entraînement, cible hebdomadaire et relevés de poids ; les conseils restent non médicaux et l’écran de saisie des relevés reste à finaliser.
- [ ] Renforcement : rate limiting, observabilité, sauvegardes testées, hardening et audit.
- [ ] Étude séparée d'une intégration E2EE basée sur un protocole éprouvé.

## Qualité et exploitation

- [x] Rôle `superadmin`, bootstrap local sécurisé et endpoint d'administration protégé.
- [ ] Interface d'administration : gestion des comptes, des espaces et journal d'audit.
- [x] Typecheck et lint mobile.
- [~] Suite de tests API écrite ; à exécuter systématiquement dans un environnement Python 3.12 disponible.
- [ ] CI : lint, typecheck, tests API et vérification des migrations.
- [ ] Logs structurés, métriques, alertes et health checks de production.
- [ ] Procédure documentée de sauvegarde et restauration PostgreSQL.
