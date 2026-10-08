# 09 — Synthèse décisionnelle actualisée

**Verdict au 8 octobre 2026 :** les modifications de mémoire suivent `docs/VISION.md` pour une mémoire personnelle, consentie, traçable et révisable. L'architecture FastAPI/PostgreSQL/Expo peut rester monolithique. La chaîne Alembic et les tests SQL non vectoriels passent sur PostgreSQL local dans des schémas temporaires ; la CI pgvector, la qualité sur modèle réel et le parcours Android ne sont pas encore qualifiés. La migration welcome venait d'une branche déjà fusionnée dans `main` avant le rebase ; la migration mémoire suit désormais cette révision.

## Décisions immédiates

1. **Confirmer la chaîne Alembic avant de fusionner ou déployer.** La migration mémoire suit welcome avec un identifiant unique ; upgrade/downgrade/reupgrade ont réussi sur PostgreSQL local isolé. Confirmer la CI et une copie restaurée des données avant déploiement.
2. **Qualifier le contrôle utilisateur de la mémoire.** API et écran Expo paginent et affichent la provenance ; vérifier 120 souvenirs et deux comptes sur appareil/navigateur.
3. **Mesurer le contexte du modèle.** Le doublon a été retiré et un plafond en octets est appliqué. Vérifier les tokens et la réponse à 2k/4k/8k avec le modèle visé.
4. **Qualifier recherche et oubli sur PostgreSQL réel.** Le vieux défaut des 100 plus récents est corrigé ; FTS, repli lexical et propagation de l'oubli demandent des tests représentatifs, des plans SQL et une politique de sauvegarde.
5. **Poursuivre les extractions ciblées.** Les helpers conversation/neural, la traçabilité mémoire et les modules personnels mobiles sont séparés ; garder SSE, refresh et idempotence lors des prochains lots.

## Ce qui est prouvé ici

- Revue du worktree et des contrats API/mobile ; **237 tests API réussis, 2 cas pgvector ignorés** en incluant PostgreSQL local isolé. Ruff API, TypeScript, 39 tests mobiles et `git diff --check` passent.
- Le contrôle Alembic a révélé puis permis de corriger une collision locale. Migration complète et deux tests de concurrence passent sur PostgreSQL 14 local ; ces résultats ne prouvent pas Supabase, Ollama, Android ou la production.
- La recherche FTS conserve maintenant les accents avant la racinisation française. Le [plan SQL local](../validation/memory-postgres-plans.json) à 100 et 1 000 souvenirs reste un parcours séquentiel ; son coût mesuré est faible dans ce jeu synthétique, sans préjuger d'une base plus grande.
- Le benchmark SQLite synthétique donne rappel exact 3/3, paraphrase 1/2 et aucun résultat inter-utilisateur sur cinq requêtes ; ce corpus réduit ne qualifie pas la production. Les invariants de bout en bout restent à tester.

## Lecture de la vision

`docs/VISION.md` place la boucle conversationnelle et la mémoire personnelle fiable avant l'autonomie et le partage familial. Le worktree respecte cette direction en laissant embeddings et pgvector désactivés par défaut ; leur activation demande un gain mesuré. La mémoire familiale, les habitudes inférées et la consolidation autonome demeurent des étapes séparées avec consentement et autorisation dédiés. La simplification du code doit renforcer cette séparation, sans multiplier les abstractions ni les services.

Actions détaillées : [audit mémoire](02-memory-audit.md), [roadmap](07-roadmap.md), [qualité transversale](10-codebase-quality-actions.md), [rapport d'exécution](11-implementation-report.md) et [plan de déploiement](../deployment-memory.md).
