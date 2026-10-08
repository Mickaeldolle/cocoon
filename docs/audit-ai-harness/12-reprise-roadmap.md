# 12 — Reprise de la roadmap mémoire et qualité

Point d'arrêt du **8 octobre 2026**. Ce document permet de reprendre [la roadmap](07-roadmap.md) après la pause demandée par l'utilisateur. Il ne remplace ni [la vision](../VISION.md), ni le [rapport d'exécution](11-implementation-report.md), ni le [runbook de déploiement](../deployment-memory.md). Revalider l'état du dépôt et des environnements à la reprise : les chiffres ci-dessous sont le dernier relevé local, pas une preuve de production.

## 1. État à conserver

- Le chat direct reste le parcours principal. La mémoire est **personnelle uniquement pour le moment**, issue de propositions à confirmer ; les contrôles d'accès restent côté API. Les embeddings et pgvector demeurent facultatifs, avec repli lexical. Ne pas activer `MEMORY_EMBEDDINGS_ENABLED` ni `MEMORY_VECTOR_ENABLED` par simple présence de l'extension.
- La migration mémoire `20261008_40_personal_memory.py` suit la migration welcome `20261006_39`, déjà fusionnée dans `main` avant le rebase. Ne pas modifier une migration appliquée ni corriger `alembic_version` sans inventorier chaque environnement.
- Le worktree contient un ensemble important de modifications suivies et de nouveaux fichiers non suivis. À la reprise, **inspecter `git status` et les diffs avant toute remise à zéro, fusion ou déplacement** ; ne pas présumer qu'un fichier nouveau est jetable.
- Dernier relevé : **237 tests API réussis, 2 tests pgvector ignorés** faute d'extension locale ; **39 tests mobiles réussis**, TypeScript, ESLint et Prettier. La chaîne Alembic complète a été montée, descendue à welcome et remontée dans un schéma PostgreSQL local temporaire. Des parcours Expo Web ont été vus avec des comptes et une base SQLite fictifs. Les détails et limites sont dans le [rapport](11-implementation-report.md).
- Lors du dernier essai, `ollama`, son endpoint local, `adb`, le client PostgreSQL en ligne de commande et le moteur Docker n'étaient pas disponibles. Leur présence devra être revérifiée, sans supposer que les résultats ont changé.

## 2. Première séance de reprise

1. Lire ce document, `07-roadmap.md`, `11-implementation-report.md`, `docs/deployment-memory.md` et les changements intervenus depuis la pause. Relever la branche, la révision et `git status --short`. Ne pas écraser les modifications préexistantes.
2. Rejouer les contrôles locaux **sur le worktree courant** : suite API, Ruff, tests mobiles, TypeScript, ESLint, Prettier, graphe Alembic et rendu Compose. Utiliser une base jetable pour les tests PostgreSQL ; le mode `MEMORY_TEST_LOCAL_SCHEMA=1` ne doit être employé que sur le PostgreSQL local de développement décrit dans le rapport.
3. Classer chaque preuve selon son environnement : statique, SQLite, PostgreSQL local, CI pgvector, navigateur local, Android installé, provider vivant, Vercel/Supabase et VPS Docker. Mettre à jour les chiffres et le rapport avant de conclure qu'un lot est terminé.
4. Garder les deux flags vectoriels à `false` pendant les essais de migration et d'accès. Préparer une sauvegarde **restaurée sur une cible isolée** avant toute opération sur une base contenant des données personnelles.

Contrôles de départ depuis la racine, en PowerShell. Avant `pytest`, vérifier les variables de base de données : la suite peut créer des données de test et doit cibler uniquement une base jetable ou le schéma temporaire local explicitement prévu.

```powershell
git status --short
git diff --check
cd apps/api
uv run --offline python -m pytest -q
uv run --offline ruff check .
cd ../mobile
node --test
./node_modules/.bin/tsc.cmd --noEmit
./node_modules/.bin/eslint.cmd .
./node_modules/.bin/prettier.cmd --check .
```

Si `uv` ou `node` n'est pas disponible dans le shell repris, retrouver d'abord le runtime du projet ; ne pas installer ou mettre à jour des dépendances pour interpréter un simple échec de commande. Les tests PostgreSQL se lancent séparément avec la configuration jetable décrite dans le rapport.

## 3. Actions restantes, dans l'ordre recommandé

| Priorité | Action concrète | Preuve de sortie |
| --- | --- | --- |
| **P0 — CI et migration** | Déclencher la CI du worktree sur PostgreSQL avec pgvector ; contrôler `upgrade → downgrade welcome → upgrade`, installation vectorielle idempotente et les deux tests jusque-là ignorés. Revoir les plans SQL produits. | Exécution CI verte, artefact des plans, une seule tête Alembic et aucun test vectoriel ignoré pour absence d'extension. Une copie restaurée de données fictives passe le même parcours avant toute cible réelle. |
| **P0 — Supabase de qualification** | Utiliser un projet/base **jetable distinct de la production**. Inventorier `alembic_version`, schéma, Data API, grants `anon`/`authenticated`, rôles migration/exécution, TLS et mode de connexion. Activer l'extension SQL `vector`, migrer la copie, créer l'index optionnel, puis exécuter `--check-vector` avec le rôle API/worker. | Extension et table visibles, droits DML minimaux suffisants, rôle API sans DDL, aucune lecture privée par la Data API, parcours A/B réel sur cette base. Consigner les résultats sans URI ni secret. |
| **P1 — Provider et worker** | Choisir l'emplacement réel du modèle conversationnel, du service d'embeddings et des workers. Sur Vercel, le PC local n'est pas joignable par `localhost` et une Function ne remplace pas un worker durable. Tester un endpoint d'embeddings privé et authentifié, ou héberger API/worker/Ollama ensemble sur VPS. Planifier les routes internes seulement après vérification du forfait et de la durée des jobs. | Capture et indexation confirmées après redémarrage, absence de doublon après bail expiré, âge des jobs surveillé, repli lexical observé quand embeddings indisponibles. |
| **P1 — Qualité mémoire et coût** | Exécuter le corpus de `docs/validation/memory-live-cases.json` avec le modèle réellement retenu, aux fenêtres 2k/4k/8k ; compléter avec paraphrases, contradictions, inconnus et comptes A/B. Mesurer tokens provider, réponses, rappel/précision, p50/p95 et requêtes SQL sur PostgreSQL. | Rapport reproductible et revue humaine des réponses. Activer pgvector pour les utilisateurs seulement si le gain et son coût sont démontrés face au lexical. |
| **P1 — Parcours réels** | Sur les URL Vercel/Expo Web, tester login, route profonde, chat streamé, confirmation/pagination/correction/oubli et changement rapide A→B. Sur un APK Android installé, tester session/biométrie, clavier, flux tardif et notifications avec deux comptes et deux appareils. | Captures et journal de test sans texte privé ; pas de fuite A/B, de double envoi ou de notification au mauvais compte. Les essais navigateur locaux déjà faits ne valident pas ces cibles. |
| **P1 — Oubli et exploitation** | Définir durées de conservation pour souvenirs, sources, vecteurs, logs et backups. Faire une sauvegarde de données fictives, oublier une mémoire, restaurer la sauvegarde antérieure sur une **seconde base isolée**, puis tester le rejeu contrôlé des effacements avant remise en service. Ajouter supervision, test de restauration et procédure de rollback sur l'hébergement retenu. | Procès-verbal de restauration et d'oubli A/B, politique de rétention publiée, alertes et reprise sans réintroduction silencieuse d'une mémoire oubliée. |
| **P2 — Lisibilité restante** | Après les parcours UI, extraire uniquement les états/effets cohésifs de `assistant.tsx` et `conversation-detail-screen.tsx`. Inventorier les données de la colonne Hermes et les éventuels clients des routes historiques avant tout retrait de schéma ou d'API. | Contrats SSE, auth, idempotence, refresh et conversations cachées préservés ; tests et parcours web/Android affectés réussis. Aucune extraction imposée par la seule taille d'un fichier. |

## 4. Points de décision

- **Topologie Vercel/Supabase ou VPS :** choisir qui exploite le provider et les workers avant d'activer les embeddings. Le [runbook](../deployment-memory.md) décrit les deux voies et les commandes ; ne pas inscrire de secret dans ce document ni dans `EXPO_PUBLIC_*`.
- **Confidentialité :** décider quelles données peuvent quitter l'hôte privé si un provider distant est choisi. La vision privilégie le local ; ne pas présenter un modèle distant comme local.
- **Effacement :** l'action actuelle retire l'usage futur et les vecteurs, mais ne purge pas immédiatement toutes les sources et sauvegardes. La promesse utilisateur doit rester conforme à cet effet jusqu'à la preuve de restauration et de purge.
- **Refactor :** maintenir le monolithe modulaire et les contrats actuels tant qu'une mesure ou une responsabilité claire ne justifie pas un nouveau découpage.

## 5. Où trouver le détail

- [Vision et critères Memory V1](../VISION.md)
- [Audit architectural et état du code](01-current-architecture.md), [sécurité multi-utilisateur](03-security-multiuser.md), [qualité de toute la base](10-codebase-quality-actions.md)
- [Roadmap priorisée](07-roadmap.md) et [rapport d'exécution](11-implementation-report.md)
- [Plan local, Vercel/Supabase et VPS Docker](../deployment-memory.md), [installation mémoire](../MEMORY_SETUP.md)
- [Mesures locales](../validation/MEMORY_IMPLEMENTATION.md), [benchmark lexical](../validation/memory-benchmark.json), [plans PostgreSQL](../validation/memory-postgres-plans.json)
