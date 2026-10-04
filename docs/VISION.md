# ROADMAP — Assistant IA personnel et familial intelligent

## 1. Vision générale

L'objectif du projet est de construire progressivement un **assistant IA personnel intelligent**, utilisable par plusieurs membres d'une même famille.

Chaque utilisateur doit disposer de son propre assistant contextuel, capable au fil du temps de :

- apprendre à connaître son utilisateur ;
- mémoriser les informations réellement utiles ;
- comprendre ses préférences ;
- connaître ses projets ;
- suivre ses objectifs ;
- retenir certaines décisions ;
- comprendre ses habitudes ;
- retrouver des informations anciennes lorsqu'elles redeviennent pertinentes ;
- adapter sa manière de répondre ;
- distinguer faits, préférences, contraintes, intérêts et suppositions ;
- remettre en question les informations qu'il possède lorsqu'elles sont devenues obsolètes ;
- prendre en compte les contraintes objectives avant les préférences personnelles.

À terme, l'objectif est de tendre vers un assistant proche, dans l'esprit, d'un **Jarvis personnel** :

```text
conversation
+
memory
+
reasoning
+
tools
+
planning
+
proactivity
+
voice
```

Mais le développement doit rester progressif.

La première priorité n'est pas de construire immédiatement cet assistant final.

La première priorité est :

> Construire une excellente boucle de traitement d'un message permettant à chaque utilisateur de disposer d'une mémoire personnelle fiable, isolée et réutilisable dans les conversations futures.

---

# 2. Principe fondamental

L'application ne doit pas être pensée comme un simple chatbot :

```text
Utilisateur
    ↓
LLM
    ↓
Réponse
```

Elle doit progressivement fonctionner ainsi :

```text
Utilisateur authentifié
        ↓
Message
        ↓
Analyse du contexte
        ↓
Recherche des mémoires accessibles
        ↓
Construction du contexte pertinent
        ↓
LLM
        ↓
Réponse
        ↓
Analyse de l'interaction
        ↓
Extraction éventuelle de nouvelles informations
        ↓
Mise à jour de la mémoire appropriée
```

À plus long terme :

```text
Utilisateur
     ↓
Assistant
     ↓
Mémoire
+
Contexte
+
Raisonnement
+
Outils
+
Planification
     ↓
Réponse ou action
     ↓
Observation du résultat
     ↓
Mise à jour des connaissances
```

La mémoire ne doit donc jamais être une simple copie de l'historique des conversations.

---

# 3. Le projet doit évoluer à partir de l'existant

Le projet existe déjà.

Il ne faut pas repartir arbitrairement de zéro.

Avant toute refactorisation importante, Codex doit analyser le projet existant et déterminer :

```text
KEEP
REFACTOR
REMOVE
REBUILD
```

pour les composants principaux.

Analyser notamment :

- architecture globale ;
- frontend ;
- backend ;
- base de données ;
- authentification ;
- gestion des utilisateurs ;
- gestion des conversations ;
- stockage des messages ;
- intégration Ollama ;
- prompts existants ;
- streaming éventuel ;
- gestion des erreurs ;
- timeouts ;
- tests ;
- configuration ;
- sécurité ;
- séparation des responsabilités.

La règle générale doit rester :

> Modifier progressivement ce qui existe, plutôt que reconstruire l'ensemble de l'application sans justification.

---

# 4. Contrainte principale : LLM local avec Ollama

Le projet utilise actuellement un **LLM local via Ollama**.

Cette contrainte doit être considérée comme normale et structurante.

Un modèle local peut :

- mettre plusieurs secondes avant de commencer à répondre ;
- générer lentement ;
- dépendre fortement des ressources CPU/GPU disponibles ;
- nécessiter plusieurs appels pour certaines opérations ;
- être temporairement indisponible ou chargé.

## Règle importante

Il ne doit pas exister de timeout applicatif court qui coupe artificiellement une réponse simplement parce que le modèle prend du temps.

Éviter par exemple les timeouts arbitraires de :

```text
10 secondes
20 secondes
30 secondes
```

si leur seul objectif est de considérer une génération lente comme une erreur.

Les timeouts doivent uniquement protéger contre de véritables problèmes :

- serveur inaccessible ;
- connexion impossible ;
- requête réellement bloquée ;
- erreur réseau ;
- annulation demandée par l'utilisateur.

---

# 5. Expérience utilisateur autour de la lenteur

La lenteur du modèle ne doit pas donner l'impression que l'application est figée.

Prévoir :

- streaming de la réponse ;
- indication de génération ;
- possibilité d'annulation ;
- gestion claire des erreurs ;
- conservation de la conversation même en cas d'échec ;
- absence de double soumission du même message.

À terme, certains états peuvent être affichés :

```text
Analyse de la demande…
Recherche dans la mémoire…
Préparation du contexte…
Génération de la réponse…
```

Mais uniquement s'ils correspondent réellement au fonctionnement de l'application.

---

# 6. L'application est multi-utilisateur

L'assistant n'est pas destiné à un seul utilisateur.

Il pourra être utilisé par plusieurs membres de la famille.

Cette contrainte doit être prise en compte **dès la V1**.

Chaque membre possède :

```text
User
 ├── conversations
 ├── messages
 ├── memories
 ├── preferences
 ├── interests
 ├── procedural memory
 ├── projects personnels
 └── contexte personnel
```

Une information appartenant à un utilisateur ne doit jamais être automatiquement accessible par un autre utilisateur.

---

# 7. Isolation des données

