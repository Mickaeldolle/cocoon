# Architecture cible — Assistant Cocoon

## Décision

Cocoon reste un **monolithe modulaire** Expo + FastAPI + PostgreSQL. Il ne devient ni une
collection de microservices ni un agent autonome opaque. L'Assistant est un domaine applicatif
qui orchestre un modèle, des données explicitement partagées et des outils à effets contrôlés.

Chaque action durable suit toujours ce contrat : **comprendre → vérifier → proposer → confirmer
→ exécuter → tracer**.

## MVP actif — client mobile, deux moteurs interchangeables

L’interface Expo ne contient aucun moteur d’agent ni secret de fournisseur. Elle dialogue seulement
avec l’API Cocoon, qui sélectionne explicitement un des deux moteurs : `local` pour l’adaptateur
OpenAI-compatible existant, ou `hermes` pour la passerelle JSON-RPC WebSocket de Hermes Agent.
Il n’existe aucune bascule silencieuse entre les deux moteurs.

En mode Hermes, chaque compte obtient un profil opaque distinct et une session Hermes durable liée
à son `assistant_thread`. Le profil n’active que le toolset de mémoire ; les skills, MCP, sous-agents
et outils d’action ne font pas partie de cette intégration mobile. La directive Hermes
`::ask{question="…" options="…|…"}` devient jusqu’à trois boutons Expo. L’historique visible reste
également stocké dans PostgreSQL, toujours filtré par `user_id`.

En mode local, le noyau récupère les derniers tours et les mémoires personnelles, appelle le modèle,
valide sa réponse JSON puis persiste le tour et les souvenirs sûrs. Dans les deux modes, une erreur
ou une indisponibilité reste visible : aucune réponse déterministe n’est substituée et aucun contenu
de messagerie familiale n’est fourni au moteur.

## Objectifs produit

- Donner l'impression d'échanger avec un assistant personnel attentif, qui sait demander une
  précision lorsqu'il ne comprend pas.
- Ingestion contrôlée de texte, puis de voix, photos et e-mails explicitement connectés.
- Transformer une information en événement, rappel, échéance, préparation ou tâche seulement
  après confirmation explicite.
- Vérifier les conflits d'agenda avant la proposition puis à nouveau juste avant l'écriture.
- Ne consulter que les données volontairement confiées à l'Assistant ; ne jamais accéder aux
  conversations familiales ou cachées.
- Garder une évolution par modules : une nouvelle source ou capacité ne doit pas nécessiter une
  réécriture du mobile ni du noyau Assistant.

## Multi-utilisateur familial, Assistant strictement personnel

Cocoon accueille plusieurs membres d'une famille, mais chaque compte possède son propre espace
Assistant. Il n'existe ni mémoire familiale implicite, ni contexte LLM partagé, ni recherche entre
comptes. Cette isolation s'applique aux faits, e-mails, enregistrements vocaux, agenda, localisation,
rappels, propositions, notifications et journaux d'audit.

La messagerie normale et la messagerie secrète sont des domaines séparés. Elles ne sont jamais
indexées, résumées ou transmises au modèle dans le cadre de l'Assistant personnel. Une capacité
familiale future, par exemple proposer un événement commun, doit être un objet distinct avec des
membres explicitement invités, un périmètre de données minimal et une confirmation de chaque
personne concernée. Elle ne donne aucun accès à la mémoire personnelle des autres membres.

## Limites non négociables

- Le modèle n'est pas une source de vérité pour les dates légales, les règles de garantie ou les
  recommandations médicales. Les règles métier sont versionnées, testées et expliquées.
- Une absence de modèle est visible : le mobile affiche « Le modèle est indisponible » ; aucune
  réponse générique n'est fabriquée à sa place dans le parcours Assistant.
- Les écritures externes (agenda, e-mail, notifications planifiées) exigent une proposition
  confirmée. Les opérations sont idempotentes.
- La localisation ne doit jamais supprimer silencieusement un réveil. Elle peut éclairer une
  proposition après consentement explicite.

## Architecture logique

```text
Expo mobile
  ├─ Assistant UI / voix / permissions / notifications locales
  └─ Client API typé
             │
FastAPI — monolithe modulaire
  ├─ API Assistant
  ├─ Runtime local OpenAI-compatible OU adaptateur Hermes Gateway
  ├─ Orchestrateur agent
  │   ├─ ContextBuilder
  │   ├─ LLMProvider
  │   ├─ PolicyEngine
  │   ├─ ToolRegistry
  │   └─ ProposalExecutor
  ├─ Domaines : mémoire, agenda, rappels, tâches, recettes, connecteurs
  └─ Worker transactionnel
             │
PostgreSQL ── outbox ── notifications / connecteurs OAuth
```

## Clean Architecture pragmatique

Pour chaque nouveau module API, adopter progressivement la structure suivante :

```text
app/modules/<module>/
  domain/          # entités, règles métier pures, ports
  application/     # cas d'usage et transactions
  infrastructure/  # SQLAlchemy, OAuth, fournisseurs LLM, APIs externes
  presentation/    # FastAPI routers et schémas Pydantic
  tests/
```

