# Mémoire personnelle — état de validation

Date : 6 octobre 2026. Périmètre : backend, migration, configuration, worker et tests. Voir [le plan](../MEMORY_PLAN.md) et [le guide d'exploitation](../MEMORY_SETUP.md).

**Complément du 8 octobre après rebase :** la migration mémoire porte maintenant `20261008_40` et suit la migration welcome `20261006_39`. `alembic heads` indique une seule tête ; le test de graphe passe. La suite API complète actuelle donne **237 réussis, 2 cas pgvector ignorés, 3 avertissements** avec les tests PostgreSQL locaux activés. La traçabilité des réponses rejette les identifiants de sources ou souvenirs d'un autre compte ; les chemins capture, rejeu et confirmation ont aussi des tests A/B. Ruff passe. La chaîne Alembic complète a été montée, descendue à welcome puis remontée sur PostgreSQL 14 local dans un schéma temporaire.

## Vérifications réalisées

- Suite API complète actuelle : **237 tests réussis, 2 ignorés**. Les cas ordinaires emploient SQLite isolé ; quatre cas utilisent des schémas temporaires PostgreSQL locaux. Les deux cas ignorés exigent pgvector, absent de ce serveur. Les avertissements de dépréciation proviennent de Starlette/httpx/anyio et d'Alembic.
- Analyse Ruff : aucune erreur sur `app`, `migrations` et `tests`.
- Migration mémoire désormais `20261008_40`, chaînée après `20261006_39_assistant_welcome` à la suite du rebase. La montée et la descente sur SQLite isolé ont conservé les sources existantes. Sur PostgreSQL 14 local, une chaîne complète a été montée à `20261008_40`, descendue à `20261006_39`, puis remontée, dans un schéma aléatoire supprimé ensuite. La base `public` est restée à welcome.
- Contrôles fonctionnels : isolation par compte et projet, absence de résultats hors sujet, souvenirs anciens, doublons normalisés, préférences compatibles, exceptions temporaires, versions historiques, provenance exacte du message utilisateur, rejet d'une proposition sans source utilisateur fiable, propositions confirmées, consentement et oubli avec propagation des dépendances. Le prompt ne duplique plus les souvenirs ; son contexte entier est borné en octets UTF-8 avec essais à 2k/4k/8k. Ce plafond est une estimation, pas un comptage exact des tokens du modèle.
- Indexation : tests avec embeddings simulés de l'idempotence, des empreintes de configuration, des leases, des retries et de l'oubli pendant l'inférence. Validation de la dimension et des valeurs numériques des vecteurs ; requête vectorielle paramétrée vérifiée à la compilation SQL.
- Continuité : décisions anciennes pertinentes, questions avec références et options provisoires de l'assistant ; aucune activation automatique comme faits durables.

Commande de suite locale, depuis `apps/api` :

```powershell
.\.venv\Scripts\python.exe -c "import os; os.environ['DATABASE_URL']='sqlite://'; import pytest; raise SystemExit(pytest.main(['-q','--tb=short']))"
```

Cette substitution ne modifie pas `.env`. Pour les tests PostgreSQL locaux, `MEMORY_TEST_LOCAL_SCHEMA=1` utilise uniquement la base locale `cocoon` via `127.0.0.1`/`localhost` et crée un schéma isolé ; `MEMORY_TEST_DATABASE_URL` exige toujours une base jetable `_test`/`_ci`. Voir [le guide](../MEMORY_SETUP.md).

## Benchmark ciblé

[Résultats JSON](memory-benchmark.json), générés le 8 octobre sur SQLite isolé. Chaque corpus personnel contient 10, 100, 500 ou 1 000 souvenirs. Cinq questions attendent un souvenir précis : trois formulations directes et deux reformulations ; quatre demandes sont sans réponse, dont `art` face à un souvenir sur le `carton`. Un second compte contient un souvenir au texte identique pour exercer l'isolation. La référence est une approximation lexicale du fonctionnement antérieur, limitée aux 100 souvenirs récents ; elle n'est comparée qu'aux trois questions directes.

| Souvenirs | Rappel direct à 5 | Rappel reformulé à 5 | Référence récente, direct | Sans réponse avec résultats | Résultats d'un autre compte |
| --- | --- | --- | --- | --- | --- |
| 10 | 3/3 | 1/2 | 3/3 | 0/4 | 0/5 |
| 100 | 3/3 | 1/2 | 3/3 | 0/4 | 0/5 |
| 500 | 3/3 | 1/2 | 0/3 | 0/4 | 0/5 |
| 1 000 | 3/3 | 1/2 | 0/3 | 0/4 | 0/5 |

Le rappel global à 5 vaut 4/5 et le MRR 0,8 sur chaque corpus. Les résultats révèlent une **limite lexicale concrète** : la reformulation sans mot commun n'est pas retrouvée. Le JSON inclut le nombre de requêtes SQL émises pendant chaque retrieval : médiane 2, maximum 3 pour chacune des quatre tailles de corpus. Les durées p50/p95 sont des mesures locales courtes, sensibles à la charge de la machine, sans réseau ni modèle réel. Ce petit jeu public ne permet pas d'établir la précision ou la performance en production. Les tests PostgreSQL locaux confirment les frontières de mots et le stemming français après conservation des accents à l'entrée FTS. Le [plan SQL](memory-postgres-plans.json) montre un parcours séquentiel à 100 et 1 000 souvenirs, avec 0,469 et 3,643 ms d'exécution sur corpus synthétique.

## Qualification restante

Les deux tests ignorés exigent pgvector : recherche vectorielle avec isolation et réservation concurrente des travaux d'indexation. L'extension `vector` n'est pas disponible sur le PostgreSQL local ; la CI dispose d'un service pgvector mais son exécution hébergée n'a pas été vérifiée ici. Le plein texte, les plans SQL et les deux courses entre révocation du consentement et écriture mémoire passent sur PostgreSQL local.

Aucun Ollama réel n'a été interrogé et aucun embedding réel n'a été produit pendant cette vérification. Il faut encore mesurer le gain hybride face au plein texte sur un corpus français représentatif, calibrer le seuil et vérifier la latence sur le matériel cible. Les options restent désactivées par défaut.

Restent également : interruption/redémarrage réel du worker, restauration de sauvegarde avec exclusions d'oubli, parcours Android et comportement réel du LLM face aux ambiguïtés et instructions présentes dans les sources. La continuité est extractive et ne suit pas automatiquement la résolution de chaque question.

Aucune migration n'a été exécutée sur la base Supabase personnelle. Aucun service distant n'a été installé ou reconfiguré, et aucun déploiement n'a été effectué. Les références de dépendance protègent les nouvelles réponses des chemins chat/stream ; les anciennes réponses et les chemins historiques dépourvus de traçabilité complète restent une limite de l'oubli des dérivations. L'historique brut n'est pas effacé.