L'isolation entre utilisateurs est une règle fondamentale.

Une recherche mémoire ne doit jamais fonctionner ainsi :

```text
chercher dans toutes les mémoires
↓
prendre les meilleurs résultats
↓
filtrer ensuite selon l'utilisateur
```

Le filtrage des permissions doit intervenir **avant ou directement pendant la recherche**.

Exemple conceptuel :

```text
SELECT memories
WHERE owner is accessible by current_user
ORDER BY vector_similarity
```

Cette règle doit s'appliquer à :

```text
memories
messages
conversations
projects
documents
tasks
signals
tool data
```

---

# 8. Espaces familiaux

L'application doit prévoir qu'une information puisse être personnelle ou partagée.

Exemple personnel :

```text
L'utilisateur préfère coder le soir.
```

Exemple partagé :

```text
La famille part en vacances du 10 au 17 août.
```

Ces deux informations ne doivent pas être stockées de la même manière.

Prévoir progressivement une notion de propriétaire :

```text
owner_type
owner_id
```

Par exemple :

```text
owner_type = USER
owner_id = user_123
```

ou :

```text
owner_type = FAMILY_SPACE
owner_id = family_456
```

À terme, d'autres propriétaires peuvent exister :

```text
PROJECT
GROUP
```

---

# 9. Modèle familial

Prévoir une structure conceptuelle proche de :

```text
User
  │
  ↓
Membership
  │
  ↓
FamilySpace
```

Exemple :

```text
FamilySpace
 ├── members
 ├── roles
 ├── shared memories
 ├── shared projects
 ├── shared tasks
 ├── shared calendar
 └── shared documents
```

La présence dans un même espace familial ne signifie pas que toutes les données sont automatiquement communes.

---

# 10. Séparer assistant personnel et contexte familial

Conceptuellement, chaque utilisateur possède son assistant personnel.

Mais cet assistant peut également accéder à certains espaces partagés.

Exemple :

```text
Assistant personnel
      │
      ├── mémoire personnelle
      ├── préférences personnelles
      ├── projets personnels
      │
      └── espaces accessibles
             │
             └── FamilySpace
```

Une question comme :

```text
Qu'est-ce que je dois faire demain ?
```

doit principalement consulter le contexte personnel.

Une question comme :

```text
Qu'est-ce qu'on avait prévu pour les vacances ?
```

peut nécessiter le contexte familial partagé.

---

# 11. Ne jamais fusionner abusivement les préférences familiales

Exemple :

```text
Utilisateur A :
Je préfère partir tôt le matin.

Utilisateur B :
Je préfère partir après 10h.
```

Il ne faut pas créer automatiquement :

```text
"La famille préfère partir tôt."
```

Les deux préférences doivent rester attachées à leurs utilisateurs respectifs.

Une mémoire familiale doit représenter une information réellement collective.

Exemple :

```text
La famille a décidé de partir samedi à 8h.
```

---

# 12. Les quatre formes principales de mémoire

Le système doit distinguer conceptuellement :

```text
Working Memory
Episodic Memory
Semantic Memory
Procedural Memory
```

Ces concepts ne correspondent pas nécessairement à quatre tables distinctes.

Ils représentent des responsabilités différentes.

---

# 13. Working Memory — mémoire de travail

La mémoire de travail est temporaire.

Elle contient les informations nécessaires à la conversation ou à la tâche actuelle.

Exemple :

```text
Utilisateur :
Je veux créer une API.

Puis :
On utilisera FastAPI.

Puis :
La base sera PostgreSQL.

Puis :
Elle devra fonctionner sur mon VPS.
```

Toutes ces informations doivent rester disponibles pendant la conversation.

Elles n'ont cependant pas nécessairement toutes vocation à devenir des mémoires persistantes.

La working memory peut contenir :

- messages récents ;
- sujet actuel ;
- projet courant ;
- résultats d'outils ;
- décisions temporaires ;
- éléments nécessaires au raisonnement en cours.

---

# 14. Episodic Memory — mémoire épisodique

La mémoire épisodique représente les événements significatifs.

Elle répond aux questions :

```text
Que s'est-il passé ?
Quand ?
Dans quel contexte ?
Sur quel projet ?
Pourquoi ?
```

Exemple :

```text
Le 21 septembre 2026,
l'utilisateur a décidé de séparer
mémoire sémantique et mémoire épisodique
dans son assistant.
```

Un épisode ne doit pas être une simple copie du message.

Il s'agit d'une représentation synthétique d'un événement pertinent.

---

# 15. Semantic Memory — mémoire sémantique

La mémoire sémantique représente ce que l'assistant pense savoir actuellement.

Exemple :

```text
L'utilisateur développe principalement en Python.

L'utilisateur préfère généralement FastAPI.

L'utilisateur travaille sur le projet Atlas.

L'utilisateur s'intéresse à Docker.
```

Une mémoire sémantique doit pouvoir :

- être modifiée ;
- être remplacée ;
- devenir obsolète ;
- avoir un niveau de confiance ;
- avoir une portée ;
- être explicite ou inférée.

---

# 16. Procedural Memory — mémoire procédurale

La mémoire procédurale décrit comment l'assistant doit travailler avec un utilisateur.

Elle doit impérativement être personnelle.

Exemple :

```text
Utilisateur A :
préfère des réponses techniques détaillées.

Utilisateur B :
préfère des réponses courtes et simples.
```

L'assistant ne doit pas apprendre un style global pour toute la famille.

Exemples de mémoire procédurale :