Les modules existants seront déplacés progressivement, sans « big bang ». Le domaine ne dépend
ni de FastAPI ni de SQLAlchemy ; les interfaces de dépôt, de fournisseur LLM et de connecteur
sont définies côté domaine/application. Les routes restent minces : authentifier, valider,
appeler un cas d'usage, sérialiser.

Dans Expo :

```text
src/features/<feature>/
  api.ts           # contrat généré ou types partagés
  queries.ts       # TanStack Query
  components/
  hooks/
  state.ts
  types.ts
```

Les écrans de `app/` restent des compositions de fonctionnalités. Les appels HTTP ne sont pas
dupliqués dans les composants.

## Noyau agent

### 1. ContextBuilder

Construit un contexte minimal par utilisateur : dernier échange, propositions en attente,
éléments explicitement conservés, créneaux libres pertinents et préférences. Il ne charge jamais
des données de messagerie ni tout l'historique sans nécessité. Chaque requête est filtrée par
`user_id` côté serveur avant toute construction de contexte ; l'application mobile ne constitue
jamais cette barrière d'autorisation.

### 2. AssistantRuntime

Deux adaptateurs explicites sont disponibles. Le runtime local utilise le port OpenAI-compatible
pour LM Studio/Ollama. L’adaptateur Hermes utilise `session.create`, `session.resume` et
`prompt.submit`, puis attend `message.complete`. Son URL et son jeton restent exclusivement dans
l’API. Une réponse invalide, un délai dépassé ou un fournisseur absent produit une erreur explicite
et observable.

Le profil Hermes est `cocoon-<uuid-utilisateur>` : il ne contient ni nom ni e-mail. Sa configuration
est créée avec mémoire uniquement. Cette frontière par profil est obligatoire, car une mémoire
Hermes partagée entre profils briserait l’isolation familiale.

### 3. PolicyEngine

Décide ce qui est autorisé : pas de conseil médical, pas de donnée cachée, pas d'action externe
sans confirmation, pas de règle légale inventée. Il impose aussi les limites de taille de contexte
et le niveau de consentement requis pour chaque outil.

### 4. ToolRegistry

Chaque capacité est un outil typé et déclaratif :

| Outil | Lecture | Écriture confirmée |
| --- | --- | --- |
| Mémoire | faits explicitement partagés | note/fait personnel |
| Agenda | plages et conflits | événement local/externe |
| Rappels | échéances planifiées | rappel unique/récurrent |
| Préparation | contexte choisi | tâches/checklist |
| Recettes | ingrédients déclarés | liste de courses |
| E-mail | messages connectés et filtrés | paquets d'actions |

Un outil reçoit des entrées Pydantic validées et retourne un résultat typé. Le modèle ne peut pas
appeler directement une API externe.

### 5. ProposalExecutor et journal

Une proposition est immuable, liée à son utilisateur et à une version du contexte. Sa confirmation
est idempotente. L'exécution conserve un journal : outil, paramètres masqués si nécessaire,
résultat, identifiant de ressource et horodatage.

## Modèle de données cible

Les tables actuelles forment le début de cette base. Les ajouts à standardiser sont :

- `assistant_sources` : origine consentie d'une information (texte, voix, photo, e-mail), durée
  de conservation et empreinte de contenu.
- `personal_facts` : fait structuré, type, valeur JSON validée, confiance, source et cycle de vie.
- `action_proposals` : proposition immuable, statut, confirmation et ressource créée.
- `calendar_events` : événement privé, fuseau, provenance et identifiant externe éventuel.
- `reminder_rules` : échéance unique ou périodique, date d'ancrage, avance, prochain passage.
- `checklists` et `checklist_items` : préparation contextualisée, par exemple une sortie scolaire.
- `connector_connections` : fournisseur, scopes, état de synchronisation et jetons chiffrés côté
  serveur uniquement.
- `audit_events` : événement technique et métier, sans contenu sensible inutile.

Pour une garantie : date de fin + avance de sept jours → rappel unique. Pour un contrôle technique
ou une révision : date d'ancrage + périodicité + avance → règle récurrente. Les calculs appartiennent
au moteur temporel, pas au texte libre du modèle.

## Agenda et conflits

1. Le modèle extrait une intention et un créneau proposé.
2. Le serveur valide le fuseau, la durée et les chevauchements.
3. En cas de conflit, il retourne une réponse conversationnelle avec des alternatives ; il ne crée
   aucune proposition d'écriture.
4. À la confirmation, le serveur vérifie à nouveau le chevauchement dans la transaction.
5. L'événement est créé localement ou synchronisé via le connecteur autorisé.

La première version utilise l'agenda privé Cocoon. Google Calendar sera une extension de
connecteur : OAuth avec le scope minimal, stockage chiffré de refresh tokens, synchronisation
incrémentale avec `syncToken`, révocation et resynchronisation en cas d'expiration. Aucun calendrier
externe n'est lu sans connexion explicite.

## Rappels et réveils

