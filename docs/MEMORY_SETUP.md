# Mémoire personnelle — installation et exploitation

## Ce qui fonctionne sans installation supplémentaire

La recherche lexicale porte sur le corpus personnel autorisé, sans présélection des 100 derniers souvenirs. PostgreSQL ajoute son plein texte français ; SQLite reste un repli pour les tests. Le contexte contient dates, types, portées et provenance. Les candidats doivent toujours être confirmés. Les changements explicites remplacent une préférence du même sujet et de la même portée ; les ambiguïtés et exceptions coexistent, avec une consigne de clarification au modèle.

La continuité utilise des extraits de déclarations et questions de conversation avec leurs références. Ce sont des éléments provisoires, pas une synthèse générée ni des faits automatiquement activés. Les projets sont reconnus par leur nom explicite, avec le consentement `assistant.projects`. Le modèle peut recevoir plusieurs versions en contradiction : aucune garantie que sa clarification soit correcte sans évaluation réelle.

Les options proposées par l'assistant peuvent être reprises dans le contexte de travail pour une question de suivi ; elles restent étiquetées comme propositions de l'assistant. Les questions anciennes ne sont pas présumées encore ouvertes. Une question explicitement historique peut retrouver une version remplacée, avec son état et ses dates, sans la présenter comme actuelle.

Les dépendances Python nécessaires sont déjà présentes : FastAPI, SQLAlchemy, Alembic, Pydantic, httpx et psycopg. Aucun paquet Python pgvector, Redis, base graphe ou service payant supplémentaire n'est requis.

## Migration obligatoire avant de redémarrer l'API

Depuis `apps/api`, sur l'environnement destiné au déploiement :

```powershell
uv sync --locked --extra dev
uv run alembic upgrade head
```

La migration `20261008_40` suit `20261006_39_assistant_welcome` et ajoute les champs structurés facultatifs, les index d'embeddings avec leurs leases, les checkpoints de conversation, les références de dépendance des réponses et les exclusions d'oubli. Sur PostgreSQL, elle ajoute un index GIN du plein texte français. Elle n'installe pas pgvector et ne reclassifie pas les anciens souvenirs.

Ces commandes nécessitent les droits de modification du schéma. Faire une sauvegarde selon la procédure de l'environnement avant la migration. La création de l'index GIN peut prendre un verrou sur un gros corpus : prévoir une fenêtre de maintenance si nécessaire. La migration n'a pas été appliquée à la base Supabase personnelle pendant l'implémentation.

La consultation et l'oubli restent disponibles sans consentement mémoire actif. La récupération pour le modèle, la proposition automatique, la confirmation et la correction nécessitent `assistant.memory`. Le consentement doit être accordé par l'utilisateur via les réglages ou l'API existante, jamais par une migration. L'API existante est `PUT /api/auth/consents/assistant.memory`, corps `{"policy_version":1,"source":"mobile"}` ; la révocation utilise `DELETE` sur la même route.

## Recherche sémantique locale facultative

### 1. Installer le runtime d'embedding