```text
Lorsqu'il demande du code,
l'utilisateur préfère comprendre le problème avant l'implémentation.

Lorsqu'il demande une architecture,
présenter les compromis avant de proposer une solution.

Pour une correction de texte,
conserver son style autant que possible.
```

Cette mémoire sera développée plus tard.

---

# 17. Forme de mémoire et type d'information sont deux concepts différents

Ne pas confondre :

```text
episodic
semantic
procedural
```

avec :

```text
fact
preference
interest
goal
constraint
decision
project_context
habit
skill
relationship
```

Une mémoire peut être :

```json
{
    "kind": "semantic",
    "type": "preference",
    "content": "L'utilisateur préfère PostgreSQL."
}
```

Ou :

```json
{
    "kind": "episodic",
    "type": "decision",
    "content": "L'utilisateur a choisi PostgreSQL pour Atlas."
}
```

---

# 18. Pourquoi conserver les types d'information

Le type change la manière dont la mémoire doit influencer le raisonnement.

## Preference

```text
L'utilisateur préfère PostgreSQL.
```

Cela signifie :

> Favoriser PostgreSQL lorsque cela reste adapté.

Cela ne signifie pas :

> Toujours choisir PostgreSQL.

---

## Constraint

```text
Le projet doit obligatoirement utiliser PostgreSQL.
```

Cette information doit peser beaucoup plus fortement.

---

## Fact

```text
Le projet utilise actuellement PostgreSQL.
```

Il s'agit d'un état actuel.

---

## Interest

```text
L'utilisateur s'intéresse à Docker.
```

Cette information peut être explicite ou inférée.

---

## Goal

```text
L'utilisateur souhaite apprendre Kubernetes.
```

---

## Decision

```text
PostgreSQL a été retenu pour Atlas.
```

---

# 19. Une mémoire n'est jamais automatiquement une instruction

Les mémoires doivent contextualiser la réponse.

Elles ne doivent pas remplacer le raisonnement.

Exemple :

```text
Mémoire :
L'utilisateur préfère PostgreSQL.
```

Nouvelle question :

```text
Quel stockage utiliser pour plusieurs milliards
d'événements analytiques ?
```

Le système doit comparer :

```text
besoin actuel
+
contraintes techniques
+
contexte projet
+
préférences utilisateur
+
connaissances du modèle
```

Il peut répondre :

```text
Tu utilises souvent PostgreSQL,
mais pour ce type de charge ClickHouse peut être plus approprié.
```

C'est le comportement recherché.

---

# 20. Portée — Scope

Chaque mémoire doit pouvoir avoir une portée.

Exemples :

```text
GLOBAL
USER
PROJECT
FAMILY
CONVERSATION
DOMAIN
PERSON
```

Exemple :

```text
scope = GLOBAL
L'utilisateur préfère React.
```

Mais :

```text
scope = PROJECT:company-app
Le projet doit utiliser Vue.
```

Il n'y a pas contradiction.

Le modèle de données doit rester suffisamment extensible pour permettre ces distinctions.

---

# 21. Source de la mémoire

Une mémoire doit pouvoir préciser son origine.

Exemples :

```text
explicit
inferred
observed
```

## Explicit

```text
J'aime Docker.
```

Peut devenir :

```text
interest = Docker
source = explicit
confidence élevée
```

## Inferred

```text
Comment fonctionne Docker ?
Quelle différence avec Podman ?
Comment dockeriser FastAPI ?
```

Cela peut progressivement fournir des signaux.

Mais une seule question ne doit pas immédiatement créer :

```text
"L'utilisateur aime Docker."
```

---

# 22. Signal comportemental

Prévoir la possibilité de distinguer :

```text
Memory
```

et :

```text
Signal
```

Un signal représente une indication faible.

Exemple :

```text
Utilisateur :
Comment fonctionne Docker ?
```

Peut produire :

```text
subject = Docker
type = interest
strength = faible
```

Plusieurs signaux concordants peuvent ensuite permettre une inférence.

---

# 23. Mémoire explicite et signaux

Exemple :

```text
J'aimerais vraiment apprendre Docker.
```

Peut immédiatement générer une mémoire :

```text
type = interest
source = explicit
confidence = élevée
```

Alors que :

```text
Comment fonctionne Docker ?
```

produit plutôt :

```text
Signal
interest(Docker)
```

Cette distinction doit être conservée.

---

# 24. Consolidation

À terme :

```text
Episodes
+
Signals
+
Semantic memories
       ↓
Memory Consolidator
       ↓
Updated semantic memories
```

Exemple :

```text
nombreuses discussions Docker
+
Kubernetes
+
CI/CD
+
déploiement Linux
```

peuvent conduire à :

```text
L'utilisateur développe un intérêt pour DevOps.
```

Mais :

```text
source = inferred
```

doit être conservé.

---

# 25. Architecture cible du cœur conversationnel

La première architecture cible doit ressembler à :

```text
                    User
                     │
                     ↓
              Authentication
                     │
                     ↓
             Message Processor
                     │
          ┌──────────┴──────────┐
          │                     │
          ↓                     ↓
 Working Context       Memory Retriever
                                │
                                ↓
                     Permission filtering
                                │
                                ↓
                        Memory Ranking
          │                     │
          └──────────┬──────────┘
                     ↓
               Context Builder
                     ↓
                  Ollama
                     ↓
              streamed response
                     ↓
               save response
                     ↓
              Memory Extractor
                     ↓
              Memory Manager
```

---