Le worker transactionnel PostgreSQL planifie les rappels de domaine et inscrit une notification dans
l'outbox. Le worker d'envoi ne déduit aucune donnée sensible : la notification push reste générique.

Pour un réveil, le serveur peut proposer l'horaire, mais le téléphone programme une **notification
locale** confirmée. Cela évite de dépendre du réseau au moment critique. Les capacités audio,
silencieux, autorisations exactes et restrictions de batterie restent celles d'iOS/Android ; Cocoon
ne promet pas de contourner le système.

## Voix

La voix utilise le même `AssistantTurn` que le texte :

```text
maintenir pour parler → enregistrement temporaire → transcription → texte modifiable
→ AssistantTurn → réponse texte → lecture vocale interruptible
```

- Enregistrement court, indicateur clair, permission micro à l'action et suppression du fichier
  temporaire après transcription par défaut.
- `SpeechProvider` et `TranscriptionProvider` abstraits : implémentation appareil, locale ou
  serveur sans modification de l'UI métier.
- La transcription est toujours affichée avant l'envoi ; la réponse reste lisible si la synthèse
  est indisponible.

## E-mail et sources externes

L'e-mail est un connecteur, non une permission globale de surveillance. Le flux est :

```text
OAuth lecture seule → sync incrémentale → filtre de pertinence → extraction structurée
→ paquet d'actions proposé → confirmation partielle ou totale
```

Un e-mail d'école peut ainsi générer un événement, une checklist « gourde / casquette » et deux
rappels. Les contenus bruts ne sont pas indexés ni envoyés largement au modèle ; celui-ci reçoit
seulement le message explicitement sélectionné ou l'extrait nécessaire, selon le consentement.

## Recherche sémantique et RAG

Ne pas déployer une base vectorielle séparée au début. PostgreSQL reste la source de vérité ;
ajouter `pgvector` lorsque les notes, documents et photos exigent une recherche sémantique. Un
résultat RAG est un contexte non fiable : il doit mentionner sa source et ne déclenche jamais une
action sans les validations normales.

## Stack recommandée

| Besoin | Choix initial | Évolution |
| --- | --- | --- |
| Mobile | Expo SDK 57, React Native, TypeScript strict, Expo Router | development builds pour permissions natives |
| Données client | TanStack Query, Zustand seulement pour état local | génération des types depuis OpenAPI |
| API | FastAPI, Pydantic v2, SQLAlchemy, Alembic | ports/adaptateurs par domaine |
| Données | PostgreSQL | `pgvector` quand le besoin est mesuré |
| Tâches différées | outbox PostgreSQL + worker idempotent | file dédiée seulement si la charge le justifie |
| Agent | endpoint OpenAI-compatible ou Hermes Gateway privé | streaming SSE mobile puis actions confirmables |
| Agenda/e-mail | connecteurs OAuth dédiés | Google Calendar puis Gmail, jamais dans le noyau agent |
| Voix | `expo-audio` + `expo-speech` derrière des ports | STT/TTS privé ou on-device selon arbitrage |
| Qualité | Ruff, Pytest, ESLint, TypeScript, Prettier | CI, tests de contrat OpenAPI, E2E mobile |
| Observabilité | logs structurés, audit, métriques et traces | alertes et tableaux d'exploitation |

## Feuille de route de livraison

### Phase A — Stabiliser le socle Assistant

1. Valider une conversation réelle Hermes sur le poste puis sur un development build.
2. Diffuser les deltas Hermes en SSE vers Expo avec annulation explicite.
3. Finaliser les schémas de proposition et leur journal d'audit.
4. Terminer les tests d’erreurs, délais, reconnexion et idempotence.
5. Générer les types TypeScript à partir d'OpenAPI et vérifier leur dérive en CI.

### Phase B — Temps et agenda Cocoon

1. Échéances uniques, récurrentes et worker fiable.
2. Agenda privé, conflits, alternatives et interface de gestion.
3. Checklists et paquets d'actions confirmables.
4. Development build pour notifications locales et rappels testés sur téléphone.

### Phase C — Voix

1. Enregistrement court et transcription modifiable.
2. Réponse lue, arrêt de lecture et états d'erreur.
3. Choix documenté du fournisseur STT/TTS et évaluation confidentialité/latence/coût.

### Phase D — Connecteurs consentis

1. Google Calendar en lecture, synchronisation incrémentale et conflits.
2. Écriture d'événement confirmée, avec révocation et reprise sur erreur.
3. Gmail lecture seule : watch, synchronisation incrémentale, filtres et paquets d'actions.

### Phase E — Enrichissement

1. Photos/OCR, ingrédients et recettes.
2. `pgvector` et RAG sourcé si le volume le justifie.
3. Géofencing opt-in pour des suggestions, jamais pour une action silencieuse.

## Critères avant chaque nouvelle brique

Une capacité est acceptée seulement si elle a : un propriétaire métier, un contrat d'entrée/sortie
typé, une règle de consentement, une stratégie d'échec, des logs sans secrets, des tests
d'autorisation/idempotence et une migration réversible. Cette discipline est ce qui permet
d'ajouter des briques sans recoder le projet.
