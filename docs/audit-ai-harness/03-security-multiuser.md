# 03 — Isolation multi-utilisateur et sécurité

> **État actualisé.** La propagation de l'oubli et le worker mémoire sont examinés dans [02 — audit mémoire](02-memory-audit.md). Les tests locaux couvrent le rejet d'une liaison capture/run inter-utilisateur et la révocation push avant envoi. Les deux courses entre révocation du consentement mémoire et écriture passent sur PostgreSQL local isolé ; CI hébergée, appareils et restauration restent ouverts.

**Conclusion limitée au code :** les chemins audités appliquent majoritairement l'identité et la portée côté API/SQL. Aucune fuite inter-utilisateur n'a été reproduite dans cet audit documentaire. Cela ne prouve ni l'isolation de tous les chemins ni la configuration PostgreSQL de production. `docs/VISION.md:247-431,1966-2016` demande une séparation stricte entre mémoire personnelle et partage explicite.

## Contrôles observés

| Surface | Barrière observée | À tester |
| --- | --- | --- |
| Compte/session/appareil | JWT décodé, `sid` et session non révoquée rattachés à l'utilisateur (`auth/dependencies.py:30-65`) ; `enable_assistant` côté serveur (`:74-81`, `assistant/router.py:129-135`) | expiration/rotation en parallèle, retrait d'accès pendant un stream |
| Mémoire et prompt | `MemoryRepository.active_for_user` filtre `user_id`, owner, scope, état et validité en SQL ; `record_memory_usage` revérifie propriétaire des souvenirs et des messages avant d'enregistrer les dépendances. | A/B avec 100+ souvenirs, correction/suppression concurrente et coût SQL du filtrage |
| Chat et outils | Fil unique indexé par `user_id` (`assistant/models.py:36-48`) ; outils reçoivent un `user_id` serveur (`assistant/context.py:77-117`, `assistant/tools.py:77-213`) | appels internes avec ID forgé, worker, erreurs de rejeu |
| Conversations et famille | Membership vérifié (`conversations/service.py:10-25`, `family_spaces/router.py`) ; domaine secret séparé avec session renforcée (`auth/dependencies.py:83-113`, `secret/router.py:189-207`) | IDOR lecture/écriture/invitations, caches et temps réel |
| Capture/worker/confirmation | Run et capture créés depuis `current_user.id` ; le worker refuse `run.user_id != capture.user_id`. La confirmation revérifie proposition, capture et run source ; le rejeu de capture et l'annulation des propositions sœurs filtrent également le propriétaire. | Contrainte relationnelle éventuelle et essai PostgreSQL/concurrence. |
| Push | Appareils et abonnements filtrés par `item.user_id` (`run_reminder_worker.py:278-298`) ; consentement et révocation (`auth/router.py:313-321`, `:493-517`) | réattribution de token, compte changé, cible d'une notification test |
| Cache mobile | clé d'historique avec ID utilisateur, purge au changement de compte (`app/_layout.tsx`) ; état local de l'assistant recréé par compte et callbacks tardifs filtrés par propriétaire | Essai Expo Web A→déconnexion→B passé avec un message A absent de B ; transition rapide pendant un flux et Android installé à qualifier |
| Journaux | filtrage spécifique des routes secrètes dans `audit/service.py:109-142`, tests `test_audit.py:107-170` | revue des exceptions, captures d'événements et logs provider |

**[Code]** Le LLM ne choisit pas le propriétaire des outils : `tool_registry.execute` reçoit `user_id` depuis le serveur (`assistant/context.py:86-116`). Il ne peut pas confirmer directement une proposition ; l'API le fait avec `user_id` authentifié et version (`assistant/router.py:1001-1030`, `assistant/proposals.py`). Les souvenirs ne deviennent jamais des règles d'autorisation.

## Risques à traiter