# 26. PHASE 0 — Audit complet de l'existant

## Objectif

Comprendre le projet actuel avant toute transformation.

Analyser :

```text
frontend
backend
database
users
authentication
conversation
messages
Ollama
streaming
prompts
errors
timeouts
tests
permissions
```

Documenter le parcours actuel :

```text
User
 ↓
Frontend
 ↓
API
 ↓
Database
 ↓
Ollama
 ↓
Response
```

Produire :

```text
CURRENT_ARCHITECTURE.md
```

Puis classer les composants importants :

```text
KEEP
REFACTOR
REMOVE
REBUILD
```

---

# 27. PHASE 1 — Garantir l'identité utilisateur

Avant la mémoire intelligente, l'application doit savoir avec certitude :

```text
Qui parle ?
```

Chaque requête doit être liée à un utilisateur authentifié.

Les conversations doivent appartenir explicitement à un utilisateur ou à un espace autorisé.

Exemple :

```text
Conversation
------------
id
owner_type
owner_id
created_by
created_at
```

Pour la V1, les conversations pourront être principalement personnelles.

---

# 28. PHASE 2 — Introduire la structure familiale minimale

Créer :

```text
User

FamilySpace

FamilyMembership
```

Exemple :

```text
FamilyMembership
----------------
user_id
family_space_id
role
```

Pour commencer, les rôles peuvent rester simples :

```text
MEMBER
ADMIN
```

Ne pas construire immédiatement un système complexe de permissions.

Mais laisser l'architecture évoluer.

---

# 29. PHASE 3 — Stabiliser le pipeline conversationnel

Pipeline initial :

```text
POST message
     ↓
authenticate user
     ↓
validate conversation access
     ↓
save user message
     ↓
build recent conversation context
     ↓
call Ollama
     ↓
stream response
     ↓
save assistant message
```

Garantir :

- isolation utilisateur ;
- persistance fiable ;
- streaming ;
- absence de timeout arbitraire ;
- gestion des erreurs ;
- annulation possible ;
- conservation correcte de l'historique.

---

# 30. PHASE 4 — Introduire Memory V1

Créer :

```text
MemoryExtractor
MemoryRepository
MemoryRetriever
ContextBuilder
```

Pipeline :

```text
USER MESSAGE
      ↓
save
      ↓
retrieve accessible memories
      ↓
build context
      ↓
Ollama
      ↓
stream answer
      ↓
save answer
      ↓
extract memories
      ↓
validate
      ↓
persist with correct owner
```

---

# 31. Modèle mémoire V1

Exemple conceptuel :

```text
Memory
------------------

id

owner_type
owner_id

created_by_user_id

kind
    semantic
    episodic
    procedural

type
    fact
    preference
    interest
    goal
    constraint
    decision
    project_context
    habit
    skill
    relationship

content

source
    explicit
    inferred
    observed

confidence
importance

scope_type
scope_id

status
    active
    superseded
    forgotten

source_message_id

created_at
updated_at
last_accessed_at

embedding
```

---

# 32. Pourquoi `owner` et `scope` sont différents

Ne pas confondre les deux.

## Owner

Répond à :

> À qui appartient cette information ?

Exemple :

```text
owner_type = USER
owner_id = user_123
```

## Scope

Répond à :

> Dans quel contexte cette information est-elle vraie ?

Exemple :

```text
scope_type = PROJECT
scope_id = atlas
```

Ainsi :

```text
owner = user_123
scope = project_atlas
```

signifie :

> Cette mémoire appartient à cet utilisateur et concerne Atlas.

---

# 33. Création d'une mémoire partagée

Une mémoire partagée ne doit pas être créée automatiquement à partir de n'importe quel message personnel.

Exemple :

```text
User A :
Je préfère partir en vacances en Bretagne.
```

Cela reste personnel.

Même si User A appartient à une famille.

En revanche :

```text
User A :
Nous avons décidé en famille de partir en Bretagne.
```

peut éventuellement devenir :

```text
owner = FAMILY_SPACE
type = decision
```

Mais le système doit rester conservateur.

Dans une première version, il peut être préférable que les mémoires familiales soient principalement explicites.

---

# 34. MemoryExtractor

Le LLM propose des informations mémorisables.

Il ne doit jamais écrire directement en DB.

Pipeline :

```text
Message
 ↓
MemoryExtractor
 ↓
structured output
 ↓
Pydantic validation
 ↓
business rules
 ↓
MemoryRepository
```

Exemple :

```json
{
    "memories": [
        {
            "kind": "semantic",
            "type": "preference",
            "content": "L'utilisateur préfère PostgreSQL.",
            "source": "explicit",
            "confidence": 0.96,
            "importance": 0.7,
            "suggested_owner": "current_user"
        }
    ]
}
```

Le backend reste responsable de l'autorisation réelle.

---

# 35. Important : le LLM ne décide pas des permissions

Même si le modèle retourne :

```text
owner = family
```

le backend doit vérifier :

- que l'utilisateur appartient bien à cette famille ;
- qu'il peut créer cette information ;
- que l'espace existe ;
- que la mémoire peut réellement y être stockée.

Le modèle ne doit jamais constituer une source d'autorisation.

---

# 36. PHASE 5 — Embeddings

Utiliser :

```text
PostgreSQL
+
pgvector
```

si compatible avec l'architecture actuelle.

Pipeline :

```text
memory content
     ↓
embedding model
     ↓
vector
     ↓
pgvector
```

Lors d'une nouvelle question :

