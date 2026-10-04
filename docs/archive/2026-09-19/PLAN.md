# PLAN.md — Application familiale privée avec messagerie cachée

## 1. Objectif du projet

Construire une application mobile cross-platform iOS / Android destinée à un usage familial.

L'application doit être une application utile et cohérente en elle-même, avec notamment :

- plusieurs espaces familiaux privés ;
- partage de publications ;
- partage d'images, vidéos et documents ;
- messagerie ;
- assistant IA strictement personnel ;
- notifications ;
- gestion des profils et membres.

La fonctionnalité centrale sensible est une **messagerie cachée**.

Certains salons peuvent être invisibles pour un utilisateur donné et ne devenir accessibles qu'après :

1. réalisation d'un schéma / geste secret dans l'interface ;
2. authentification renforcée via Passkey ;
3. création d'une session d'accès secret courte durée.

Le statut caché d'un salon est **individuel par utilisateur** et administré uniquement manuellement en base de données.

---

# 2. Principes fondamentaux

## 2.1 KISS

L'architecture doit rester simple tant qu'une complexité supplémentaire n'est pas nécessaire.

À éviter au MVP :

- microservices ;
- Kubernetes ;
- CQRS ;
- event sourcing ;
- GraphQL ;
- duplication inutile des modèles ;
- architecture prématurément distribuée.

Le backend doit être un **monolithe modulaire**.

---

## 2.2 Backend source de vérité

Les règles de sécurité ne doivent jamais dépendre uniquement de l'application Expo.

Le frontend ne doit pas être responsable de filtrer les données auxquelles l'utilisateur n'a pas accès.

Toutes les autorisations doivent être appliquées côté API.

---

## 2.3 Séparation des domaines

Les trois domaines majeurs doivent rester clairement séparés :

1. espaces familiaux ;
2. messagerie ;
3. assistant IA personnel.

L'assistant IA ne doit pas avoir accès par défaut aux conversations cachées.

---

# 3. Stack technique retenue

## Mobile

- Expo
- React Native
- TypeScript
- Expo Router
- TanStack Query
- Zustand
- React Hook Form
- Zod
- Expo SecureStore
- Expo Notifications

L'application doit utiliser des **development builds Expo / EAS**, et ne pas dépendre d'Expo Go pour les fonctionnalités natives sensibles.

---

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy 2
- Alembic

---

## Données

- PostgreSQL
- Redis
- stockage objet compatible S3

Le stockage objet pourra être :

- MinIO ;
- Cloudflare R2 ;
- AWS S3 ;
- Scaleway Object Storage ;
- ou un autre provider compatible S3.

L'application ne doit pas dépendre directement d'un provider spécifique.

---

## Temps réel

- WebSocket
- Redis Pub/Sub si nécessaire

REST reste utilisé pour les opérations classiques.

WebSocket est utilisé uniquement pour le temps réel.

---

## Infrastructure

- VPS Linux
- Docker
- Docker Compose
- Caddy comme reverse proxy HTTPS
- EAS Build pour Android / iOS

Pas de Kubernetes au MVP.

---

# 4. Organisation du repository

Utiliser un monorepo contenant deux applications indépendantes.

```text
project/
├── apps/
│   ├── mobile/
│   └── api/
│
├── packages/
│   ├── contracts/
│   └── config/
│
├── docs/
│
├── docker/
│
├── PLAN.md
└── README.md
```

Les applications `mobile` et `api` doivent pouvoir être développées et déployées séparément.

---

# 5. Architecture globale

```text
                    iOS / Android
                         │
                    HTTPS / WSS
                         │
                         ▼
                    ┌────────┐
                    │ Caddy  │
                    └───┬────┘
                        │
                        ▼
                  ┌───────────┐
                  │ FastAPI   │
                  │ REST + WS │
                  └─────┬─────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
          ▼             ▼             ▼
     PostgreSQL       Redis        S3/MinIO

                        │
                        ▼
                Assistant service
                        │
                        ▼
                       LLM
```

---

# 6. Espaces familiaux

Un utilisateur peut appartenir à plusieurs espaces familiaux.

Exemples :

```text
Utilisateur
├── Famille proche
├── Grands-parents
├── Cousins
└── Famille élargie
```

Il ne doit donc pas exister de simple `user.family_id`.