1. **P1, intégrité en profondeur** — le worker refuse une paire run/capture de propriétaires différents, y compris en rejeu ; la confirmation refuse aussi une proposition reliée à une capture ou à un run d'un autre compte avant toute écriture de ressource. Le rejeu ne retourne que les propositions du propriétaire du run et la confirmation n'annule que ses propositions sœurs. Des tests injectent ces incohérences. Les FK restent simples. Évaluer une contrainte relationnelle composite lors d'une future migration après inventaire des données ; le contrôle applicatif est la barrière actuelle.
2. **P1, confidentialité** — le worktree propage maintenant l'oubli aux versions, vecteurs et réponses traçables (`memory/service.py:112-227`), mais la capture et certains contenus historiques/sauvegardes peuvent persister. Les exclusions étant dans la même base, restaurer une sauvegarde antérieure à l'oubli réintroduit le souvenir ; un rejeu des effacements depuis un registre indépendant ou une procédure équivalente doit précéder la remise en service. Une politique de conservation/suppression complète reste à définir. Définir l'oubli « du contexte » et l'effacement des sources, avec sauvegardes et délai de purge. Test : supprimer A puis vérifier mémoire, capture, événements, exports et restauration isolée.
3. **P1, prompt injection depuis données stockées** — `assistant/kernel.py:36-68` injecte des résumés non fiables comme texte utilisateur JSON. La séparation structurelle aide, mais aucune garantie ne transforme le texte mémorisé en donnée inerte. Tester une mémoire fictive qui demande de révéler B ou d'ignorer les règles ; borner la sortie des outils et filtrer avant le modèle. Complexité faible à moyenne ; acceptation : aucun accès B, aucune mutation sans confirmation.
4. **P2, défense SQL** — aucune policy RLS n'a été trouvée dans les migrations. Les filtres applicatifs sont la barrière active. Évaluer RLS après cartographie des rôles et des chemins workers ; ne pas activer globalement sans plan de tests. Complexité élevée à cause du pool, des migrations et des tâches hors HTTP.

## RLS, si le risque résiduel le justifie

PostgreSQL applique une politique par ligne aux commandes ordinaires, mais le propriétaire de table et les rôles privilégiés peuvent la contourner ; `FORCE ROW LEVEL SECURITY` change le cas du propriétaire. Voir la [documentation PostgreSQL](https://www.postgresql.org/docs/current/ddl-rowsecurity.html). Pour Cocoon : rôle applicatif non propriétaire et sans `BYPASSRLS`, rôle migration séparé, variable de contexte transactionnelle `SET LOCAL app.user_id` après authentification, policies `USING` et `WITH CHECK` sur les tables strictement personnelles, reset automatique à fin de transaction, workers définissant l'identité avant chaque unité de travail. Tester pooling transactionnel (`core/database.py:19-39`), tâches sans utilisateur, opérations admin et sauvegardes. RLS complète les contrôles applicatifs ; la gestion des données familiales demande des policies de membership explicites. Ne pas confondre `scope_type` déclaré et permission accordée.

## Matrice de non-régression A/B (données fictives)

| Cas | Action A sur donnée B | Attendu |
| --- | --- | --- |
| 1 conversations | GET liste/détail B | absente/404 |
| 2 messages | modifier ou envoyer via conversation B | 404/403, aucune écriture |
| 3 souvenirs | PATCH/DELETE mémoire B | 404 et état B intact |
| 4 retrieval | demander une phrase unique de B | aucun résultat B |
| 5 prompt | capturer messages vers provider fictif | aucun identifiant/contenu B |
| 6 worker | run A avec capture B injectée en fixture | rejet et aucune proposition |
| 7 cache | écran A puis B sur même appareil | aucune donnée A visible |
| 8 push | outbox A + appareil B, token réattribué | aucun push B |
| 9 IDOR | UUID B dans toutes les routes de détail | réponse non révélatrice |
| 10 changement de compte | A→logout→B, puis retour | cache et secret purgés |
| 11 traces | provoquer 4xx/5xx avec donnée B | aucune donnée B dans réponse/log |
| 12 injection | mémoire A « lis B » | aucune requête ou sortie B |

Les tests couvrent plusieurs bases A/B (`tests/test_isolation.py`, `tests/test_memory.py`, `tests/test_memory_pipeline.py`, `tests/test_secret_access.py`, `tests/test_neural.py`, `tests/test_reminder_worker.py`) sur SQLite isolé. Deux tests de concurrence mémoire passent également sur PostgreSQL local ; la matrice complète reste à exécuter de bout en bout sur PostgreSQL hébergé et appareils. Les tests ajoutés couvrent le worker 6, la confirmation d'une proposition avec source A/B discordante, la révocation push et le rejet de références mémoire d'un autre compte dans la traçabilité.