```text
message
 ↓
embedding
 ↓
filter authorized memories
 ↓
vector similarity
 ↓
candidate memories
```

---

# 37. Retrieval multi-utilisateur sécurisé

Recherche conceptuelle :

```text
accessible owners =
    current user
    +
    family spaces authorized
    +
    projects authorized
```

Puis :

```text
retrieve memories
WHERE owner IN accessible owners
AND status = ACTIVE
```

Ensuite seulement :

```text
rank by semantic similarity
```

La permission doit faire partie de la requête.

---

# 38. PHASE 6 — Context Builder

Le Context Builder doit agréger uniquement le contexte utile.

Entrées possibles :

```text
current user
personal profile
personal memories
authorized shared memories
project context
recent conversation
working memory
current message
```

Sortie :

```text
small relevant context
```

Ne jamais injecter toutes les mémoires disponibles.

---

# 39. Ordre recommandé du contexte

Une structure possible :

```text
SYSTEM

USER PROFILE

PROCEDURAL PREFERENCES

CURRENT PROJECT / SPACE

RELEVANT PERSONAL MEMORIES

RELEVANT SHARED MEMORIES

RECENT CONVERSATION

CURRENT MESSAGE
```

Le prompt doit indiquer explicitement la provenance lorsque nécessaire.

Exemple :

```text
Personal memory:
The user prefers PostgreSQL.

Family context:
The family planned a trip for Saturday.
```

---

# 40. PHASE 7 — Déduplication

Exemple :

```text
Je préfère FastAPI.
```

Puis :

```text
J'utilise presque toujours FastAPI pour mes API.
```

Ne pas créer indéfiniment de nouveaux souvenirs.

Avant insertion :

```text
new memory
     ↓
search similar memories
     ↓
classify relationship
```

Relations possibles :

```text
NEW
SAME
UPDATE
CONTRADICTION
```

---

# 41. Gestion des contradictions

Exemple :

```text
Janvier :
Je préfère Vue.
```

Puis :

```text
Septembre :
Je préfère maintenant React.
```

Faire :

```text
Vue
status = superseded
```

Puis :

```text
React
status = active
```

Conserver l'historique.

---

# 42. Contradictions entre membres

Très important :

```text
User A prefers Vue.
User B prefers React.
```

Ce n'est PAS une contradiction.

Ces souvenirs appartiennent à deux utilisateurs différents.

La détection de contradiction doit donc tenir compte de :

```text
owner
scope
type
subject
```

---

# 43. PHASE 8 — Mémoire épisodique

Une fois la mémoire sémantique fiable, introduire les épisodes.

Exemple :

```text
Episode:
User A decided to migrate Atlas from Vue to React
on September 21.
```

Ou au niveau familial :

```text
Episode:
The family decided to travel on Saturday morning.
```

Les épisodes doivent toujours conserver leur propriétaire.

---

# 44. PHASE 9 — Signaux comportementaux

Introduire progressivement :

```text
Signal
```

Exemple :

```text
subject = Docker
type = interest
strength = 0.2
owner = USER:user_123
```

Les signaux doivent eux aussi être isolés par utilisateur.

Il ne faut jamais inférer automatiquement l'intérêt d'un membre à partir du comportement d'un autre.

---

# 45. PHASE 10 — Decay

Les intérêts implicites peuvent perdre de l'importance.

Exemple :

```text
Docker interest:
0.8 → 0.5
```

après plusieurs mois sans interaction.

Mais une mémoire explicite durable ne doit pas forcément subir le même traitement.

Prévoir progressivement :

```text
ephemeral
temporary
stable
long_term
```

---

# 46. PHASE 11 — Consolidation

La consolidation doit également fonctionner séparément par propriétaire.

Exemple :

```text
User A:
Docker + Kubernetes + CI/CD
```

peut produire :

```text
User A semble développer un intérêt DevOps.
```

Cela ne doit pas devenir une connaissance de toute la famille.

Pour générer une mémoire familiale, seules les interactions réellement partagées doivent être prises en compte.

---

# 47. PHASE 12 — Mémoire procédurale

Chaque utilisateur doit construire progressivement sa propre manière d'interagir avec l'assistant.

Exemple :

```text
User A
---------
réponses détaillées
explications techniques
architecture avant code
```

```text
User B
---------
réponses courtes
moins de jargon
résumé en premier
```

Le LLM peut être identique.

Le comportement final diffère grâce au contexte procédural.

---

# 48. PHASE 13 — Profils utilisateurs

Créer une distinction entre :

```text
UserProfile
```

et :

```text
Memory
```

Certaines données sont structurelles :

```text
display_name
locale
timezone
interface preferences
assistant preferences
```

Elles ne doivent pas nécessairement être stockées sous forme de souvenirs.

---

# 49. PHASE 14 — Entités et relations

À terme, introduire :

```text
Entity
Relation
```

Cela permettra de comprendre :

```text
Alice
  ↓ sœur de
Bob
```

ou :

```text
User A
  ↓ works_on
Atlas
  ↓ uses
PostgreSQL
```

Il n'est pas nécessaire d'utiliser une base graph dès le départ.

PostgreSQL suffit probablement longtemps.

---

# 50. PHASE 15 — Projets personnels et partagés

Un projet peut appartenir :

```text
à un utilisateur
```

ou :

```text
à un FamilySpace
```

Exemple :

```text
Personal Project:
Assistant IA

Family Project:
Organisation des vacances
```

Un projet peut regrouper :

```text
description
members
decisions
constraints
memories
documents
tasks
technologies
goals
```