Utiliser une relation many-to-many.

## Modèle conceptuel

```text
FamilySpace
- id
- name
- description
- avatar
- created_by
- created_at
- updated_at
```

```text
FamilySpaceMember
- family_space_id
- user_id
- role
- joined_at
```

Rôles initiaux :

- OWNER
- ADMIN
- MEMBER

Ne pas créer un système de permissions excessivement complexe pour le MVP.

---

# 7. Contenu familial

Un espace familial peut contenir :

- publications ;
- images ;
- vidéos ;
- documents ;
- albums ;
- événements ;
- commentaires ;
- réactions.

Le contenu d'un espace ne doit être accessible qu'aux membres autorisés de cet espace.

---

# 8. Stockage des médias

Ne pas stocker directement les fichiers binaires importants dans PostgreSQL.

PostgreSQL contient les métadonnées.

Le stockage objet contient les fichiers.

Exemple :

```text
Media
- id
- storage_key
- mime_type
- size
- checksum
- created_by
- created_at
```

Les URLs de stockage privées ne doivent pas devenir des liens permanents publics.

Utiliser des URLs signées temporaires si nécessaire.

---

# 9. Messagerie

## 9.1 Modèle unique de salon

Ne pas créer de types métiers distincts :

- DM ;
- GROUP.

Un salon est simplement une conversation contenant deux membres ou plus.

```text
2 membres   => équivalent d'un DM
3+ membres  => équivalent d'un groupe
```

Le nombre de membres suffit à déterminer le comportement d'interface éventuel.

---

## 9.2 Conversation

```text
Conversation
- id
- name nullable
- created_by
- created_at
- updated_at
```

`name` est nullable.

Pour une conversation à deux personnes sans nom explicite, l'application peut afficher le nom de l'autre participant.

---

## 9.3 Membres

```text
ConversationMember
- conversation_id
- user_id
- role
- is_hidden
- is_muted
- is_archived
- is_pinned
- last_read_at
- joined_at
```

La clé fonctionnelle importante est :

```text
ConversationMember.is_hidden
```

---

# 10. Fonctionnement des salons cachés

## 10.1 Statut individuel

Un salon n'est jamais "secret" globalement.

Le statut caché est individuel.

Exemple :

```text
Conversation #42

Utilisateur A -> is_hidden = false
Utilisateur B -> is_hidden = true
Utilisateur C -> is_hidden = false
```

Résultat :

- A voit le salon normalement ;
- B ne voit pas le salon dans l'interface standard ;
- C voit le salon normalement.

Le comportement de B n'a aucun impact sur A ou C.

---

## 10.2 Administration du statut caché

`is_hidden` ne doit jamais être configurable depuis l'application.

Il ne doit exister dans l'interface :

- aucun bouton "Masquer" ;
- aucun bouton "Rendre secret" ;
- aucune option correspondante ;
- aucun paramètre utilisateur correspondant.

Pour le MVP, `is_hidden` est modifié **manuellement en base de données par un administrateur technique**.

Exemple :

```sql
UPDATE conversation_member
SET is_hidden = TRUE
WHERE conversation_id = :conversation_id
  AND user_id = :user_id;
```

Il ne doit pas exister d'endpoint utilisateur standard permettant de modifier cette propriété.

---

# 11. API standard et API cachée

## API standard

Exemple :

```http
GET /api/conversations
```

Cette API ne doit retourner que les conversations du membre avec :

```text
is_hidden = false
```

Le frontend ne doit jamais recevoir toutes les conversations pour ensuite effectuer :

```typescript
conversations.filter(c => !c.isHidden)
```

Cette approche est interdite.

---

## API cachée

Exemple :

```http
GET /api/secret/conversations
```

Cette API ne retourne que les conversations du membre avec :

```text
is_hidden = true
```

Elle exige une authentification renforcée valide.

---

# 12. Non-divulgation avant déverrouillage

Avant authentification renforcée, l'application ne doit idéalement connaître :

- ni l'existence du salon caché ;
- ni son nom ;
- ni ses participants ;
- ni son dernier message ;
- ni son nombre de messages ;
- ni ses pièces jointes.

Une réponse API standard ne doit pas contenir :

```json
{
  "id": "...",
  "is_hidden": true
}
```

pour laisser Expo masquer ensuite la conversation.

