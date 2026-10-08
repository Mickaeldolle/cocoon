# 02 — Mémoire : revue du worktree du 8 octobre 2026

Périmètre : changements Git non commités, `docs/VISION.md`, `docs/MEMORY_PLAN.md` et contrats API/mobile. État actualisé après les corrections décrites dans [11 — rapport d'exécution](11-implementation-report.md). **Observé** signifie lu dans le code ; **testé** désigne une vérification exécutée localement ; **à qualifier** n'est pas une preuve de fonctionnement déployé.

## Verdict sur les objectifs

| Objectif | État observé | Action restante |
| --- | --- | --- |
| Assistant personnel isolé, confirmé avant mémorisation durable | La confirmation des propositions reste obligatoire ; `MemoryRepository.predicates` filtre utilisateur, propriétaire, portée, état et validité avant classement (`apps/api/app/modules/memory/repository.py:15-38`). | Ajouter les cas A/B et les invariants de provenance sur PostgreSQL réel ; vérifier les chemins worker et restauration. |
| Retrouver un vieux souvenir pertinent | La recherche s'applique au corpus autorisé **avant** `LIMIT` ; l'ancien défaut « 100 récents avant classement » est corrigé. Le chemin PostgreSQL utilise FTS avec repli lexical. | Mesurer `EXPLAIN (ANALYZE, BUFFERS)` et rappel sur corpus réaliste ; vérifier le plan des termes courants et ajuster le seuil de pertinence sur un corpus de contrôle. |
| Mémoire temporaire distincte de la mémoire durable | `memory/working.py` reconstruit des éléments provisoires à partir des échanges autorisés et garde un checkpoint. | Mesurer le coût des lectures/écritures à chaque tour ; vérifier que les choix suggérés restent provisoires et ne deviennent jamais des faits durables sans accord. |
| Provenance, temporalité et correction | Les champs `origin`, `observed_at`, `entity`, `attribute`, `value` et les corrections versionnées existent ; les propositions sans source utilisateur sont refusées et la provenance est visible dans le mobile. | Tester les propositions historiques et les données réelles anonymisées ; vérifier la restitution sur appareil. |
| Oubli et retrait de consentement | `memory/service.py:112-227` parcourt les versions, retire les embeddings et propage des exclusions aux sources/réponses traçables ; les index sont invalidés lors d'une révocation (`auth/router.py`). | Définir et tester précisément l'effacement des sources, des anciennes réponses non traçables et des sauvegardes. Dire « n'est plus utilisée dans le contexte futur » tant que l'effacement physique n'est pas assuré. |
| Modèles locaux et recherche hybride | Ollama `/api/embed`, vecteurs pgvector, worker avec lease/retry et repli lexical sont présents (`memory/embeddings.py`, `worker.py`) ; désactivés par défaut dans `core/config.py:55-64`. | Prouver la migration PostgreSQL, la dimension/modèle réels, la concurrence, la reprise et le gain de qualité avant activation. |
| Consultation/correction/oubli par l'utilisateur | API et écran mobile paginés avec `next_offset`, métadonnées de provenance et opérations de correction/oubli. | Vérifier le parcours avec 120 souvenirs et deux comptes dans l'application réelle. |

Le périmètre V1 de `docs/MEMORY_PLAN.md` est cohérent avec une mémoire **personnelle** seulement. `docs/VISION.md` décrit aussi la mémoire familiale et la proactivité comme direction ultérieure ; ces permissions ne doivent pas être inférées du schéma actuel. Le choix d'une recherche vectorielle optionnelle est proportionné, à condition de conserver la recherche lexicale et de prouver sa valeur.

## Historique Git et validation restante

La migration welcome `20261006_39` avait été réalisée dans une précédente branche feature, puis fusionnée sur `main` avant le rebase de la branche mémoire actuelle. Cette dernière utilisait encore le même identifiant de révision dans son worktree : le doublon provenait donc du rebase, pas de deux migrations welcome concurrentes. **Corrigé dans ce worktree :** la migration mémoire porte `20261008_40_personal_memory.py`, avec `down_revision = "20261006_39"`. Un test vérifie une seule tête Alembic et cet ordre. La montée complète, la descente à welcome et la remontée ont réussi sur PostgreSQL 14 local dans un schéma temporaire supprimé ensuite ; la base de développement est restée à welcome. La CI, une copie restaurée et le déploiement restent à qualifier.

## Qualité du contexte et du retrieval

1. Le doublon de souvenirs dans le prompt a été retiré ; la sélection applique un plafond global en octets et conserve les identifiants des éléments effectivement fournis. Le provider reçoit maintenant un plafond de sortie configurable (`LLM_MAX_OUTPUT_TOKENS`, 2048 par défaut). Mesurer encore les tokens réels et la qualité à 2k/4k/8k avec le modèle choisi ; le plafond d'entrée en octets ne garantit pas seul l'absence de dépassement.
2. `assistant/context.py` ajoute tâches, calendrier et projets aux demandes personnelles, tandis que `memory/working.py` reconstruit le contexte provisoire. Une salutation isolée évite maintenant ces lectures (9 requêtes SQL observées avant, 0 après pour les deux chargeurs en SQLite), sans omettre une demande qui commence par « Bonjour ». Sur SQLite isolé avec 101 messages, un appel de `working_context` exécute 6 requêtes SQL lors de la création du checkpoint, puis 5 lors d'un appel identique ; ce second appel ne réécrit pas le checkpoint. Mesurer encore la latence des tours ordinaires et la pertinence sur un corpus représentatif, sans routage LLM supplémentaire non justifié.
3. Le chemin PostgreSQL utilise FTS avec repli lexical borné par utilisateur. Un essai PostgreSQL local a révélé puis corrigé l'absence de rappel pour une requête accentuée après normalisation. Les plans à 100 et 1 000 souvenirs montrent un parcours séquentiel, malgré le GIN, avec 0,469 et 3,643 ms d'exécution SQL sur données synthétiques. Comparer lexical, FTS et hybride sur un corpus représentatif avant de réécrire la requête ; vérifier la latence hébergée et les termes courants.
4. `memory/retriever.py:33-111` fusionne lexical/vecteur et déduplique. Garder le repli lexical en cas d'échec Ollama/pgvector ; vérifier une absence de résultat sans injection de souvenir faible, les scopes de projet et les égalités de score.
5. `memory/conflicts.py` traite prudemment les préférences explicites, mais pas toutes les contradictions factuelles. Ajouter des cas d'essai datés et liés à une entité/attribut ; proposer la correction à l'utilisateur avant de remplacer. Ne pas consolider silencieusement.

## Preuves et limites

- **Testé localement :** la suite API complète donne 237 réussis et 2 cas pgvector ignorés, avec quatre tests PostgreSQL non vectoriels exécutés dans des schémas locaux isolés ; Ruff API, TypeScript mobile et les tests mobiles ciblés passent. Ces vérifications n'incluent pas l'appareil ni un Ollama vivant.
- `docs/validation/memory-benchmark.json` décrit des corpus synthétiques de 10 à 1 000 souvenirs avec cinq requêtes par taille. Rappel exact 3/3, paraphrase 1/2, MRR 0,8, zéro résultat pour quatre questions absentes et cinq requêtes inter-utilisateur ; médiane de 2 requêtes SQL par retrieval, maximum 3 dans cet essai SQLite. Ce petit jeu ne valide pas la qualité réelle ni le coût en production.
- Les tests PostgreSQL sont opt-in (`tests/test_memory_postgres.py`). Le parcours Alembic et les cas non vectoriels passent sur PostgreSQL local ; la CI pgvector et son exécution hébergée restent à confirmer. Conserver des résultats datés par environnement, taille de corpus et modèle.

## Critères de sortie mémoire V1

- Une seule tête Alembic, upgrade/downgrade et restauration validés sur base de test PostgreSQL ; aucune donnée de production manipulée pour la qualification.
- Cas A/B, consentement retiré, oubli/correction, sources exclues et projets séparés vérifiés à l'API **et** dans le worker.
- Toutes les pages de la mémoire consultables/corrigeables/oubliables sur mobile ; provenance et statut compréhensibles.
- Corpus versionné avec souvenirs anciens, paraphrases, contradictions, termes courants et questions sans réponse ; rappel, précision, latence et coût de contexte comparés avant/après.
- Tests avec le modèle local visé, puis sur appareil si l'interface change. Les résultats SQLite/synthétiques restent étiquetés comme tels.