---

# 51. PHASE 16 — Outils

Lorsque la mémoire est fiable, ajouter des outils.

Exemples :

```text
search_memory()
search_documents()
get_calendar()
create_task()
web_search()
read_email()
send_email()
```

Chaque outil doit respecter les permissions utilisateur.

Exemple :

```text
User A
```

ne doit pas pouvoir lire :

```text
User B private calendar
```

simplement parce qu'ils appartiennent à la même famille.

---

# 52. PHASE 17 — Outils partagés

Certaines ressources pourront être partagées :

```text
family calendar
family tasks
shared shopping list
family notes
family documents
```

L'architecture devra distinguer :

```text
private resource
```

de :

```text
shared resource
```

---

# 53. PHASE 18 — Raisonnement multi-étapes

Exemple :

```text
Prépare notre départ en vacances samedi.
```

L'assistant pourrait :

```text
1. récupérer le voyage familial ;
2. consulter le calendrier partagé ;
3. vérifier les tâches restantes ;
4. retrouver les décisions précédentes ;
5. vérifier éventuellement la météo ;
6. proposer une checklist.
```

Cela doit arriver après les fondations mémoire et permissions.

---

# 54. PHASE 19 — Proactivité

À terme :

```text
Assistant → User
```

doit devenir possible.

Exemple personnel :

```text
Tu avais prévu de reprendre Atlas aujourd'hui.
```

Exemple familial :

```text
Le départ familial est demain matin.
Il reste trois tâches non terminées.
```

Mais une notification familiale ne doit être envoyée qu'aux membres concernés.

---

# 55. Proactivité personnalisée

Les préférences de notifications doivent elles aussi être personnelles.

Exemple :

```text
User A:
notifications fréquentes
```

```text
User B:
uniquement urgences
```

Ne pas imposer une politique unique à toute la famille.

---

# 56. PHASE 20 — Voix

La voix doit rester un canal.

Architecture :

```text
Speech-to-text
      ↓
Assistant Core
      ↓
Memory / Context / Tools
      ↓
Text-to-speech
```

La logique métier ne doit pas dépendre de la voix.

---

# 57. Sécurité

Le multi-utilisateur rend la sécurité encore plus importante.

Vérifier systématiquement :

```text
current_user
resource owner
membership
permissions
```

Ne jamais accepter :

```text
user_id envoyé par le frontend
```

comme preuve d'identité.

L'identité doit provenir du mécanisme d'authentification backend.

---

# 58. Règle repository

Les repositories manipulant des données privées doivent idéalement demander explicitement un contexte d'accès.

Éviter :

```text
get_all_memories()
```

Préférer :

```text
get_accessible_memories(current_user, ...)
```

ou :

```text
get_user_memories(current_user.id, ...)
```

Les APIs dangereuses trop générales doivent être limitées.

---

# 59. Observabilité

En développement, pouvoir inspecter :

```text
authenticated user

conversation owner

accessible scopes

memories retrieved

memory owner

similarity score

importance

context generated

prompt final

LLM response

memories extracted

memory target owner
```

C'est essentiel pour déboguer les fuites de contexte.

---

# 60. Tests de sécurité indispensables

Créer notamment :

## Test A

```text
User A possède Memory A.
User B ne doit jamais la récupérer.
```

## Test B

```text
User A et User B appartiennent à Family X.

Family Memory X
doit être accessible aux deux.
```

## Test C

```text
User C n'appartient pas à Family X.

Family Memory X
ne doit pas être accessible.
```

## Test D

```text
User A possède une préférence personnelle.

Elle ne doit pas devenir automatiquement
une préférence familiale.
```

---

# 61. Tests fonctionnels Memory V1

## Fact

```text
Je m'appelle Paul.
```

Nouvelle conversation :

```text
Comment je m'appelle ?
```

Attendu :

```text
Paul.
```

---

## Preference

```text
Je préfère FastAPI.
```

Puis :

```text
Que me conseilles-tu pour une petite API Python ?
```

La préférence peut être prise en compte.

---

## Preference non absolue

```text
L'utilisateur préfère PostgreSQL.
```

Puis :

```text
Quel moteur utiliser pour une recherche full-text massive ?
```

Le système doit pouvoir proposer autre chose.

---

## Trivialité

```text
Merci.
```

Aucune mémoire durable.

---

## Signal

```text
Comment fonctionne Docker ?
```

Ne pas immédiatement créer :

```text
User loves Docker.
```

---

## Contradiction

```text
Je préfère Vue.
```

Puis :

```text
Je préfère maintenant React.
```

Vue devient historique.

React devient actuel.

---

## Scope

```text
Je préfère React globalement.

Sur Project X, je dois utiliser Vue.
```

Les deux mémoires coexistent.

---

# 62. Tests multi-utilisateur spécifiques

## Test 1

User A :

```text
Je préfère Python.
```

User B demande :

```text
Quel langage je préfère ?
```

Le système ne doit pas répondre Python à partir de la mémoire de A.

---

## Test 2

User A :

```text
Nous avons décidé en famille
de partir samedi matin.
```

Si la mémoire est réellement familiale :

User B peut retrouver cette information.

---

## Test 3

User A :

```text
Je préfère partir samedi matin.
```

Cette préférence reste personnelle.

---

## Test 4

User A et User B ont des préférences techniques différentes.

Le Context Builder doit fournir la préférence correspondant à l'utilisateur courant.

---

# 63. Performance Ollama