Le salon ne doit tout simplement pas apparaître dans la réponse.

---

# 13. Déverrouillage de l'espace caché

Le flux est :

```text
Application normale
        │
        ▼
Schéma / geste secret
        │
        ▼
Demande d'authentification renforcée
        │
        ▼
Passkey
        │
        ▼
Vérification côté backend
        │
        ▼
Session secrète courte durée
        │
        ▼
Liste des salons cachés
```

---

# 14. Schéma / geste secret

Le schéma sert uniquement de mécanisme de découverte / dissimulation.

Exemples possibles :

- plusieurs clics sur un élément ;
- pression longue ;
- combinaison de gestes ;
- séquence particulière.

Ce mécanisme ne doit **jamais être considéré comme une authentification**.

Un utilisateur qui découvre le geste ne doit pas pouvoir accéder aux conversations sans Passkey valide.

---

# 15. Passkey

L'authentification renforcée repose sur une Passkey.

Une Passkey n'est pas une empreinte digitale.

L'empreinte, Face ID, le PIN ou un autre mécanisme local peut servir à autoriser l'utilisation de la Passkey.

Le backend vérifie une preuve cryptographique.

Il ne reçoit jamais la donnée biométrique.

## Modèle conceptuel

```text
PasskeyCredential
- id
- user_id
- credential_id
- public_key
- counter
- device_name
- created_at
- last_used_at
```

Le secret cryptographique privé doit rester sur l'appareil / dans le credential provider.

---

# 16. Sessions

Séparer la session normale et l'accès renforcé.

## Session standard

Après authentification normale :

```text
normal_access_token
refresh_token
```

Le refresh token doit être stocké dans un mécanisme sécurisé tel que SecureStore.

---

## Session secrète

Après Passkey :

```text
secret_access_token
```

Le token secret doit être de courte durée.

Ordre de grandeur initial :

```text
normal access token : 15 à 60 minutes
secret access token : environ 5 minutes
```

Ces durées restent configurables.

Les endpoints secrets doivent exiger explicitement un scope ou niveau d'authentification renforcé.

Exemple conceptuel :

```json
{
  "sub": "user-id",
  "scope": "secret",
  "auth_time": "..."
}
```

Ne jamais utiliser un simple booléen local Expo comme preuve d'accès secret.

---

# 17. Verrouillage automatique

L'espace secret doit se reverrouiller lorsqu'un événement sensible se produit.

Au minimum :

- application envoyée en arrière-plan ;
- fermeture de l'application ;
- logout ;
- expiration de la session secrète ;
- redémarrage de l'application.

Lors du verrouillage :

- supprimer le secret access token local ;
- vider l'état React lié aux conversations cachées ;
- vider le cache TanStack Query des données cachées ;
- ne conserver aucune donnée sensible inutile en mémoire.

---

# 18. Protection de l'aperçu multitâche

Quand l'application passe en arrière-plan depuis une conversation cachée, le contenu secret ne doit pas rester visible dans l'aperçu du sélecteur d'applications.

Prévoir un écran neutre / protection visuelle avant ou pendant le passage en arrière-plan.

Cette fonctionnalité doit être testée séparément sur :

- iOS ;
- Android.

---

# 19. Notifications

Les notifications doivent respecter l'état individuel `ConversationMember.is_hidden`.

## Conversation visible

La notification peut éventuellement contenir :

- nom de l'expéditeur ;
- aperçu du message ;
- nom du salon.

---

## Conversation cachée

Ne jamais mettre dans le push :

- contenu du message ;
- nom du salon ;
- nom de l'expéditeur ;
- nom des pièces jointes ;
- autre métadonnée sensible.

Utiliser une notification générique, par exemple :

```text
Nouvelle notification
```

ou permettre de désactiver les notifications cachées.

La décision doit être prise **par destinataire**.

Une même conversation peut produire :

```text
Utilisateur A -> notification normale
Utilisateur B -> notification générique
```

selon `ConversationMember.is_hidden`.

---

# 20. Stockage local des conversations cachées

Minimiser le stockage local durable.

Au MVP, privilégier :

- aucun historique secret durable si ce n'est pas nécessaire ;
- récupération après authentification renforcée ;
- suppression du cache au verrouillage.

