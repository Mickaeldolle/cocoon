# Plan de déploiement — mémoire personnelle et pgvector

État du dépôt au 8 octobre 2026. Ce document est un **runbook à exécuter sur un environnement choisi**, pas une preuve de déploiement. Il couvre le développement Windows local, le site Expo Web et l'API FastAPI sur deux projets Vercel, Supabase PostgreSQL, puis un VPS Docker. La mémoire lexicale et le chat restent utilisables sans pgvector. Les embeddings et la recherche vectorielle sont facultatifs et désactivés par défaut.

## 1. Choix d'architecture et limites

| Cible | API / Web | PostgreSQL | Modèle de conversation | Embeddings / worker mémoire |
| --- | --- | --- | --- | --- |
| Développement local | FastAPI + Expo local | Supabase de développement ou PostgreSQL local | Ollama local via FastAPI | Ollama local et `run_memory_worker` séparé ; pgvector dans PostgreSQL si activé |
| Hébergement actuel | Deux projets Vercel : API Python et export statique Expo | Supabase, pooler transactionnel pour l'API | Endpoint compatible OpenAI joignable depuis Vercel, à qualifier et à approuver pour les données envoyées | **Désactivés** tant qu'un endpoint d'embedding privé/authentifié et un worker durable ne sont pas effectivement déployés |
| VPS ultérieur | Caddy + API + workers en Compose ; Expo Web servi par Caddy ou laissé sur Vercel | Supabase via surcharge Compose, ou PostgreSQL privé dans Compose | Ollama privé sur l'hôte/VPS ou autre endpoint autorisé | Worker Compose `memory` opt-in ; pgvector Supabase ou image `pgvector/pgvector:pg16` |

La [vision](VISION.md) privilégie une mémoire personnelle, isolée et confirmée, avec un LLM local lorsque c'est possible. L'API sur Vercel ne peut pas joindre `localhost` du PC pour Ollama. Elle ne peut pas non plus exécuter la boucle permanente du worker mémoire : une Function Python est bornée dans le temps, même si elle prend en charge le streaming. Pour préserver l'objectif de confidentialité, ne pas faire croire qu'un modèle distant est local ; obtenir une décision explicite avant d'y envoyer des données familiales. [Vercel documente FastAPI et le streaming Python](https://vercel.com/docs/functions/runtimes/python) ainsi que les [limites de durée](https://vercel.com/docs/functions/limitations).

**Gate d'activation vectorielle :** le code actuel appelle `/api/embed` à chaque recherche sémantique. L'URL d'embedding n'a pas de mécanisme de jeton/header et refuse les identifiants dans l'URL. Il est donc sûr de préparer pgvector sur Supabase sans activer `MEMORY_VECTOR_ENABLED` sur Vercel ; l'activation de bout en bout attend une connectivité privée authentifiée, ou l'API et le worker hébergés auprès d'Ollama sur VPS. Le repli lexical reste le comportement de référence.

## 2. Préparation commune avant toute migration

1. Figer une révision Git et relever la révision de la base **sans publier les URL ni mots de passe** : `SELECT version_num FROM alembic_version;`. La tête attendue du dépôt est `20261008_40`, après `20261006_39`. Si un environnement a appliqué l'ancien identifiant mémoire `20261006_39` avant le rebase, arrêter cette procédure et préparer une réparation propre à cet environnement ; ne pas éditer `alembic_version` à l'aveugle.
2. Sauvegarder la base avec un outil PostgreSQL/Supabase adapté et **restaurer cette sauvegarde sur une base de test isolée**. Le backup doit contenir les exclusions d'oubli et les sources. Documenter durée et responsable de la restauration. Les scripts `backup-postgres.ps1` du dépôt ciblent le Compose local, pas Supabase.
3. Appliquer `alembic upgrade head` sur une copie PostgreSQL jetable, puis tester un retour à `20261006_39` et une remontée à `head`. Le downgrade supprime les exclusions d'oubli : il est réservé au test jetable ; en production, préférer un rollback du code compatible avec le schéma ou une migration corrective après sauvegarde.
4. Vérifier les sorties de `alembic heads`, des tests API, de Ruff, du typecheck/lint/tests Expo et du rendu Compose. La CI versionnée exécute ces contrôles et migre un PostgreSQL pgvector jetable ; elle ne prouve pas les droits et réglages du projet Supabase réel.

Pour la base **jetable** seulement, depuis `apps/api` avec `DATABASE_URL` pointant vers elle :