Le multi-utilisateur ne doit pas conduire à multiplier inutilement les appels au LLM.

Avec un modèle local, éviter une pipeline naïve :

```text
classifier
+
intent detector
+
memory extractor
+
main response
+
deduplicator
+
summary generator
```

sur chaque message.

Pour la V1 :

```text
deterministic retrieval
↓
main LLM call
↓
memory extraction
```

doit être privilégié autant que possible.

---

# 64. Mutualisation du LLM

Tous les utilisateurs peuvent utiliser le même serveur Ollama.

Il n'est pas nécessaire d'avoir :

```text
1 LLM par utilisateur
```

L'isolation ne se fait pas au niveau du modèle.

Elle se fait au niveau :

```text
database
retrieval
context
permissions
```

Le même modèle peut recevoir des contextes différents selon l'utilisateur.

---

# 65. Gestion de la concurrence

Comme plusieurs membres peuvent utiliser l'application simultanément, prévoir que plusieurs générations Ollama puissent être demandées.

Observer les capacités réelles du matériel.

Il peut être nécessaire plus tard de gérer :

```text
queue
concurrency limit
job state
```

Mais ne pas ajouter immédiatement Redis ou une infrastructure complexe sans besoin réel.

Prévoir simplement que :

```text
LLMService
```

puisse évoluer vers une gestion de file d'attente.

---

# 66. Abstraction du provider LLM

Le système ne doit pas dépendre directement d'Ollama partout.

Créer une abstraction :

```text
LLMProvider
```

Exemples de responsabilités :

```text
chat()
stream_chat()
generate_structured()
embed()
```

Implémentation actuelle :

```text
OllamaProvider
```

Cela permettrait plus tard d'introduire d'autres providers sans modifier le reste de la logique.

---

# 67. Ne pas créer de multi-agent prématurément

Pour la V1 :

```text
Assistant
   │
   ├── ConversationService
   ├── MemoryService
   ├── ContextBuilder
   ├── LLMService
   └── PermissionService
```

est suffisant.

Ne pas créer immédiatement :

```text
MemoryAgent
FamilyAgent
ProjectAgent
PlannerAgent
RouterAgent
```

Ajouter des agents spécialisés uniquement si les workflows futurs le justifient.

---

# 68. Interface V1

L'interface peut rester volontairement simple.

Priorité :

```text
login
↓
chat
↓
conversation
↓
streamed response
```

Ajouter rapidement une vue développement :

```text
Memory Inspector
```

permettant de voir :

```text
owner
kind
type
scope
source
confidence
status
content
```

---

# 69. Future interface

Plus tard :

```text
Assistant

Memory

Projects

Family

Tasks

Calendar

Documents

Automations

Settings
```

L'espace `Family` pourra présenter les ressources partagées.

Mais l'assistant conversationnel reste le point d'entrée principal.

---

# 70. Contrôle de la mémoire

Chaque utilisateur doit pouvoir à terme :

```text
voir ce que l'assistant sait sur lui

modifier une information

supprimer une mémoire

demander l'oubli

voir la provenance

voir si une information est personnelle ou partagée
```

Pour une mémoire familiale, les droits de modification pourront dépendre des permissions de l'espace.

---

# 71. Vie privée

Le système doit toujours pouvoir répondre conceptuellement à :

```text
Pourquoi sais-tu cela ?
```

Grâce à :

```text
source_message_id
```

ou éventuellement :

```text
source_episode_id
source_tool
```

Les mémoires inférées doivent être identifiables comme telles.

---

# 72. Ce qui constitue la V1

La V1 ne doit pas essayer d'implémenter tout le document.

Elle doit accomplir parfaitement :

```text
1. utilisateur authentifié ;

2. conversations isolées ;

3. messages persistés ;

4. appel Ollama robuste et sans timeout arbitraire ;

5. streaming de la réponse ;

6. MemoryExtractor ;

7. mémoire sémantique explicite ;

8. embeddings ;

9. retrieval sécurisé ;

10. ContextBuilder ;

11. personnalisation basique des réponses ;

12. déduplication simple ;

13. mise à jour d'une mémoire obsolète ;

14. structure FamilySpace minimale ;

15. possibilité future de mémoire partagée.
```

---

# 73. Ce qui peut rester minimal dans la V1 familiale

Pour éviter de complexifier inutilement :

Les premières conversations peuvent rester :

```text
PERSONAL
```

Les mémoires créées automatiquement peuvent également être :

```text
PERSONAL
```

par défaut.

Le support :

```text
FAMILY_SHARED
```

peut exister architecturalement sans disposer immédiatement de toute l'interface métier.

Autrement dit :

> Prévoir le partage maintenant, mais ne pas obligatoirement implémenter toutes ses fonctionnalités dès la première itération.

---

# 74. Définition de Done Memory V1

La V1 est considérée comme terminée lorsque :

- plusieurs utilisateurs peuvent exister ;
- leurs conversations sont isolées ;
- leurs messages sont isolés ;
- leurs mémoires sont isolées ;
- FamilySpace existe ;
- Membership existe ;
- les permissions sont vérifiées côté backend ;
- Ollama ne subit pas de timeout court ;
- la réponse peut être streamée ;
- le MemoryExtractor fonctionne ;
- les sorties sont validées ;
- des mémoires personnelles peuvent être créées ;
- les embeddings sont stockés ;
- pgvector ou équivalent permet la recherche ;
- les recherches sont filtrées avant ranking ;
- MemoryRetriever fonctionne ;
- ContextBuilder fonctionne ;
- les préférences sont contextualisées ;
- les contraintes sont distinguées des préférences ;
- `scope` est prévu ;
- `owner` est prévu ;
- les doublons simples sont gérés ;
- les contradictions simples sont gérées ;
- les scénarios multi-utilisateurs passent ;
- une vue debug permet d'inspecter les mémoires.

