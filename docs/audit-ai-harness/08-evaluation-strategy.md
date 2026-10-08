# 08 — Évaluation reproductible et non-régression

> **Mise à jour du worktree :** le benchmark synthétique inclut désormais paraphrases, absences et comptes A/B ; six cas PostgreSQL optionnels existent et une étape CI de migration est préparée. L'un collecte les plans SQL à 100 et 1 000 souvenirs dans un artefact CI ; un autre vérifie la sérialisation des corrections et confirmations de note avec la révocation du consentement. Ils ne remplacent pas un corpus représentatif, la vérification PostgreSQL exécutée et les mesures réelles détaillées dans [02 — audit mémoire](02-memory-audit.md).

Objectif : comparer deux versions du retrieval/harnais ou deux modèles sans exposer de données réelles. Les tests actuels couvrent déjà mémoire, isolation, providers, captures, notifications et messagerie (`apps/api/tests/test_memory.py`, `test_isolation.py`, `test_provider.py`, `test_neural.py`, `test_reminder_worker.py`, `test_secret_access.py`) dans une base SQLite isolée (`tests/conftest.py:14-40`). Les tests mobiles existants sont surtout ciblés (`apps/mobile/tests/*.cjs`). Cela ne constitue pas une qualification PostgreSQL concurrente ni Android.

## Corpus de référence

Créer des utilisateurs fictifs A/B, deux familles distinctes, trois projets, >120 souvenirs pour A, des messages anciens, corrections, suppressions et événements datés. Chaque scénario contient : entrée, identité et permissions, souvenirs attendus/interdits, réponse minimale acceptable, statut d'action, budget modèle et latence observée. Aucun texte utilisateur réel, token, adresse ou secret. Versionner corpus, seed, prompt, paramètres de génération, modèle et version d'embeddings ; exécuter sur DB éphémère. Garder un corpus de développement et un corpus de contrôle caché pour éviter de régler l'heuristique sur les seules phrases de test.

| Scénario | Attendu principal |
| --- | --- |
| Préférence déclarée 110 souvenirs plus tôt | retrouvée malgré récence ; réponse cite la préférence sans l'ériger en contrainte |
| Projet et décision ancienne | bon projet/scope, source retrouvée |
| Information inconnue | réponse admet l'absence de preuve, sans invention |
| Django ancien → FastAPI actuel | fait ancien non présenté comme actuel ; chronologie conservée |
| Correction puis oubli | ancienne version et descendants supprimés du retrieval/contexte ; sources traitées selon politique |
| Salutation simple | pas de recherche inutile si route déterministe activée |
| Synonyme/paraphrase | comparer lexical, FTS et hybride seulement si activé |
| Souvenir hors sujet / injection | non injecté ou traité comme donnée ; aucun outil non autorisé |
| A/B, famille, secret | rien de B ni du secret dans retrieval, prompt, réponse, cache, push, trace |
| LLM lent/503/JSON invalide | message utilisateur conservé, réponse/erreur sûre, retry sans doublon |
| Contexte 2k/4k/8k et 100+ messages | pas de dépassement ; décisions importantes présentes |
| Worker interrompu / provider push refusé | reprise idempotente et bon destinataire |

## Mesures séparées

1. **Retrieval :** precision@k, recall@k, MRR, proportion de souvenirs obsolètes/interdits, latence p50/p95, nombre de candidats avant/après filtre. Les permissions ont un seuil absolu : zéro résultat non autorisé.
2. **Contexte :** proportion de souvenirs attendus inclus, hors sujet injectés, tokens par section, dépassements, conservation provenance/date, séparation instruction/donnée.
3. **Réponse :** exactitude factuelle sur preuves, respect des préférences et contraintes, taux « inconnu reconnu », faux souvenirs, stabilité sur répétitions et premier token/fin. Évaluation humaine aveugle pour les nuances ; grader automatique seulement sur assertions vérifiables.
4. **Opérations :** actions non autorisées, doublons de proposition/outbox, erreurs non sûres, A/B sur API/worker/cache/mobile, reprise après interruption.
5. **Performance globale :** ouverture à froid, home→chat, premier delta et réponse complète par type de modèle/réseau, utilisation CPU/GPU/DB si accessible. Ne pas mélanger la latence retrieval avec l'inférence.

Comparer des versions avec même seed/données et mêmes paramètres. Publier effectifs, distribution et cas échoués, sans inventer de score global. Un changement ne passe pas si isolation, oubli, consentement ou idempotence régressent, même si la qualité moyenne augmente. Les expériences pgvector doivent montrer un gain sur paraphrases et vieux souvenirs, sous coût/latence acceptable, avant activation. Les tests de charge sur ~10 utilisateurs simulent des générations concurrentes et des workers, puis mesurent saturation et files ; ne déduire aucune capacité de tests unitaires.

**Baseline locale actuelle :** le fichier [memory-benchmark.json](../validation/memory-benchmark.json) contient 5 questions par corpus de 10, 100, 500 et 1 000 souvenirs : rappel exact 3/3, paraphrase 1/2, MRR 0,8, aucun résultat pour quatre questions absentes et cinq recherches inter-utilisateur. Le retrieval émet une médiane de 2 requêtes SQL, au maximum 3 dans cet essai SQLite. La paraphrase manquée constitue un cas concret à améliorer ou à comparer avec pgvector ; ces effectifs sont insuffisants pour fixer un seuil de production.

Le corpus fictif [memory-live-cases.json](../validation/memory-live-cases.json) et `python -m app.commands.evaluate_memory_context --dry-run --output ../../docs/validation/memory-context-dry-run.json` (depuis `apps/api`) préparent quatre cas à 2k, 4k et 8k. La sortie [locale](../validation/memory-context-dry-run.json) montre un cas saturé où le souvenir demandé était exclu à 2k avant de prioriser les termes précis de la question ; après correction, il figure dans les trois préparations. Le dry run mesure des octets UTF-8, **pas des tokens**. Avec un provider réellement configuré, enlever `--dry-run` pour obtenir les tokens déclarés, la latence et les réponses ; vérifier la fenêtre réellement configurée chez ce provider, puis faire une revue humaine des réponses. Ce corpus public sert au développement, pas à la qualification cachée.

## Validation par niveau

**Local/statique :** tests unitaires et API avec provider simulé. **PostgreSQL isolé :** migrations futures, contraintes, concurrence, `EXPLAIN`, RLS éventuelle. **Navigateur :** SSE et Web Push/UX web. **Android development build :** démarrage, clavier, biométrie, push et notifications sur écran verrouillé. **Live provider :** Ollama/petit modèle réel, STT, Expo/FCM. **Production :** restauration de sauvegarde, surveillance, sécurité des secrets et canary. Chaque rapport de phase indique ce qui est réellement validé.