```powershell
uv sync --locked --extra dev
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade 20261006_39
uv run alembic upgrade head
```

La commande `upgrade` modifie le schéma et demande un rôle de migration. Le `downgrade` détruit les nouvelles tables mémoire et ne doit jamais être lancé sur les données réelles sans décision de restauration. Une fois l'essai réussi, exécuter **une seule fois** `upgrade head` sur la base cible dans une fenêtre contrôlée, sans migration automatique au démarrage d'une Function Vercel.

**Constat local du 8 octobre :** le serveur PostgreSQL 14 répond via le pilote Python, mais l'extension `vector` n'est ni installée ni disponible dans `pg_available_extensions`. La chaîne Alembic complète a été montée, descendue à welcome et remontée dans un schéma temporaire, sans changer la révision `public` de la base de développement. Les tests plein texte et concurrence mémoire passent dans des schémas locaux isolés ; les deux tests vectoriels restent à exécuter après installation de pgvector sur une base compatible. Voir [résultats et plans SQL](audit-ai-harness/11-implementation-report.md).

## 3. Supabase : accès, sécurité et pgvector

### Connexions et schéma

- Dédier un projet Supabase au développement/à la qualification ; séparer production et test. Supabase recommande le **pooler transactionnel** pour les Functions Vercel et la connexion **directe** pour migrations et dumps. Si l'opérateur n'a pas IPv6, le pooler **session** convient pour la migration. Copier les URI exactes depuis **Connect**, sans recomposer hôte/port/utilisateur. `sslmode=require` chiffre ; `verify-full` avec certificat racine Supabase vérifie aussi l'identité du serveur. [Modes de connexion et TLS](https://supabase.com/docs/guides/database/connecting-to-postgres).
- Cocoon utilise SQLAlchemy/psycopg via FastAPI, **pas Supabase Auth ni la Data API**. Sur Vercel, `engine_options` utilise `NullPool` et désactive les prepared statements pour le pooler `:6543`. Confirmer sur l'environnement réel par inscription, lecture/écriture et plusieurs requêtes simultanées ; `/health/ready` seul ne suffit pas.
- **Contrôle critique :** les tables sont dans `public`. Selon l'âge et les réglages du projet Supabase, les rôles Data API `anon`/`authenticated` peuvent avoir des droits automatiques sur ces tables alors que Cocoon ne définit pas de politiques RLS pour cette interface. Avant toute donnée réelle, désactiver la Data API si elle n'est utilisée par aucun autre produit du projet, ou retirer les grants client et vérifier l'absence d'accès sur **toutes** les tables Cocoon. Ne pas faire un `REVOKE` global sans inventorier les autres usages du projet. [Sécurisation Supabase](https://supabase.com/docs/guides/database/secure-data), [grants et RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

Lecture à lancer dans l'éditeur SQL Supabase, sur le projet identifié :

```sql
select n.nspname as schema_name, c.relname as table_name,
       has_table_privilege('anon', c.oid, 'SELECT') as anon_select,
       has_table_privilege('authenticated', c.oid, 'SELECT') as authenticated_select
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p')
order by c.relname;
```

Pour Cocoon, ces valeurs doivent être `false` pour les tables privées si la Data API reste exposée. Tester aussi insert/update/delete ou inspecter les grants complets avant qualification. L'authentification Cocoon ne fournit **pas** de politique RLS compatible avec les JWT Supabase : ne pas accorder `authenticated` en pensant que cela représente un compte Cocoon.

### Installer l'extension sans activer la recherche

1. Dans **Supabase → Database → Extensions**, rechercher **`vector`** (nom SQL de pgvector) et l'activer. Supabase l'installe généralement dans le schéma `extensions`. [Procédure officielle pgvector](https://supabase.com/docs/guides/database/extensions/pgvector).
2. Vérifier en lecture :

```sql
select e.extname, n.nspname as installed_schema, e.extversion
from pg_extension e join pg_namespace n on n.oid = e.extnamespace
where e.extname = 'vector';
```

3. Après la migration Alembic, vérifier `select current_schema(), current_setting('search_path');` avec l'URL de **migration** Supabase : `current_schema()` doit être `public` pour placer la table au bon endroit. Depuis `apps/api` avec cette URL, exécuter `uv run python -m app.commands.run_memory_worker --setup-vector`. Cette commande idempotente crée `memory_vector_index` et réutilise l'extension déjà installée dans `extensions` sans tenter de la recréer. Si l'extension manque sur PostgreSQL local, elle tente de l'installer dans `public`. Elle nécessite des droits DDL, distincts des permissions habituelles d'exécution de l'API. Vérifier `to_regclass('public.memory_vector_index')` puis les grants Data API de cette nouvelle table. Ne pas l'exécuter depuis une requête publique.
4. Garder `MEMORY_EMBEDDINGS_ENABLED=false` et `MEMORY_VECTOR_ENABLED=false` tant que l'API, le worker, Ollama et les tests de qualité/latence ne sont pas prêts ensemble. La table vectorielle vide n'affecte pas le retrieval lexical.

Après les grants, exécuter `uv run python -m app.commands.run_memory_worker --check-vector` depuis `apps/api` avec **l'URI du rôle API/worker**, pas celle du migrateur. Cette lecture ne publie ni URI ni secret ; son JSON doit indiquer `ready=true`, le schéma de l'extension et les quatre droits DML. Un code de sortie 1 signale une extension/table invisible ou un droit manquant. Garder le contrôle Data API et un essai réel d'insertion/recherche séparés : ce préflight ne les remplace pas.

L'index actuel effectue une recherche exacte sur un corpus autorisé matérialisé ; il ne crée pas HNSW/IVFFlat. Ne pas ajouter un index approximatif pour une dizaine d'utilisateurs sans `EXPLAIN` et mesures. La [documentation mémoire](MEMORY_SETUP.md) décrit le modèle Ollama proposé, les dimensions et la reprise du worker.

## 4. Développement local Windows

1. Utiliser une base de développement dédiée et une URL `DATABASE_URL` serveur seulement. Lancer `uv run alembic upgrade head` dans `apps/api`, puis FastAPI avec la configuration de développement déjà utilisée. Vérifier `/health/ready` et un parcours mémoire A/B. Ne jamais utiliser la base personnelle Supabase pour les tests qui créent/suppriment un schéma.
2. Pour les embeddings locaux, installer Ollama et `ollama pull qwen3-embedding:0.6b`, vérifier `/api/embed` depuis **la machine de l'API**, puis configurer les variables de [MEMORY_SETUP.md](MEMORY_SETUP.md) avec le modèle/dimension observés. Activer `MEMORY_EMBEDDINGS_ENABLED=true`, `MEMORY_VECTOR_ENABLED=true` seulement après `--setup-vector`, puis lancer **séparément** `uv run python -m app.commands.run_memory_worker`.
3. Vérifier qu'une proposition requiert confirmation, qu'un utilisateur B ne retrouve pas la mémoire de A, qu'une révocation/oubli retire la mémoire du contexte et de l'index, et qu'une panne Ollama replie vers le lexical. Mesurer p50/p95 de la première réponse, du retrieval et de l'indexation avec le modèle conversationnel lancé en même temps.

## 5. Hébergement actuel : Vercel + Supabase

1. Déployer l'API depuis `apps/api` (`index.py` expose `app`). Régler `APP_ENV=production`, `JWT_SECRET`, `DATABASE_URL` **Transaction pooler** avec TLS, `CORS_ORIGINS` exacts, `WEBAUTHN_ORIGIN` égal à l'origine web pour les passkeys, et le provider conversationnel compatible OpenAI autorisé. Régler `LLM_MAX_OUTPUT_TOKENS` et `ASSISTANT_PROMPT_MAX_BYTES` d'après la fenêtre effective du modèle ; leurs valeurs par défaut ne qualifient pas un petit modèle. Aucun secret dans `EXPO_PUBLIC_*`. Sur cette cible, laisser les deux flags mémoire vectorielle à `false` avant qualification. Ne pas lancer une boucle permanente de worker ni Alembic dans le build ou dans une Function.
2. Déployer Expo Web depuis `apps/mobile` comme second projet ; `vercel.json` exporte dans `dist`. Fournir au build `EXPO_PUBLIC_API_URL=https://<api>.vercel.app` sans slash final. Tester une route profonde rechargée, login, chat en streaming, écran mémoire paginé et CORS depuis la vraie origine web. L'APK utilise la même API HTTPS mais exige une qualification installée distincte.
3. Les workers `run_capture_worker`, `run_reminder_worker`, `run_memory_worker` sont des **processus durables** ; ils ne sont pas hébergés par le déploiement FastAPI Vercel. `/api/captures` et `/api/captures/stream` peuvent traiter une capture pendant une requête bornée, mais `/api/captures/queue` laisse un run en attente sans worker ; une reprise avec la même clé peut réclamer un bail expiré, seulement si le client relance effectivement le traitement. Le lecteur mobile des captures locales héritées ne fait aujourd'hui que remettre en file et consulter leur état. L'API expose maintenant `GET/POST /api/internal/jobs/captures/run` et `GET/POST /api/internal/jobs/memory/run` : chacun réclame au plus un job, exige `INTERNAL_WORKER_TOKEN` (au moins 32 caractères) et reste inactif sans ce secret. La route mémoire refuse aussi l'indexation désactivée. Ces appels bornés exigent un ordonnanceur fiable et ne remplacent pas un worker permanent si le modèle dépasse la durée d'une Function. Les rappels programmés disposent séparément du point d'entrée décrit dans [SECRET_NOTIFICATIONS.md](SECRET_NOTIFICATIONS.md). Garder `INTERNAL_WORKER_TOKEN`, `NOTIFICATION_WORKER_TOKEN` et la clé VAPID privée seulement sur l'API ; les valeurs publiques Expo seules vont au client.
4. **Planifier selon le forfait réel.** Vercel Cron appelle une route en `GET` et envoie `Authorization: Bearer <CRON_SECRET>` quand `CRON_SECRET` est défini. Régler `CRON_SECRET` et `INTERNAL_WORKER_TOKEN` à la même valeur aléatoire **dans le projet API uniquement**, puis ajouter les deux chemins au `vercel.json` de l'API avec une fréquence que le forfait permet. Si la route de notifications utilise aussi Vercel Cron dans ce même projet, `NOTIFICATION_WORKER_TOKEN` doit recevoir cette même valeur ; un ordonnanceur externe permet de garder des jetons distincts. Le forfait Hobby ne permet qu'une exécution quotidienne : elle est trop rare pour traiter rapidement une capture en file. Sur un forfait permettant une fréquence adaptée, surveiller les codes 5xx, la durée, l'âge des jobs et les baux expirés ; Vercel Cron ne relance pas automatiquement un appel échoué. Les durées maximales des Functions dépendent aussi de la configuration et du forfait. [Vercel Cron et authentification](https://vercel.com/docs/cron-jobs/manage-cron-jobs), [fréquences](https://vercel.com/docs/cron-jobs/usage-and-pricing), [durées des Functions](https://vercel.com/docs/functions/limitations).

   Exemple **à adapter au forfait**, dans `apps/api/vercel.json` si le projet API utilise ce répertoire comme racine :

   ```json
   {
     "$schema": "https://openapi.vercel.sh/vercel.json",
     "crons": [
       { "path": "/api/internal/jobs/captures/run", "schedule": "* * * * *" },
       { "path": "/api/internal/jobs/memory/run", "schedule": "* * * * *" }
     ]
   }
   ```

   Ne planifier la route mémoire qu'après pgvector, endpoint d'embedding privé, worker testé et activation des deux flags. Pour Hobby ou un modèle long, utiliser le worker Docker sur un hôte privé ou un ordonnanceur externe qui envoie un `POST` avec le même jeton ; vérifier son accès à Supabase et la confidentialité du provider. Supabase Cron avec `pg_net` peut envoyer des appels HTTP, mais `pg_net` conserve temporairement requêtes et en-têtes dans sa file : auditer les privilèges de lecture et le stockage du jeton avant d'utiliser cette voie. [Supabase pg_net](https://supabase.com/docs/guides/database/extensions/pg_net), [avis de sécurité Supabase](https://supabase.com/docs/guides/troubleshooting/database-roles-can-read-request-headers-queued-by-pg_net-ad6357).
5. Vérifier les cold starts, la taille du bundle, limites de requête, durée des réponses longues et l'erreur du provider. Un serveur distant compatible OpenAI peut servir le chat, mais change la frontière de confidentialité voulue dans `VISION.md`. Documenter le fournisseur et le jeu de données autorisé avant usage familial réel.

## 6. VPS Docker : deux modes de base

Le VPS doit avoir Docker Compose récent, une image API construite à partir de la révision figée, un `.env` hors Git, DNS/TLS et une sauvegarde restaurable. Seul Caddy publie des ports ; PostgreSQL, API brute, worker, Ollama et métriques ne sont pas exposés. L'ancien service Redis, sans usage runtime dans Cocoon, ne démarre plus ; son volume historique reste déclaré. Inventorier d'éventuelles données avant de le supprimer physiquement et ne pas employer `docker compose down --volumes` pour ce nettoyage. Renseigner `WEBAUTHN_ORIGIN` avec l'origine HTTPS du site si les passkeys sont utilisées ; renseigner la paire VAPID et un `WEB_PUSH_SUBJECT=mailto:...` réel pour Web Push. Le profil `memory` ne démarre qu'à la demande. La condition Compose `service_completed_successfully` fait attendre l'API et les workers après migration ; elle ne remplace pas une vérification de données. [Ordre de démarrage Docker Compose](https://docs.docker.com/compose/how-tos/startup-order).

### A. PostgreSQL privé dans Compose

Le `docker/compose.yml` emploie `pgvector/pgvector:pg16`. Pour un volume PostgreSQL 16 existant, faire un backup et un essai de restauration avant de changer d'image ; ne jamais changer de version majeure par simple remplacement du tag. Installer pgvector seulement après démarrage/migration, depuis un conteneur API/migration autorisé, puis activer les flags et le worker. Exemples depuis la racine :

```text
docker compose -f docker/compose.yml --env-file .env config --quiet
docker compose -f docker/compose.yml --env-file .env up -d --build
docker compose -f docker/compose.yml --env-file .env run --rm migrate python -m app.commands.run_memory_worker --setup-vector
docker compose -f docker/compose.yml --env-file .env run --rm --no-deps api python -m app.commands.run_memory_worker --check-vector
docker compose -f docker/compose.yml --env-file .env --profile memory up -d memory-worker
```

Le troisième appel utilise le conteneur de migration, doté des droits DDL, après la migration ; le dernier exige `MEMORY_EMBEDDINGS_ENABLED=true` dans `.env`. Configurer l'URL Ollama du **point de vue des conteneurs**, par exemple `http://host.docker.internal:11434` seulement si le runtime hôte écoute sur une interface joignable et protégée. Un runtime sur le même réseau Docker privé peut utiliser un nom de service ; ne pas publier Ollama sur Internet.

### B. PostgreSQL conservé sur Supabase

Ajouter `docker/compose.supabase.yml` **après** le fichier de base (Docker Compose ≥ 2.24.4 pour `!override`). Cette surcharge ne démarre pas le service PostgreSQL local, donne une sortie réseau au migrateur et conserve Caddy/API/workers. Dans `.env`, fournir deux URI Supabase avec TLS : `DATABASE_URL` pour un rôle d'exécution limité aux lectures/écritures nécessaires à l'API et aux workers, et `MIGRATION_DATABASE_URL` pour un rôle distinct capable de modifier le schéma. La surcharge refuse de démarrer si la seconde manque. Utiliser l'URI **Direct** si le VPS joint IPv6, ou le **Session pooler** si le VPS est IPv4 seulement, pour les migrations ; une API et des workers persistants peuvent aussi utiliser ces modes avec leur propre rôle. Ne pas réutiliser automatiquement l'URI Transaction pooler de Vercel. Après chaque migration ou création de `memory_vector_index`, vérifier les grants du rôle d'exécution sur les nouveaux objets ; ce rôle ne doit pas posséder `CREATE` sur le schéma. Valider lecture/écriture, reconnexion et budget de connexions.

Avant `up`, exécuter cette lecture **une fois avec chaque URI**, depuis une connexion qui utilise réellement le rôle correspondant ; l'éditeur SQL ouvert en administrateur ne vérifie pas le rôle de l'API :

```sql
select current_user, current_database(),
       has_schema_privilege(current_user, 'public', 'CREATE') as can_create_in_public;
```

Après migration, vérifier depuis l'URI d'exécution `has_table_privilege(current_user, 'public.memory_items', 'SELECT')` et de même pour `INSERT`, `UPDATE` et `DELETE` sur les tables nécessaires ; vérifier les séquences et `memory_vector_index` après son installation. Le rôle d'exécution ne doit pas créer dans `public` ; le rôle de migration doit pouvoir appliquer le schéma. Préparer les grants et, si souhaité, les privilèges par défaut du **rôle qui crée réellement les objets** avant de démarrer l'API ; ne pas supposer que deux URI différentes désignent deux rôles différents.

```text
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env config --quiet
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env build
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env run --rm migrate alembic upgrade head
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env run --rm migrate python -m app.commands.run_memory_worker --setup-vector
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env run --rm --no-deps api python -m app.commands.run_memory_worker --check-vector
```

Le service `migrate` se connecte alors à Supabase avec `MIGRATION_DATABASE_URL` et **modifie cette base** ; API et workers gardent `DATABASE_URL`. Vérifier séparément les deux cibles, les rôles et le backup restauré avant ces commandes. Après la migration et l'installation pgvector, accorder puis tester les droits du rôle d'exécution sur les nouveaux objets **avant** de démarrer l'API. Ensuite :

```text
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env up -d
docker compose -f docker/compose.yml -f docker/compose.supabase.yml --env-file .env --profile memory up -d memory-worker
```

Le second appel n'est à faire qu'après activation et qualification des embeddings. Le service `migrate` est également relancé par `up` ; l'upgrade Alembic doit rester idempotent et ne crée alors aucune nouvelle révision. Le profil local `local-postgres` ne doit pas être activé. Garder l'API et Ollama proches sur le VPS ou par lien privé réellement authentifié ; seul le stockage vectoriel reste chez Supabase.

## 7. Vérifications de sortie et retour arrière

### Données conservées après un oubli

L'action **Oublier** retire le souvenir du contexte futur, invalide son vecteur et exclut les messages sources ainsi que les réponses dérivées que la provenance permet de retrouver. Elle ne supprime pas immédiatement le texte des captures, messages, propositions, événements ou sauvegardes. La révocation du consentement mémoire bloque l'usage et invalide les index ; elle ne constitue pas non plus une purge de ces sources. L'interface annonce seulement l'arrêt de l'utilisation dans les prochains contextes.

Avant d'héberger des données personnelles réelles, arrêter et publier une politique de conservation distincte pour : (1) souvenirs et versions corrigées, (2) captures/messages/propositions et événements, (3) index et vecteurs reconstructibles, (4) journaux et métriques, (5) sauvegardes et exports. Fixer pour chaque classe une durée, un responsable, une procédure de purge, le délai maximal de disparition des sauvegardes et une réponse aux demandes d'effacement du compte. Aucune durée de purge automatique de ces sources n'est implémentée par ce lot ; ne pas promettre une suppression physique immédiate.

Essai obligatoire sur données fictives avant cette promesse : créer une mémoire A avec capture et réponse dérivée, sauvegarder la base, oublier la mémoire, puis vérifier l'absence du contexte/retrieval et des vecteurs. Restaurer ensuite la sauvegarde dans **une seconde base isolée** : si elle précède l'oubli, elle réintroduit les données et perd les exclusions stockées dans la même base. Définir et tester un registre d'effacements conservé hors de cette sauvegarde, ou un autre processus de rejeu contrôlé, avant de restaurer une telle copie en production. Vérifier également qu'une demande d'effacement complet n'expose ni ne touche les données B. Conserver une trace technique de l'essai sans texte personnel.

| Gate | Preuve attendue |
| --- | --- |
| Schéma | Une tête Alembic `20261008_40`, `alembic current` identique, extension `vector` dans le schéma relevé, `memory_vector_index` présent si option activée |
| Sécurité | Données A/B isolées au niveau API et recherche, aucun grant Data API involontaire, secrets absents du bundle Expo et des logs, HTTPS valide |
| Fonctionnement | `/health/ready`, chat et streaming réels, confirmation mémoire, pagination/correction/oubli, worker qui indexe après confirmation, repli lexical si Ollama/pgvector indisponible |
| Exploitation | Backup restauré sur une seconde base, alerte API/DB/worker, âge des jobs, latence et erreurs mesurés, test de redémarrage et de reprise sans doublon |
| Client | Web Vercel sur origine réelle et APK Android installé si inclus dans la livraison ; un export web local ne prouve pas l'APK ni la production |

Pour revenir vite au lexical, mettre les deux flags `MEMORY_EMBEDDINGS_ENABLED=false` et `MEMORY_VECTOR_ENABLED=false` sur toutes les instances API, arrêter le worker, puis redéployer/redémarrer. Les souvenirs confirmés et la recherche lexicale restent. Ne pas supprimer extension/table/index lors de ce rollback fonctionnel. Revenir à une ancienne version de code seulement si son schéma est compatible ; un `downgrade` retirant `memory_exclusions` peut réintroduire dans le contexte des éléments oubliés et nécessite une restauration planifiée. Pour Vercel, redéployer la révision précédente **après** cette vérification de compatibilité ; pour Compose, reconstruire l'image de la révision choisie en gardant le volume et le backup.