Ne jamais stocker des messages secrets en clair dans AsyncStorage.

SecureStore doit être réservé aux petites informations sensibles comme :

- refresh token ;
- identifiants de clé ;
- secrets de device.

Ne pas utiliser SecureStore comme base de données de messages.

---

# 21. Temps réel

Utiliser REST + WebSocket.

REST :

- liste des conversations ;
- historique ;
- création de contenu ;
- profils ;
- espaces familiaux ;
- documents ;
- authentification.

WebSocket :

- nouveaux messages ;
- accusés de lecture ;
- typing ;
- présence si nécessaire ;
- événements temps réel.

Exemple :

```text
POST message
    │
    ▼
PostgreSQL
    │
    ▼
Redis Pub/Sub
    │
    ▼
WebSocket
    │
    ▼
autres appareils
```

Redis Pub/Sub devient surtout utile si plusieurs instances FastAPI sont exécutées.

---

# 22. Assistant IA

L'assistant IA est **strictement personnel**.

Il n'existe pas d'assistant familial.

Chaque utilisateur possède son propre assistant.

```text
User
└── PersonalAssistant
    ├── Conversations
    ├── Messages
    ├── Memory
    └── Configuration
```

Les données d'un utilisateur ne doivent jamais être accessibles par l'assistant d'un autre utilisateur.

---

## 22.1 Accès au LLM

Expo ne doit jamais parler directement au LLM.

Interdit :

```text
Expo -> Ollama / vLLM / provider
```

Architecture :

```text
Expo
  │
  ▼
FastAPI
  │
  ▼
Assistant service
  │
  ▼
LLM
```

Le provider doit pouvoir être interchangeable.

Exemples :

- LLM self-hosted sur VPS ;
- Ollama ;
- vLLM ;
- API OpenAI-compatible ;
- autre provider.

---

## 22.2 Isolation avec la messagerie cachée

Par défaut :

```text
Assistant IA X Conversations cachées
```

L'assistant ne doit pas :

- lire les conversations cachées ;
- indexer leurs messages ;
- créer des embeddings à partir de leurs messages ;
- stocker leurs données dans sa mémoire ;
- transmettre leurs pièces jointes au LLM.

Toute évolution future sur ce point devra être explicitement conçue et validée.

---

# 23. Architecture Expo

Organisation feature-based recommandée :

```text
apps/mobile/
├── app/
│   ├── (public)/
│   ├── (auth)/
│   ├── (app)/
│   ├── (secret)/
│   └── _layout.tsx
│
├── features/
│   ├── auth/
│   ├── family-spaces/
│   ├── feed/
│   ├── messaging/
│   ├── secret-access/
│   ├── assistant/
│   ├── media/
│   ├── notifications/
│   └── profile/
│
├── components/
├── hooks/
├── services/
├── stores/
├── lib/
└── types/
```

Ne pas mélanger toute la logique métier dans les composants React.

---

# 24. Gestion de l'état mobile

## TanStack Query

Utiliser TanStack Query pour les données serveur :

- conversations ;
- messages ;
- posts ;
- family spaces ;
- documents ;
- profils.

---

## Zustand

Utiliser Zustand uniquement pour l'état local :

- espace familial actif ;
- état de navigation ;
- état d'interface ;
- données locales non serveur.

Éviter de dupliquer les réponses API dans Zustand si TanStack Query les gère déjà.

---

# 25. Architecture FastAPI

Utiliser un monolithe modulaire.

```text
apps/api/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── exceptions.py
│   │
│   ├── modules/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── devices/
│   │   ├── passkeys/
│   │   ├── family_spaces/
│   │   ├── feed/
│   │   ├── media/
│   │   ├── conversations/
│   │   ├── messages/
│   │   ├── secret_access/
│   │   ├── notifications/
│   │   └── assistant/
│   │
│   └── shared/
│
├── migrations/
├── tests/
└── pyproject.toml
```

Un module peut contenir par exemple :

```text
conversations/
├── models.py
├── schemas.py
├── repository.py
├── service.py
└── router.py
```

Les routers ne doivent pas contenir toute la logique métier.

---

# 26. Worker

Prévoir un worker séparé de l'API pour les tâches asynchrones :

- notifications push ;
- génération de miniatures ;
- traitement vidéo ;
- emails ;
- cleanup ;
- jobs IA longs.

