# Mémoire personnelle — état de validation

Date : 6 octobre 2026. Périmètre : backend, migration, configuration, worker et tests. Voir [le plan](../MEMORY_PLAN.md) et [le guide d'exploitation](../MEMORY_SETUP.md).

## Vérifications réalisées

- Suite API complète : **202 tests réussis, 2 ignorés**, exécutée avec `DATABASE_URL=sqlite://` sur le processus de test pour isoler la vérification de disponibilité de la base distante. Deux avertissements de dépréciation proviennent de Starlette/httpx/anyio.
- Analyse Ruff : aucune erreur sur `app`, `migrations` et `tests`.
- Migration `20261006_39` : montée et descente testées sur un schéma SQLite isolé, avec conservation des données existantes. Chaîne Alembic PostgreSQL compilée sans connexion ; ce contrôle ne prouve pas l'exécution des migrations sur PostgreSQL.
- Contrôles fonctionnels : isolation par compte et projet, absence de résultats hors sujet, souvenirs anciens, doublons normalisés, préférences compatibles, exceptions temporaires, versions historiques, provenance exacte du message utilisateur, propositions confirmées, consentement et oubli avec propagation des dépendances.
- Indexation : tests avec embeddings simulés de l'idempotence, des empreintes de configuration, des leases, des retries et de l'oubli pendant l'inférence. Validation de la dimension et des valeurs numériques des vecteurs ; requête vectorielle paramétrée vérifiée à la compilation SQL.
- Continuité : décisions anciennes pertinentes, questions avec références et options provisoires de l'assistant ; aucune activation automatique comme faits durables.

Commande de suite locale, depuis `apps/api` :

```powershell
.\.venv\Scripts\python.exe -c "import os; os.environ['DATABASE_URL']='sqlite://'; import pytest; raise SystemExit(pytest.main(['-q','--tb=short']))"
```

Cette substitution ne modifie pas `.env`. Les tests PostgreSQL utilisent une variable distincte et une base jetable.

## Benchmark ciblé

[Résultats JSON](memory-benchmark.json). Chaque corpus contient trois recherches attendues et trois demandes sans réponse. La référence est une approximation lexicale du fonctionnement antérieur, limitée aux 100 souvenirs récents.

| Souvenirs | Rappel à 5, nouvelle recherche | Rappel à 5, référence récente | Demandes sans réponse ayant des résultats |
| --- | --- | --- | --- |
| 10 | 100 % | 100 % | 0/3 |
| 100 | 100 % | 100 % | 0/3 |
| 500 | 100 % | 0 % | 0/3 |
| 1 000 | 100 % | 0 % | 0/3 |

Ces mesures démontrent la suppression de la perte due à la présélection dans ces scénarios synthétiques. Elles ne mesurent ni compréhension de reformulations sémantiques, ni extraction réelle, ni intelligence globale. Les durées enregistrées sont locales, sans appel réseau ni modèle réel.

## Qualification restante

Les deux tests ignorés nécessitent PostgreSQL/pgvector : plein texte et isolation vectorielle, puis réservation concurrente des travaux d'indexation. Ils sont préparés pour `MEMORY_TEST_DATABASE_URL` et pour le service pgvector de la CI, mais cette CI n'a pas été exécutée dans cette session.

Ollama n'est pas installé sur la machine inspectée. Aucun embedding réel n'a été produit. Il faut encore mesurer le gain hybride face au plein texte sur un corpus français représentatif, calibrer le seuil et vérifier la latence sur le matériel cible. Les options restent désactivées par défaut.

Restent également : interruption/redémarrage réel du worker, confirmation concurrente sur PostgreSQL, restauration de sauvegarde avec exclusions d'oubli, parcours web/mobile et comportement réel du LLM face aux ambiguïtés et instructions présentes dans les sources. La continuité est extractive et ne suit pas automatiquement la résolution de chaque question.

Aucune migration n'a été exécutée sur la base Supabase personnelle. Aucun service distant n'a été installé ou reconfiguré, et aucun déploiement n'a été effectué. Les références de dépendance protègent les nouvelles réponses des chemins chat/stream ; les anciennes réponses et les chemins historiques dépourvus de traçabilité complète restent une limite de l'oubli des dérivations. L'historique brut n'est pas effacé.