---

# 75. Ce qui doit rester hors V1

Ne pas retarder la V1 pour :

```text
voice

multi-agent

email

calendar

web tools

advanced family permissions

knowledge graph

complex procedural memory

behavioral interest inference

nightly consolidation

autonomous planning

proactive notifications

home automation
```

---

# 76. Roadmap globale

Ordre recommandé :

```text
PHASE 0
Audit projet actuel

PHASE 1
Identity / Auth isolation

PHASE 2
FamilySpace + Membership

PHASE 3
Conversation pipeline robuste

PHASE 4
Memory model

PHASE 5
MemoryExtractor

PHASE 6
Embeddings + vector search

PHASE 7
Secure MemoryRetriever

PHASE 8
ContextBuilder

PHASE 9
Deduplication / contradictions

PHASE 10
Episodic memory

PHASE 11
Signals

PHASE 12
Decay

PHASE 13
Memory consolidation

PHASE 14
Procedural memory

PHASE 15
Entities / relationships

PHASE 16
Personal / family projects

PHASE 17
Tools

PHASE 18
Shared tools

PHASE 19
Multi-step reasoning

PHASE 20
Proactivity

PHASE 21
Voice
```

---

# 77. Vision du système final

À terme, User A pourrait demander :

```text
Je voudrais lancer une nouvelle application
qui collecte énormément de données IoT.
Tu partirais sur quoi ?
```

L'assistant pourrait répondre :

```text
Tu travailles habituellement avec Python,
FastAPI et PostgreSQL.

FastAPI reste cohérent ici pour ton API,
mais je ne reprendrais pas automatiquement
PostgreSQL pour la partie stockage.

Le volume et la nature temporelle des données
peuvent rendre TimescaleDB ou une solution analytique
plus pertinente.

Dans ton projet précédent, PostgreSQL avait surtout
été retenu parce que les données étaient fortement
relationnelles.
```

Cette réponse combine :

```text
semantic memory
+
episodic memory
+
project context
+
preferences
+
technical reasoning
```

sans transformer la mémoire en règle absolue.

---

# 78. Exemple familial final

User B demande :

```text
On avait prévu quoi samedi ?
```

L'assistant peut retrouver :

```text
family shared memory:
départ à 8h

family task:
préparer les affaires

personal memory User B:
préfère préparer ses affaires la veille
```

Et répondre :

```text
Le départ familial est prévu samedi à 8h.

Il reste encore la préparation des affaires.
Comme tu préfères généralement préparer ça la veille,
vendredi soir serait probablement le meilleur moment.
```

Ici, l'assistant combine :

```text
shared family context
+
personal memory
```

sans exposer de données privées appartenant à un autre membre.

---

# 79. Principe final d'architecture

Toujours séparer :

```text
IDENTITY
Qui est l'utilisateur ?

OWNERSHIP
À qui appartient la donnée ?

PERMISSION
Qui peut la consulter ?

SCOPE
Dans quel contexte est-elle valable ?

MEMORY TYPE
Que représente cette information ?

CONFIDENCE
À quel point est-elle fiable ?

RELEVANCE
Est-elle utile pour la demande actuelle ?
```

Ces concepts ne doivent pas être mélangés.

---

# 80. Consignes finales pour Codex

Pour chaque phase :

1. analyser le code actuel ;
2. ne pas repartir de zéro sans justification ;
3. identifier les modifications minimales ;
4. respecter les fonctionnalités existantes ;
5. garder l'isolation multi-utilisateur ;
6. ne jamais faire confiance au frontend pour les autorisations ;
7. limiter les appels LLM inutiles ;
8. respecter les contraintes de performance Ollama ;
9. ne pas ajouter de timeout court ;
10. privilégier le streaming ;
11. écrire les tests avant ou avec les modifications critiques ;
12. garder les composants extensibles mais simples ;
13. ne pas anticiper inutilement les phases éloignées ;
14. éviter l'over-engineering ;
15. documenter les décisions importantes.

La règle générale du développement doit rester :

> Construire la solution la plus simple capable de satisfaire correctement la phase actuelle, tout en évitant de créer une impasse évidente pour les phases suivantes.

---

# 81. Objectif final

Le projet ne doit pas devenir simplement :

> un chatbot avec un historique plus long.

Il doit progressivement devenir un système capable de construire une représentation contextualisée, isolée et révisable de chaque utilisateur :

```text
qui il est
ce qu'il fait
ce qu'il préfère
ce qu'il sait
ce qu'il souhaite apprendre
ses projets
ses objectifs
ses contraintes
ses habitudes
ses relations
son historique
sa manière de travailler
```

ainsi qu'une représentation distincte des informations réellement partagées :

```text
famille
projets communs
événements communs
décisions communes
tâches communes
documents communs
```

L'assistant doit ensuite utiliser intelligemment ces connaissances sans les considérer comme des vérités absolues.

La fondation de tout le système reste donc :

> Identifier l'utilisateur, comprendre son message, retrouver uniquement les informations auxquelles il a droit, sélectionner ce qui est pertinent, produire une réponse contextualisée, puis apprendre de cette interaction sans mélanger les mémoires des différents utilisateurs.