Architecture :

```text
FastAPI
   │
   ▼
Redis / queue
   │
   ▼
Worker
```

Choisir une solution simple au départ.

Ne pas introduire Celery automatiquement si une alternative plus légère suffit.

---

# 27. Modèle de données initial

Liste indicative des tables principales :

```text
user
device
session
passkey_credential

family_space
family_space_member

post
comment
reaction

media
document
album

conversation
conversation_member
message
message_attachment

notification

assistant_conversation
assistant_message
assistant_memory
```

Une seule base PostgreSQL au MVP.

Ne pas séparer artificiellement les données dans plusieurs bases.

---

# 28. Autorisation

Toutes les ressources doivent être récupérées dans le contexte de l'utilisateur courant.

Ne jamais considérer comme fiable un :

```text
user_id
family_space_id
conversation_id
```

simplement parce qu'il provient du frontend.

Exemple dangereux :

```python
user_id = request.user_id
```

L'identité utilisateur doit provenir de la session authentifiée.

Pour chaque conversation :

1. vérifier que le current_user est membre ;
2. vérifier son `ConversationMember` ;
3. vérifier le contexte standard ou secret ;
4. appliquer les droits correspondants.

---

# 29. Tests de sécurité obligatoires

Ajouter des tests dédiés aux frontières d'autorisation.

Exemple :

```text
Conversation #42

A -> membre, visible
B -> membre, cachée
C -> non membre
```

Tests minimum :

```text
A + API standard -> 200
A + API secret   -> ne doit pas exposer #42 comme salon caché

B + API standard -> #42 absente
B + API secret sans step-up -> 401/403
B + API secret avec step-up -> #42 accessible

C + API standard -> inaccessible
C + API secret -> inaccessible
```

Tester également :

- messages ;
- attachments ;
- notifications ;
- WebSocket ;
- endpoints de recherche ;
- téléchargement de fichiers.

Il ne doit pas être possible de contourner le filtrage en connaissant directement l'ID d'une conversation cachée.

---

# 30. WebSocket et conversations cachées

Le serveur WebSocket doit appliquer les mêmes autorisations que REST.

Une conversation cachée ne doit pas être révélée à un utilisateur avant authentification renforcée via :

- événement `new_message` ;
- badge ;
- typing ;
- présence ;
- compteur de non-lus ;
- nom de conversation ;
- événement `conversation_updated`.

Le canal temps réel ne doit pas devenir une fuite indirecte.

---

# 31. Sécurité des pièces jointes

Un utilisateur ne doit pas pouvoir contourner le système de salon caché en utilisant directement l'URL d'une pièce jointe.

Lors de l'accès à une pièce jointe :

1. authentifier l'utilisateur ;
2. retrouver la conversation / ressource correspondante ;
3. vérifier le membership ;
4. vérifier si elle est cachée pour cet utilisateur ;
5. exiger le step-up si nécessaire ;
6. seulement ensuite générer l'accès temporaire au fichier.

---

# 32. E2EE

Le chiffrement end-to-end est souhaitable à terme pour la messagerie.

Cependant :

- ne pas inventer de protocole cryptographique ;
- ne pas coder de chiffrement maison ;
- ne pas bloquer le MVP sur une implémentation E2EE improvisée.

L'architecture doit permettre une future intégration d'un protocole reconnu.

L'E2EE doit faire l'objet d'un plan de sécurité séparé avant implémentation.

---

# 33. Déploiement VPS initial

Architecture recommandée :

```text
VPS
├── Caddy
├── FastAPI
├── Worker
├── PostgreSQL
├── Redis
├── MinIO éventuellement
└── LLM éventuellement
```

Chaque composant tourne dans Docker.

Utiliser Docker Compose.

Le LLM ne doit pas exposer directement son port sur Internet.

Exemple :

```text
Internet
   │
   ▼
Caddy :443
   │
   ▼
FastAPI
   │
   └── réseau Docker privé -> LLM
```

---

# 34. Roadmap de développement

## Phase 1 — Fondations

- monorepo ;
- Expo ;
- FastAPI ;
- PostgreSQL ;
- migrations ;
- configuration ;
- authentification standard ;
- modèles User / Device / Session ;
- tests de base.

---

## Phase 2 — Espaces familiaux