Installer [Ollama pour Windows](https://ollama.com/download/windows) sur la machine qui exécutera l'inférence, puis télécharger le modèle :

```powershell
ollama pull qwen3-embedding:0.6b
```

Le téléchargement prend de l'espace disque et l'inférence consomme de la RAM/VRAM et du calcul. Mesurer le partage des ressources avec le modèle conversationnel et la transcription. La [fiche officielle du modèle](https://ollama.com/library/qwen3-embedding:0.6b) et la [documentation `/api/embed`](https://docs.ollama.com/api/embed) décrivent son usage.

### 2. Activer pgvector dans la base

La bibliothèque serveur pgvector doit être disponible dans PostgreSQL. Avec Supabase, utiliser l'extension disponible sur le service ; aucune installation de PostgreSQL sur le PC n'est nécessaire pour cette base distante. Sur un PostgreSQL Windows personnel, suivre les [instructions officielles pgvector](https://github.com/pgvector/pgvector#windows), qui demandent les outils C++ pour la compilation ; ne pas installer ces outils si l'extension est déjà fournie par l'hébergeur.

Après la migration, exécuter depuis `apps/api` :

```powershell
uv run python -m app.commands.run_memory_worker --setup-vector
```

Cette commande administrative idempotente active l'extension et crée `memory_vector_index`. Elle nécessite les droits de création d'extension/table ; l'utilisateur courant de l'API et du worker n'a pas besoin de conserver les droits de création d'extension. Le code prend aussi en compte une extension déjà installée dans un schéma `extensions`. La recherche est exacte et filtre le corpus autorisé avant les distances ; aucun index approximatif n'est ajouté.

Avec `DATABASE_URL` du **rôle API/worker**, vérifier ensuite sans modifier le schéma :

```powershell
uv run python -m app.commands.run_memory_worker --check-vector
```

La commande renvoie un JSON sans URI ni secret et un code de sortie non nul si `ready=false`. `ready=true` exige PostgreSQL, l'extension `vector`, l'accès au schéma de cette extension, une table `memory_vector_index` visible et les droits SELECT/INSERT/UPDATE/DELETE du rôle connecté. Cela ne prouve ni la qualité des embeddings ni les droits Data API de Supabase.

### 3. Configurer l'API et le worker

Dans les variables serveur de l'API et du worker, pour une exécution locale hors Docker :

```dotenv
MEMORY_EMBEDDINGS_ENABLED=true
MEMORY_VECTOR_ENABLED=true
MEMORY_EMBEDDING_BASE_URL=http://localhost:11434
MEMORY_EMBEDDING_MODEL=qwen3-embedding:0.6b
MEMORY_EMBEDDING_REVISION=1
MEMORY_EMBEDDING_DIMENSIONS=1024
MEMORY_EMBEDDING_TIMEOUT_SECONDS=60
MEMORY_QUERY_TIMEOUT_SECONDS=3
MEMORY_MIN_SIMILARITY=0.65
MEMORY_CONTEXT_TOKENS=1200
ASSISTANT_PROMPT_MAX_BYTES=24000
LLM_MAX_OUTPUT_TOKENS=2048
MEMORY_WORKER_INTERVAL_SECONDS=10
```

Ces variables ne doivent jamais être `EXPO_PUBLIC_*`. La configuration du modèle conversationnel ne change pas. Les valeurs doivent correspondre entre API et indexeur. Le seuil `0.65` est un point de départ configurable, pas une qualité garantie : mesurer les faux positifs et le rappel avant d'activer la recherche hybride en usage réel.

`MEMORY_CONTEXT_TOKENS` est un nom historique : le contexte mémoire est actuellement borné en **octets UTF-8**, références incluses. `ASSISTANT_PROMPT_MAX_BYTES` plafonne ensuite le système, le message courant, l'historique, les souvenirs et les données métier réunis. `LLM_MAX_OUTPUT_TOKENS` limite la génération envoyée au provider (également pour les autres usages LLM de l'API). Le plafond d'entrée reste une estimation en octets, **pas** un comptage des tokens du modèle : ajuster les deux valeurs à sa fenêtre réelle et vérifier les réponses avec le modèle visé. Les souvenirs ne sont plus dupliqués dans le prompt.

`localhost` désigne la machine qui exécute le processus. Si l'API tourne sur Vercel, `localhost:11434` ne rejoint pas le PC. Pour rester local/privé, héberger l'API et l'indexeur auprès du runtime, ou établir une liaison privée authentifiée via un reverse proxy. Ne pas exposer Ollama directement sur Internet. Le code n'ajoute pas de mécanisme de tunnel ni d'authentification au runtime ; l'URL doit être joignable par les deux processus dans leur environnement sécurisé. Les endpoints avec identifiants dans l'URL sont refusés.

Un provider conversationnel distant continuera à recevoir le contexte sélectionné : des embeddings locaux ne rendent pas à eux seuls toute la conversation locale.

### 4. Lancer l'indexeur

```powershell
uv run python -m app.commands.run_memory_worker
```

Ce processus doit rester actif, séparément de l'API et des workers de capture/rappel. Il traite les souvenirs actifs des comptes autorisés, un à la fois, et rattrape le corpus existant sans confirmation supplémentaire des index dérivés. Il n'active aucun nouveau souvenir. La pause de dix secondes ne s'applique que lorsqu'il n'y a plus de travail.

Pour un seul passage :

```powershell
uv run python -m app.commands.run_memory_worker --once
```

Les erreurs entraînent un délai croissant et cinq tentatives au maximum. Après correction de la cause :

```powershell
uv run python -m app.commands.run_memory_worker --retry-failed --once
```

Le worker ne conserve aucune transaction pendant l'appel au modèle. Il vérifie de nouveau l'état, le consentement et l'empreinte avant d'enregistrer le résultat. Les logs indiquent état, compte de résultats et durée sans texte privé.

### 5. Changement de modèle et retour arrière

Modèle, dimension, endpoint, révision, format d'entrée et mode vectoriel déterminent une empreinte de configuration. Un changement déclenche la réindexation progressive ; les vecteurs incompatibles sont ignorés. Augmenter `MEMORY_EMBEDDING_REVISION` si le contenu du même tag Ollama change. Le code ne vérifie pas automatiquement le digest du modèle distant.

Pour désactiver la recherche hybride, remettre `MEMORY_EMBEDDINGS_ENABLED=false` et `MEMORY_VECTOR_ENABLED=false`, puis redémarrer l'API et arrêter l'indexeur. La recherche lexicale continue. Une panne de runtime, un stockage vectoriel absent ou un timeout de recherche produisent le même repli sans couper la réponse conversationnelle.

Le downgrade Alembic retire les nouvelles tables et les index dérivés, dont `memory_vector_index`, mais conserve les anciennes sources. Exporter les demandes d'oubli avant un downgrade : retirer leurs exclusions ferait perdre cette protection. L'extension PostgreSQL elle-même n'est pas supprimée.

## Consultation, correction et oubli

- `GET /api/memories?limit=50&offset=0` : page de souvenirs actifs et `next_offset` éventuel.
- `GET /api/memories?scope_id=<uuid>` : souvenirs personnels d'un projet.
- `GET /api/memories?include_history=true` : versions anciennes et souvenirs expirés non oubliés.
- `GET /api/memories/<uuid>?include_history=true` : provenance d'une ancienne version.
- `PATCH /api/memories/<uuid>` : nouvelle version ; champs supplémentaires `scope_type`, `scope_id`, `entity`, `attribute`, `value`, `valid_until`. Le projet doit appartenir au compte et son consentement être actif.
- `DELETE /api/memories/<uuid>` : oubli de la chaîne de versions, suppression des embeddings et exclusion de ses sources connues et réponses dérivées du contexte futur.

L'historique brut et les captures restent stockés. L'oubli pour l'assistant n'est pas un effacement de ces données. Les backups doivent conserver les exclusions et être restaurés avec elles. Les réponses déjà transmises à un provider ou affichées ne peuvent pas être retirées rétroactivement ; un flux déjà en cours peut aussi avoir reçu l'ancien contexte. Les dérivations antérieures à la mise en place des références d'usage ne disposent pas toutes d'une traçabilité complète.

Le frontend existant reste compatible ; l'écran mémoire affiche désormais les métadonnées de provenance et pagine les souvenirs. L'oubli exclut conservativement des messages entiers du contexte, pas seulement quelques mots.

## Validation et qualification

Le [rapport de validation](validation/MEMORY_IMPLEMENTATION.md) distingue les vérifications réalisées et les qualifications restantes. Les résultats du benchmark sont conservés dans [memory-benchmark.json](validation/memory-benchmark.json).

```powershell
uv run python -m app.commands.benchmark_memory --output ../../docs/validation/memory-benchmark.json
uv run pytest -q
uv run ruff check app migrations tests
```

Le benchmark utilise sa propre base SQLite en mémoire et ne consulte pas la base configurée. Il mesure trois questions exactes, deux paraphrases et quatre questions sans réponse pour chaque taille de corpus, en comparant les questions exactes avec la présélection historique des 100 derniers éléments. C'est un test de non-régression ciblé, pas un score global d'intelligence, d'extraction ou d'utilité utilisateur.

Les tests PostgreSQL/pgvector acceptent `MEMORY_TEST_DATABASE_URL` vers une base **jetable** dont le nom se termine par `_test` ou `_ci`. Ils créent puis suppriment un schéma isolé. Sur le seul PostgreSQL local `cocoon` accessible par `127.0.0.1` ou `localhost`, on peut exécuter les cas SQL sans base supplémentaire depuis `apps/api` :

```powershell
$env:MEMORY_TEST_LOCAL_SCHEMA = '1'
uv run python -m pytest -q tests/test_memory_postgres.py
Remove-Item Env:MEMORY_TEST_LOCAL_SCHEMA
```

Cette option refuse une URL distante, limite le `search_path` au schéma aléatoire de test et ne modifie pas les tables `public`. Les cas vectoriels sont ignorés si l'extension `vector` est absente ; les tests ne l'installent pas implicitement. Ne jamais fournir l'URL de la base Supabase personnelle à ces tests. La CI fournit un service PostgreSQL avec pgvector et applique les migrations avant les tests.

Restent à mesurer sur le matériel et l'environnement cibles : embeddings réels en français, rappel sémantique, seuil de similarité, latence à chaud/froid, concurrence PostgreSQL, reprises après interruption de processus, respect des sources par le LLM et utilité en plusieurs sessions. Garder les options désactivées tant que cette qualification n'est pas faite.