- FamilySpace ;
- memberships ;
- rôles ;
- feed ;
- publications ;
- médias ;
- documents.

---

## Phase 3 — Messagerie normale

- Conversation ;
- ConversationMember ;
- Message ;
- pièces jointes ;
- REST ;
- WebSocket ;
- accusés de lecture.

---

## Phase 4 — Messagerie cachée

- `ConversationMember.is_hidden` ;
- filtrage serveur ;
- aucune option UI pour modifier `is_hidden` ;
- geste secret ;
- Passkey ;
- secret access token ;
- endpoints secrets ;
- verrouillage automatique ;
- protection multitâche ;
- purge du cache secret ;
- notifications génériques ;
- tests d'autorisation spécifiques.

Cette phase est critique et doit faire l'objet d'une revue sécurité.

---

## Phase 5 — Notifications

- devices ;
- Expo Push ;
- worker ;
- politique spécifique pour conversations cachées.

---

## Phase 6 — Assistant IA personnel

- conversations IA ;
- provider configurable ;
- LLM self-hosted possible ;
- mémoire privée ;
- isolation stricte par utilisateur.

Aucun accès aux conversations cachées.

---

## Phase 7 — Renforcement

- threat model ;
- audit sécurité ;
- tests d'intrusion ;
- hardening VPS ;
- rate limiting ;
- rotation / révocation des sessions ;
- gestion multi-device ;
- étude E2EE.

---

# 35. Règles pour l'agent Codex

Codex doit respecter les règles suivantes.

1. Lire `PLAN.md` avant toute décision d'architecture.
2. Suivre KISS.
3. Ne pas introduire de dépendance ou abstraction complexe sans justification.
4. Ne jamais réécrire de gros fichiers inutilement.
5. Préférer des modifications petites et ciblées.
6. Ne jamais déplacer une règle de sécurité uniquement côté frontend.
7. Toute feature manipulant des ressources privées doit inclure des tests d'autorisation.
8. Toute évolution liée aux salons cachés doit vérifier REST, WebSocket, notifications et fichiers.
9. `ConversationMember.is_hidden` est individuel.
10. `is_hidden` n'est jamais modifiable depuis l'interface utilisateur.
11. Ne pas créer d'endpoint utilisateur permettant de modifier `is_hidden`.
12. L'API standard ne doit jamais retourner les conversations cachées.
13. Le geste secret n'est jamais une authentification.
14. La Passkey / step-up authentication est obligatoire pour accéder aux conversations cachées.
15. L'assistant IA est personnel uniquement.
16. L'assistant IA n'a aucun accès aux conversations cachées par défaut.
17. Ne jamais inventer de chiffrement maison.
18. Ne pas introduire de microservices au MVP.
19. Les identités et permissions doivent toujours être validées côté backend.
20. Avant de terminer une feature, exécuter les tests correspondants et vérifier les régressions.

---

# 36. Priorités

Ordre de priorité :

```text
1. Sécurité / confidentialité
2. Correction fonctionnelle
3. Simplicité
4. Maintenabilité
5. UX
6. Performance
7. Optimisations avancées
```

La sécurité ne doit pas être sacrifiée pour simplifier l'interface.

La complexité doit cependant rester proportionnée au besoin réel.

---

# 37. Définition synthétique du produit

Application mobile familiale privée cross-platform permettant à un utilisateur d'appartenir à plusieurs espaces familiaux afin de partager publications, images, vidéos, documents et messages.

La messagerie utilise un modèle unique de salons contenant deux membres ou plus.

Chaque membre possède un état individuel `is_hidden` pour chaque salon.

Ce statut est configuré exclusivement manuellement en base de données et n'est exposé par aucune option utilisateur.

Lorsqu'un salon est caché pour un utilisateur, il disparaît totalement de l'expérience standard et de l'API standard de cet utilisateur.

L'accès à ses salons cachés nécessite :

```text
geste secret
    +
Passkey
    +
session renforcée courte durée
```

L'application comprend également un assistant IA strictement personnel, dont les données sont isolées entre utilisateurs et qui ne dispose d'aucun accès par défaut aux conversations cachées.

L'ensemble repose sur Expo / React Native côté mobile et FastAPI / PostgreSQL côté backend, avec une architecture simple, modulaire, testée et orientée sécurité.
