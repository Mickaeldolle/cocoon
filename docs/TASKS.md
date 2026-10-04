# Roadmap exécutable — Cocoon assistant personnel

Révision : 24 septembre 2026. Vision produit : [VISION.md](VISION.md). Référence produit : [PLAN.md](PLAN.md). État du code et preuves : [audit](docs/PROJECT_AUDIT.md) et [audit d'efficacité](docs/ASSISTANT_EFFECTIVENESS_AUDIT.md). Essai gratuit : [déploiement Vercel/Supabase/ZeroGPU](docs/deployment-free.md) et [APK Android](docs/android-apk.md). Autres options : [deployment-options.md](docs/deployment-options.md). Historique des anciennes cases conservé dans `docs/archive/2026-09-19/TASKS.md`.

Légende : `[x]` résultat livré avec preuve ; `[~]` base partielle ; `[ ]` résultat non livré. Les lots ci-dessous sont à réaliser même si certaines fonctions existent déjà. Ne pas cocher un lot sur la seule présence d’un fichier ou d’un test simulé.

## État de départ

- [x] Recadrage documentaire : objectif, fonctionnalités, architecture, capture, mémoire, écarts et roadmap consolidés le 19 septembre 2026.
- [x] Mesure API initiale du 19/09 : 42 tests réussis, 2 avertissements de dépréciation ; fixture principale SQLite. La suite a ensuite grandi ; voir la mesure datée du 24/09 ci-dessous.
- [~] Socle Expo/FastAPI, authentification, données personnelles, propositions, runtime LLM local, STT et worker disponibles partiellement.
- [~] Porte de sortie bêta du PLAN : qualification locale avancée, preuves PostgreSQL/appareils/déploiement réel encore manquantes.
- [~] Contrôles rejoués le 24/09/2026 : 120 tests API réussis (2 avertissements), Ruff et typecheck mobile réussis ; lint mobile en échec (2 erreurs, 3 avertissements), zéro commit Git. Le corpus de 60 cas n'a pas encore de score de bout en bout.

## Mode d’exécution pour un agent IA

1. Lire PLAN, l’audit et le contrat du domaine ; choisir le premier lot non terminé dont les dépendances sont satisfaites.
2. Relire le code actuel et les instructions locales ; ne pas utiliser les archives comme une roadmap active.
3. Pour chaque lot : préciser sous-tâches, contrats et migrations, implémenter une tranche de bout en bout, puis valider erreurs et isolation.
4. Réutiliser les modules existants ; ne pas dupliquer routes, moteurs de propositions, mémoire ou scheduler. Les nouveaux chemins mentionnés ci-dessous sont des emplacements cibles, pas des fichiers déjà présents.
5. Toute migration est additive au départ. Fournir vérification des données, stratégie de retour arrière et test PostgreSQL. Ne pas migrer une base personnelle pour simplement lancer les tests.
6. Exécuter contrôles ciblés puis suite pertinente ; enregistrer résultats datés, limites et configuration non secrète dans `docs/validation/Bxx.md`.
7. Cocher seulement avec critères de sortie remplis ; indiquer précisément les parties non vérifiées. Mettre à jour l’audit si le comportement réel change.
8. Ne pas déployer ni exposer de service à Internet au seul motif qu’un plan a été approuvé : ce recadrage autorise la documentation, pas un déploiement implicite.

Les lots sont des unités de résultat, pas une promesse de calendrier. Réestimer après B00 et B04 selon matériel et qualité du modèle. Chemin critique : B00 → B01 → B02 → B03 → B04 → B05 → B06 → B07 → B08. Certaines préparations peuvent être faites plus tôt, sans omettre les dépendances.

## B00 — Référence reproductible et cible d’hébergement

- [~] Résultat : inventaire local et contrôles reproductibles documentés ; gestion de versions, PostgreSQL de test et capacité d’inférence restent à finaliser.

Dépendances : aucune. Entrées : `README.md`, `pyproject.toml`, lockfiles, `package.json`, `docker/compose.yml`, `eas.json`, audit.

Travail : vérifier/restaurer le dépôt Git (présent mais sans commit dans cette copie), vérifier les fichiers ignorés et les secrets sans les imprimer ; inventorier migrations et versions ; établir le runtime Python/Node reproductible. Pour la cible d'essai gratuite, choisir un modèle instruction exécutable sur Space Gradio ZeroGPU, mesurer quota/queue/latence et tester Vercel/Supabase avec données fictives ; vLLM n'est pas requis. Garder Ollama local comme référence de comparaison si disponible. Identifier URLs API/web, région Supabase, distribution APK Android et fonctionnalités suspendues en l'absence de workers ; qualifier séparément WebSocket FastAPI sur Vercel et diffusion inter-instances. Transformer le corpus fictif de 60 scénarios en évaluation exécutable avec état initial, effets attendus/interdits, preuves et score ; figer modèle, matériel et jeu tenu à l'écart. Appliquer le protocole de `docs/ASSISTANT_EFFECTIVENESS_AUDIT.md`. Mesurer coût/latence/qualité séparément ; cet essai cloud ne valide pas la confidentialité ni la disponibilité de la bêta complète.

Sortie : installation propre et tests rejouables, versions/matériel consignés, cible d’hébergement et limites documentées, première mesure de mémoire/utilité/ressenti avec ses limites. Aucune affirmation d’accès réel au runtime LLM ou au STT sans essai. Si infrastructure non choisie, garder le déploiement ouvert mais poursuivre les lots locaux.

## B01 — Isolation des comptes, consentements et périmètre bêta

- [~] Résultat : filtrage assistant par utilisateur centralisé et testé localement ; PostgreSQL concurrent, consentements et matrice complète restent à finaliser.

Dépendances : B00. Entrées : `modules/auth`, `modules/personal`, `modules/assistant`, `modules/neural`, session-store et client API mobile. Cibles : service de politiques/consentements, migrations et réglages.

Travail : définir les droits par source ; ajouter consentements et leur version ; revérifier le propriétaire sur chaque objet, run et outil. Préparer RLS sur tables personnelles avec contexte transactionnel et rôle non privilégié. Purger les caches au changement de compte, inclure le compte dans les clés. Fermer fonctions secrètes/non validées côté serveur ET mobile pour le profil bêta. Préparer invitations et révocation des appareils.

Sortie : tests A/B/A sur PostgreSQL et client, accès direct par UUID refusé, réutilisation d’une connexion du pool sans fuite, révocation effective et aucune exemption superadmin implicite. Les fonctionnalités familiales restent préservées mais hors contexte assistant.

## B02 — Propositions et exécuteur métier uniques

- [~] Résultat : les propositions conversationnelles et de capture sont confirmées par owner, expirables et journalisées ; les statuts d’échec métier sont maintenant communs, mais la consolidation des modèles et la qualification PostgreSQL concurrente restent à finaliser.

Dépendances : B01. Entrées : `neural/models.py`, `neural/router.py`, `assistant/models.py`, `assistant/schemas.py`, `assistant/router.py`, modèles personnels. Cibles : services `proposals` / `executor`, migrations.

Travail : consolider sur `assistant_proposals`, ajouter référence de capture/run nullable pour transition, schéma versionné, actions, expiration, groupes alternatifs, versions attendues et journal d’exécution. Extraire les services métier hors routeurs. Implémenter créations/modifications/annulations nécessaires en bêta, lots SQL atomiques, validation d’agenda et droits au clic. Migrer les anciennes propositions avec mapping stable ; garder endpoints de compatibilité jusqu’à migration mobile.

Sortie : même proposition rejouée → même résultat ; deux confirmations concurrentes → un effet ; deux alternatives → un seul choix ; rollback intégral d’un lot invalide ; conflit de version → 409 sans effet. Vérifier sur PostgreSQL réel, y compris l’ordre des verrous et le nombre d’objets par compte. Aucune mémoire extraite automatiquement activée par un chemin parallèle.

## B03 — Capture et runs durables, accueil unique

- [~] Résultat : chaque capture crée un run durable, expose `run_id`, événements incrémentaux et annulation autorisée ; l’accueil utilise maintenant le flux SSE puis bascule vers la file worker en cas de coupure, tandis que la qualification réseau/PostgreSQL et la reprise après redémarrage de l’application restent à finaliser.

Dépendances : B02. Contrat : [CAPTURE_MODULE_PLAN.md](CAPTURE_MODULE_PLAN.md). Entrées : routes neural/assistant, `app/home.tsx`, `app/assistant.tsx`, `src/services/api.ts`.

Travail : ajouter run, job et événements ; persister capture/run/job ensemble avant accusé ; clé d’envoi et hash ; worker avec bail et tentatives bornées. Fournir lecture de run, flux SSE récupérable et annulation. Unifier les anciens endpoints derrière les mêmes services avec compatibilité de contrat. Afficher l’interaction sous le champ, déplacer l’historique en accès secondaire, distinguer suggestion de réponse et confirmation métier. Ne pas fabriquer un avancement avant exécution réelle.

Sortie : coupure réseau, redémarrage worker, réouverture mobile et rejeu d’envoi récupèrent la même capture ; erreur DB initiale ne prétend pas avoir conservé le texte ; aucun doublon ; identifiants SSE d’un autre compte refusés. À ce stade utiliser un runtime de test et l’adaptateur local explicitement configuré.

## B04 — Runtime LLM local et outils personnels contrôlés

- [~] Résultat : le provider OpenAI-compatible local est isolé côté API, le contrat mobile est local-only et la conversation expose un SSE `started/delta/complete/error` avec idempotence, choix de continuation et propositions de mémoire soumises à confirmation ; la qualification d’appareil et les outils réels restent à valider.

Dépendances : B03 et politiques B01. Entrées : `assistant/service.py`, `assistant/kernel.py`, `core/config.py`, données personnelles et exécuteur B02. Cibles : adaptateur LLM local, registre d’outils interne et services métier contrôlés.

Travail : stabiliser le provider Ollama/OpenAI-compatible côté API ; définir un catalogue interne d’outils ; vérifier l’utilisateur et les permissions avant chaque lecture ; exposer des propositions typées, jamais une confirmation implicite ; définir budgets, concurrence, timeout de connexion, interruption et erreurs ; conserver les credentials uniquement côté serveur ; limiter les outils aux services Cocoon versionnés.

Sortie : test réel A/B/A, reprise après redémarrage et tentative d’accès croisé ; configuration incomplète échoue fermée ; tâche/agenda lus puis proposition confirmée dans le mobile avec objet vérifié. Aucune mutation directe depuis le LLM. Mesurer la qualité du modèle local pour les sorties structurées ; si elle est insuffisante, renforcer les règles déterministes et les validations plutôt que déléguer les permissions au modèle.

## B05 — Mémoire personnelle exploitable et oubli

- [~] Résultat : mémoire structurée, retrieval filtré, correction et oubli logique sont livrés ; corpus long, provenance détaillée et qualification PostgreSQL restent à finaliser.

Dépendances : B04. Entrées : `memory_items`, `assistant/kernel.py`, historique, outils mémoire. Cibles : MemoryService, ContextService, recherche SQL/plein texte, réglages de gestion.

Travail : séparer brut/historique, résumé de session et mémoire active ; confirmation et provenance ; correction versionnée ; validité et contradictions. Supprimer le plafond de présélection des 100 souvenirs récents qui écarte des sources pertinentes ; utiliser une recherche SQL filtrée et bornée, puis un ranking mesuré sur 10/100/500 souvenirs. Prioriser SQL pour dates/agenda/tâches. Citer les sources dans les réponses et continuer à remplir le contexte quand un candidat dépasse le budget. Gérer suppression/révocation jusque dans résumés, caches et contextes actifs. Proposer une validation des anciennes mémoires automatiquement extraites, sans les réimporter silencieusement.

Sortie : préférence retrouvée après plusieurs sessions, nouvelle version remplace l’ancienne, oubli sans résurrection, recherche hors compte refusée, absence de résultat honnête. Jeux fictifs avec préférences contradictoires et contexte long ; recall@5 et limite de tokens mesurés. Aucun embedding nécessaire pour valider ce lot.

## B06 — Capture vocale réelle

- [~] Résultat : maintien du micro → transcription corrigible → même pipeline est livré côté contrat/mobile ; STT et appareils réels restent à qualifier.

Dépendances : B03 ; intégration complète vérifiée après B04/B05. Entrées : `assistant/voice.py`, route transcription, `expo-audio`, écran accueil.

Travail : brancher appui/relâchement et annulation, permission et interruptions, limite 60 s/8 Mio, nettoyer cache/temporaire. Déployer STT en environnement de test privé basé sur faster-whisper avec contrat HTTP compatible ; normaliser les formats réels. Vérifier tailles avant lecture complète et borne serveur. Conserver provenance voix sans audio permanent. Revue du texte avant envoi ; alternative accessible à l’appui continu.

Sortie : appareils iOS/Android, microphone refusé, appel entrant, arrière-plan, audio vide et panne STT ; noms/dates/nombres français corrigeables ; aucun fichier résiduel après nettoyage. Mesurer STT et concurrence avec Ollama sur le matériel cible, sans prétendre que la dépendance Expo suffit.

## B07 — Rappels, récurrences et notifications fiables

- [~] Résultat : rappels confirmés, occurrences, outbox, leases et annulation sont livrés ; reçus asynchrones, appareils et PostgreSQL réel restent à qualifier.

Dépendances : B02/B03 ; parcours intégré après B06. Entrées : `run_reminder_worker.py`, `RecurringReminder`, `NotificationOutbox`, appareils, réglages brief. Cibles : scheduler/notification services et `expo-notifications`.

Travail : occurrences uniques avec fuseau, récurrence simple et DST ; rattrapage du brief après panne, modification/annulation des occurrences futures. Worker avec prise atomique/bail et retries exponentiels bornés, état d’échec terminal. Livraisons par appareil, tickets/reçus Expo, suppression des jetons invalides. Quota de notification, permissions mobiles, ouverture vers l’objet. Échéances consultables si push impossible. Un seul scheduler Cocoon doit être responsable des rappels.

Sortie : panne à l’heure prévue puis redémarrage, double worker, changement d’heure, modification d’un rappel déjà notifié, token invalide, aucun appareil et panne réseau testés. Vérifier push sur iOS/Android ; reçu fournisseur distingué de lecture utilisateur. Aucun LLM nécessaire pour délivrer les rappels existants.

## B08 — Qualification et livraison bêta

- [~] Résultat : Compose, migrations, sondes et documentation sont présents ; build distribué, restauration, observabilité et plateforme réelle restent à qualifier.

Dépendances : B00 à B07 terminés. Entrées : Compose, Caddy, Dockerfile, config API, `eas.json`, `docs/deployment.md`, scripts/tests.

Travail : config runtime LLM local/Ollama, STT et volumes, migration unique avant services, sortie réseau du worker Expo Push contrôlée et réellement testée, redémarrages et sondes ; environnement bêta séparé, quotas et invitations. CI lint/typecheck/tests/migrations ; tests E2E et corpus de 60 scénarios notés avec versions enregistrées. Mesurer séparément mémoire, utilité, ressenti et fiabilité selon `docs/ASSISTANT_EFFECTIVENESS_AUDIT.md`, avec 6 à 10 testeurs consentants et cas longitudinaux. Résoudre la divergence entre `UX-CONTRACT.md` et l'accueil sur le parcours capture/assistant. Logs sans données privées, alertes, sauvegarde chiffrée, restauration et rollback. Finaliser export/effacement/rétention. Mettre à jour README et deployment pour le seul chemin réellement vérifié. Produire builds Android/iOS signés pour le canal choisi, collecter les retours d’incident.

Sortie : preuve des 6 critères du PLAN dans `docs/validation/B08.md`, score du corpus (≥ 90 % comportement attendu et 100 % sécurité/confirmation), axes du benchmark et taux de retour publiés, tests sous 3 demandes simultanées, sondes/alertes vérifiées, restauration réussie et procédure de retour arrière. Valider les appareils et réseaux hors PC de développement. Toute impossibilité (matériel, signature iOS, hébergement, voix) reste explicitement ouverte ; pas de mention « prêt bêta » avant résolution.

## B09 — Embeddings et recherche hybride (après bêta)

- [ ] Résultat : retrouver des informations sémantiquement proches sans affaiblir l’isolation.

Dépendances : B05 et B08. Cibles : migration pgvector, adaptateur embeddings distinct, jobs d’indexation et recherche hybride.

Travail : comparer modèles sur corpus français, fixer dimension/révision, représenter source/version/hash/chunk. Indexation asynchrone idempotente des seules sources confirmées, suppression propagée. Recherche exacte filtrée par propriétaire puis fusion lexicale/vectorielle ; ajouter index approximatif seulement si mesure justifie. Réindexation parallèle et bascule sans mélanger modèles.

Sortie : cible initiale recall@5 ≥ 90 % sur questions annotées, comparaison à la recherche textuelle, aucune fuite A/B, source supprimée immédiatement absente des résultats, panne embedding sans perte de capture, reindexation/rollback testés. Seuil à documenter avant l’évaluation, jamais ajusté après pour cacher une régression.

## B10 — Compétences et nouvelles sources (après bêta)

- [ ] Résultat : étendre les contextes utiles sans réécrire le noyau ni ouvrir des pouvoirs génériques.

Dépendances : B08 ; B09 pour les longs documents sémantiques. Commencer par un cas concret priorisé par les retours des testeurs.

Travail : registre versionné de compétences déclaratives ; propositions de compétences, validation, activation explicite et désactivation. Puis un connecteur à la fois : agenda externe ou e-mail en lecture OAuth consentie, synchronisation incrémentale, révocation, minimisation et politique de rétention. Documents : S3 privé, contrôle de type/taille, analyse des fichiers, OCR, provenance et indexation. Les écritures externes passent par une proposition et une exécution durable avec rapprochement en cas d’incertitude fournisseur.

Sortie : un scénario utile complet avec tests d’isolation, expiration/révocation, replay et suppression ; aucune permission obtenue via contenu de skill/document. Aucun auto-déploiement, shell ou nouvelle dépendance installée par le modèle.

## Décomposition détaillée des lots

Les lots ci-dessus restent les unités de résultat. Les cases suivantes sont les unités de travail à traiter une par une. Une case ne doit être cochée qu’avec un test ou une preuve adaptée à son contenu.

### B00 — Audit et base reproductible

- `[x]` Vérifier l’état Git de la copie et ne pas modifier la configuration globale de Git ; l’audit lit l’état avec `safe.directory` local à la commande et confirme l’absence de commit sur cette copie, sans modifier la configuration globale.
- `[x]` Vérifier les fichiers ignorés et la présence éventuelle de secrets sans afficher leurs valeurs ; `scripts/audit-reproducibility.ps1` confirme l’absence de secret suivi et l’ignorance de `.env`.
- `[x]` Relever les versions Python, `uv`, Node, Expo, FastAPI, SQLAlchemy, Alembic et PostgreSQL ; Python 3.14.7, uv 0.11.18, Node 24.19.0, PostgreSQL 14.24 et les versions déclarées Expo/FastAPI/SQLAlchemy/Alembic sont consignés.
- `[~]` Inventorier toutes les migrations et confirmer leur ordre sur une base PostgreSQL de test ; la chaîne a été rejouée sur PostgreSQL 14.24 jusqu’à `20260922_29`, mais une base PostgreSQL dédiée et les scénarios concurrents restent à isoler.
- `[x]` Vérifier que `apps/api/migrations/env.py` charge tous les modèles nécessaires ; les modules auth, conversations, family spaces, personal, assistant et neural sont importés explicitement avant `Base.metadata`.
- `[ ]` Rejouer API, Ruff et typecheck mobile dans un environnement propre.
- `[x]` Compléter le corpus fictif des 60 scénarios et automatiser son contrôle structurel ainsi que l’exécution de plusieurs scénarios déterministes critiques dans `tests/test_scenario_corpus.py`.
- `[~]` Vérifier le modèle Ollama local, son endpoint et son temps jusqu’au premier token ; l’endpoint local répond avec `gemma4:e4b`, les appels `chat`/streaming réels retournent `mode=llm`, trois appels complets mesurés le 22/09/2026 ont pris 443 ms, 905 ms et 4 193 ms, et la mesure est rejouable par `scripts/validate-ollama.ps1` ; la mesure exacte du premier token et l’installation propre restent ouvertes.
- `[x]` Tester deux puis trois générations simultanées sans ajouter d’infrastructure prématurée ; trois appels réels à `gemma4:e4b` ont produit deux réponses `llm` et un `429` conforme à la limite configurée à deux.
- `[x]` Mettre à jour `docs/validation/B00.md` avec les versions, commandes, résultats et limites ; Python 3.14.7, Node 24.19.0, tête Alembic `20260922_29` et validation MVP y sont consignés.

### B01 — Identité et isolation

- `[x]` Écrire la matrice `User / FamilySpace / Conversation / Project / Memory / Task` dans `docs/security/access-matrix.md`.
- `[x]` Définir pour chaque ressource `owner`, `scope` et règle d’accès dans `docs/security/access-matrix.md` ; les surfaces assistant, personnelles, capture, famille et secrètes y sont distinguées.
- `[~]` Vérifier qu’aucune route ne fait confiance à un `user_id` fourni par le mobile ; les surfaces assistant, neural et personnelles filtrent maintenant l’owner côté serveur, l’audit complet des autres modules reste à terminer.
- `[~]` Centraliser les contrôles d’ownership et de membership côté API pour le contexte assistant ; les routes conversations, espaces familiaux, mémoire et personnel filtrent maintenant leur propriétaire/membre, l’audit exhaustif des surfaces restantes reste à terminer.
- `[~]` Ajouter l’identité dans les clés de cache et invalider au changement de compte ; les clés assistant, capture, mémoire, profil, notifications, appareils et données personnelles incluent maintenant l’utilisateur, le cache React Query reste purgé au changement de compte en conservant la partition secrète, tandis qu’un cache serveur distribué reste hors MVP.
- `[x]` Définir le modèle de consentement versionné et sa révocation ; le registre MVP connaît désormais `assistant.memory`, `assistant.projects`, `assistant.voice` et `notifications.push`, refuse les politiques inconnues, contrôle la version minimale et vérifie `notifications.push` au moment d’enregistrer un token.
- `[x]` Refuser par défaut l’injection des conversations secrètes et données familiales privées dans l’assistant.
- `[~]` Tester User A contre User B par UUID, cache, session réutilisée et pagination ; les tests assistant, mémoire, personnel, capture, conversation et famille couvrent l’accès croisé par UUID, les appareils peuvent maintenant être listés et révoqués par leur owner, les clés mobiles non secrètes sont partitionnées par compte, mais la réutilisation de cache distribué et PostgreSQL restent ouvertes.
- `[x]` Tester membre et non-membre d’un `FamilySpace`.
- `[ ]` Rejouer ces tests sur PostgreSQL avec deux transactions concurrentes.

### B02 — Propositions et exécution

- `[~]` Choisir le modèle canonique entre `AssistantProposal` et `NeuralProposal` ; le cycle de vie est maintenant partagé par `ProposalStatus` et le journal d’exécution relie les deux chemins, tandis que la fusion des modèles reste ouverte.
- `[~]` Ajouter version de payload, expiration et référence du run ; les deux modèles portent expiration, version, clé stable et date de confirmation, et `NeuralProposal.source_run_id` relie désormais les propositions de capture à leur run ; la fusion physique des modèles reste à finaliser.
- `[x]` Définir les statuts `PENDING / CONFIRMED / CANCELLED / EXPIRED / FAILED` ; une validation de payload échoue explicitement en `422`, journalise `failed` avec un code non sensible et interdit le rejeu.
- `[x]` Déplacer le verrouillage, l’expiration, le contrôle d’owner et le rejeu idempotent dans un service commun hors des routeurs ; les façades assistant et capture exposent maintenant confirmation et annulation, tandis que la création des ressources reste spécifique à chaque domaine.
- `[x]` Implémenter l’exécuteur pour tâche, rappel, note, course, entraînement et événement ; les chemins assistant et capture utilisent désormais le module d’exécution métier commun, avec des adaptateurs propres à leurs payloads.
- `[x]` Vérifier les permissions au moment de la confirmation ; le service commun verrouille et filtre chaque proposition par `user_id` avant toute validation de payload ou création de ressource.
- `[x]` Rendre création de la ressource, confirmation et journal d’exécution atomiques.
- `[~]` Tester double clic et retry réseau ; les parcours `/chat` et `/turn` réutilisent maintenant une clé d’idempotence persistée, et un probe PostgreSQL réel a confirmé qu’une double confirmation verrouillée produit exactement un résultat `first` et un `replay`, tandis que le scénario réseau complet reste à rejouer.
- `[~]` Tester alternatives incompatibles et conflits de version ; une confirmation assistant annule maintenant les autres propositions pendantes du même message, une proposition de capture peut être écartée via sa façade dédiée, le conflit de version est refusé en `409` sans effet, et le verrou PostgreSQL réel est confirmé ; la concurrence des alternatives complètes reste ouverte.
- `[x]` Ajouter la migration additive et la compatibilité temporaire des anciens endpoints ; les migrations `20260922_19` à `20260922_29` enrichissent progressivement les propositions, la provenance mémoire, les projets personnels et les façades assistant/capture restent compatibles.

### B03 — Conversation, capture et runs

- `[x]` Introduire une abstraction `LLMProvider` sans déplacer les secrets dans Expo.
- `[x]` Distinguer réponse LLM, fallback déterministe et erreur provider dans le contrat API ; les opérations structurées retombent sur les règles uniquement si le provider est indisponible, tandis qu’une réponse invalide et le chat personnel restent en erreur explicite.
- `[x]` Persister le message utilisateur avant l’appel LLM.
- `[x]` Garantir qu’un échec avant commit ne prétend pas avoir conservé la capture ; la capture brute et le message utilisateur sont persistés avant le travail provider.
- `[~]` Ajouter clé d’envoi, hash et détection de doublon ; les clés d’idempotence et le hash de capture sont persistés, et un retry sans clé réutilise désormais un run terminé du même compte ; la concurrence PostgreSQL de cette détection reste à qualifier.
- `[x]` Ajouter modèles `Run` et événements avec owner et statut ; le traitement partagé et le worker séparé existent.
- `[x]` Commiter capture et run avant l’accusé de réception ; `/api/captures/queue` retourne un run `queued` durable, le service Compose `capture-worker` le reprend séparément, tandis que `/api/captures` conserve le traitement immédiat de compatibilité.
- `[x]` Ajouter retries bornés, lease, reprise d’un run expiré et erreur terminale.
- `[x]` Rendre la lecture d’événements reprenable avec `after_sequence` et `Last-Event-ID`, contrôlés par owner.
- `[~]` Ajouter annulation serveur ; le worker revalide maintenant l’état juste avant la persistance, le mobile peut annuler un run connu et ne crée plus de proposition après une annulation concurrente, tandis que l’annulation fine d’une génération provider et la validation appareil restent à finaliser.
- `[x]` Remplacer les étapes de progression fictives par des événements réellement exécutés ; le flux expose uniquement `capture_persisted`, `claimed`, `understand_started`, `completed` ou `failed` effectivement persistés.
- `[~]` Tester coupure réseau, reprise mobile, redémarrage worker et erreur DB ; le mobile consomme désormais SSE, persiste la capture interrompue, vérifie le même `run_id` après remontage et attend brièvement un run `queued/running` sans recréer la capture, tandis que la reprise réelle après fermeture forcée, l’erreur DB et la concurrence PostgreSQL restent ouvertes.

### B04 — Runtime LLM local et outils contrôlés

- `[~]` Vérifier le provider choisi et le mode `local` sur une installation propre ; l’abstraction et le mode local sont en place, et Ollama `gemma4:e4b` a maintenant été sollicité réellement via l’adaptateur, mais l’installation propre reste à qualifier.
- `[x]` Vérifier que les credentials restent côté FastAPI et ne sont jamais sérialisés côté mobile.
- `[x]` Définir et versionner le catalogue interne des outils Cocoon ; trois lectures personnelles sont enregistrées, leurs paramètres sont strictement bornés, et les écritures retournent des propositions versionnées exécutées par B02 après confirmation.
- `[x]` Vérifier owner et permissions avant chaque lecture ou proposition d’outil.
- `[x]` Exposer les lectures et propositions Cocoon, jamais la confirmation ou une mutation directe depuis le LLM ; les lectures bornées tâches/agenda/mémoires sont injectées dans le contexte, et les écritures passent par les propositions B02 avec confirmation explicite.
- `[x]` Désactiver shell, sous-agents et outils non approuvés dans le registre interne.
- `[~]` Gérer concurrence, interruption, budget et erreurs réseau du runtime local ; les budgets d’appels/durée, la détection de répétition d’outil, la limite de concurrence, l’arrêt coopératif du flux provider et les erreurs réseau sont couverts, et le SSE conversationnel transmet désormais la déconnexion HTTP à l’événement d’annulation, tandis que l’essai d’annulation sur appareil réel reste à faire.
- `[~]` Tester A/B/A, reprise après redémarrage et tentative d’accès croisé ; le registre d’outils couvre maintenant A/B/A et le refus d’accès croisé local, tandis que la reprise réelle du provider reste à qualifier.
- `[~]` Documenter les limites du modèle Ollama pour JSON et appels d’outils ; `gemma4:e4b` a été testé en génération structurée réelle et peut entourer le JSON de fences Markdown, que le chemin d’organisation normalise ; les appels réels mesurés le 22/09/2026 varient de 443 ms à 4 193 ms, tandis que les appels d’outils réels et les limites de production restent à mesurer.

### B05 — Mémoire personnelle

- `[x]` Séparer mémoire de travail, épisodique, sémantique et procédurale au niveau du modèle ou des responsabilités.
- `[x]` Séparer forme de mémoire et type d’information : fait, préférence, contrainte, décision, objectif, intérêt, habitude.
- `[~]` Ajouter ou finaliser `owner`, `scope`, `source`, `confidence`, validité et provenance ; le contrat API expose owner/scope/source, les dates de validité filtrent maintenant retrieval et correction, les notes confirmées depuis le chat conservent le message assistant source et les notes de capture conservent désormais leur `source_run_id`, tandis que la qualification PostgreSQL reste à faire.
- `[x]` Conserver la capture brute sans la confondre avec une mémoire durable.
- `[~]` Ne pas créer une mémoire durable pour une question triviale ou un simple remerciement ; le filtre déterministe conserve désormais toute capture classée question malgré une requalification LLM, tandis que l’extracteur complet reste à renforcer.
- `[~]` Prioriser règles déterministes pour dates, actions et rendez-vous explicites ; les actions, jours de semaine seuls ou datés, dates numériques et expressions relatives explicites sont couverts, les scénarios plus ambigus restent à enrichir.
- `[x]` Créer `MemoryRepository`, `MemoryRetriever` et `ContextBuilder` séparés, puis exposer au mobile la consultation de la mémoire personnelle.
- `[x]` Filtrer permissions avant ranking et avant insertion dans le prompt.
- `[~]` Construire le contexte dans l’ordre : contraintes, faits actuels, projet, préférences, épisodes pertinents ; le retrieval privilégie maintenant déterministement contrainte, fait, décision/objectif de contexte projet, préférence puis épisode, tout en laissant la correspondance lexicale dominer. Les projets personnels sont désormais owner-scoped, accessibles par API et injectés via un outil de lecture borné ; le partage familial de projets reste hors contexte assistant.
- `[~]` Dédupliquer sans supprimer la provenance ; les propositions du chat comparent maintenant toutes les mémoires actives autorisées avec une clé normalisée, en conservant la mémoire et sa provenance, tandis que la provenance détaillée des épisodes reste à ajouter.
- `[~]` Gérer remplacement, contradiction, correction et oubli ; les préférences explicitement formulées remplacent maintenant uniquement une préférence du même sujet déterministe, avec provenance, et le mobile permet de corriger ou oublier une mémoire avec confirmation, tandis que les faits ambigus restent à corriger explicitement.
- `[~]` Propager l’oubli aux résumés, caches, index et contextes actifs ; les chaînes de remplacement sont maintenant invalidées récursivement avant retrieval/contexte, les caches distribués et index externes restent à traiter.
- `[x]` Tester fait, préférence non absolue, signal faible, contradiction, scope et isolation A/B au niveau des contrats actuels.

### B06 — Voix

- `[~]` Brancher maintien vocal, relâchement, annulation et permission dans l’écran d’accueil et le composer de l’assistant ; les deux surfaces réinjectent la transcription dans le champ texte corrigible, l’implémentation mobile gère aussi l’annulation pendant la demande de permission/démarrage, la validation sur appareil réel reste à faire.
- `[x]` Ajouter une alternative accessible au maintien vocal.
- `[x]` Limiter durée, taille, format et consommation mémoire avant traitement.
- `[~]` Vérifier le service STT réel et son contrat HTTP privé ; le contrat FastAPI et l’adaptateur sont testés, le consentement `assistant.voice` est vérifié à l’usage et le fournisseur réel reste à qualifier.
- `[x]` Afficher une transcription corrigible avant envoi au même pipeline que le texte.
- `[x]` Garantir le nettoyage des fichiers temporaires dans tous les chemins d’erreur côté mobile.
- `[x]` Ne pas conserver l’audio permanent sans consentement explicite.
- `[~]` Tester refus microphone, interruption, arrière-plan, audio vide et panne STT ; audio vide, taille, provider indisponible et transcription inexploitable sont couverts côté API, les scénarios microphone/appareil restent ouverts.
- `[ ]` Tester noms, dates et nombres français sur appareils iOS et Android.

### B07 — Rappels et notifications

- `[x]` Normaliser date, heure et fuseau côté serveur.
- `[x]` Implémenter occurrence unique et récurrence simple avec DST.
- `[x]` Gérer modification et annulation des occurrences futures.
- `[x]` Ajouter rattrapage après panne et redémarrage.
- `[x]` Ajouter lease, prise atomique, retries bornés et état terminal.
- `[x]` Empêcher le double envoi avec deux workers.
- `[~]` Distinguer livraison fournisseur, échec, reçu et lecture utilisateur ; ticket, reçu Expo et lecture utilisateur sont maintenant séparés, un reçu `DeviceNotRegistered` désactive le device associé sans conserver son token dans le ticket, et l’ouverture mobile utilise désormais un routage allowlisté vers la tâche ciblée, tandis que la validation fournisseur/appareil reste ouverte.
- `[~]` Gérer plusieurs appareils, tokens invalides et permissions mobiles ; tokens multiples, format Expo strict, consentement `notifications.push` vérifié à l’usage, révocation au logout, révocation utilisateur qui supprime immédiatement tous les tokens push, bouton d’activation/désactivation, enregistrement API et ouverture vers la cible du rappel sont en place, la permission réelle et le token sur appareil restent à valider.
- `[x]` Ajouter quotas et préférences personnelles de notification.
- `[~]` Tester réseau indisponible, aucun appareil, token invalide, DST, quota épuisé et rappel déjà livré ; aucun appareil devient un échec terminal consultable et les scénarios multi-appareils/format de token sont couverts localement, fournisseur/appareils/PostgreSQL restent à qualifier.

### B08 — Qualification bêta

- `[x]` Documenter la voie d'essai gratuite Vercel API/web + Supabase Free + ZeroGPU et l'installation d'un APK Android ; fournir le point d'entrée FastAPI, la configuration SPA Vercel et le profil APK. L'export web local a réussi le 24/09/2026 ; aucun déploiement externe ni APK installé n'est prouvé.
- `[ ]` Ajouter un provider Gradio ZeroGPU côté API, avec contrat de messages, quota partagé, file, erreurs, timeout et fallback ; vérifier un Space privé sur données fictives. Ne pas pointer `LLM_API_URL` vers un Space Gradio sans adaptateur.
- `[ ]` Qualifier Supabase Free : migrations depuis une connexion adaptée, pooler transactionnel et `prepare_threshold=None`, SSL, concurrence, limite de connexions, dump puis restauration isolée.
- `[ ]` Déployer deux projets Vercel distincts (API et web), fixer les variables serveur/client, tester le préflight CORS depuis l'origine exacte du web, les routes profondes, le flux SSE, les limites de durée et le corps de requête.
- `[ ]` Décider et implémenter le remplacement des workers permanents pour captures en file et rappels ; Vercel Hobby Cron quotidien ne convient pas aux rappels à l'heure. Pour la messagerie temps réel, tester l'upgrade WebSocket FastAPI/Python sur Vercel, la diffusion entre instances et la reconnexion cliente ; le polling HTTP actuel de 8 s peut servir au prototype.
- `[ ]` Construire, signer et installer l'APK preview avec une URL API HTTPS et un package Android propre au projet, puis valider Wi-Fi/données mobiles, session et mise à jour signée ; FCM v1 et push réel restent un chantier distinct.
- `[~]` Définir un environnement bêta séparé avec PostgreSQL, workers de capture/rappel et runtime LLM privés ; Compose et le cloisonnement réseau sont présents, déploiement réel non exécuté.
- `[x]` Vérifier la chaîne de migration et ajouter une sonde de readiness PostgreSQL distincte de la liveness.
- `[x]` Automatiser lint, typecheck, tests locaux et garde-fou réseau Compose ; le workflow CI prévoit maintenant un PostgreSQL jetable et `alembic upgrade head` avant les tests, sans accès à Supabase. Cette nouvelle étape attend encore une exécution GitHub réussie ; l’isolation et les migrations dans l’environnement bêta réel restent à qualifier.
- `[~]` Ajouter E2E capture → compréhension → proposition → confirmation ; le chemin API avec file worker, accueil et confirmation est maintenant couvert, tandis que le parcours mobile réel reste à qualifier.
- `[~]` Vérifier logs sans contenu privé, métriques, alertes et corrélation des runs ; corrélation, absence de corps, compteurs agrégés protégés, audit statique frontend strict et une sonde PowerShell readiness/métriques sont validés localement, scraper/alertes réels restent à brancher.
- `[~]` Fournir les scripts de sauvegarde PostgreSQL custom chiffrée avec `age`, restauration explicitement confirmée et nettoyage des temporaires ; l’exécution sur une base bêta dédiée et le rollback restent à prouver.
- `[~]` Construire et installer le build Android ; le bundle Android Expo est maintenant exporté avec succès (1419 modules, 3,5 MB) dans un répertoire temporaire, mais l’installation sur appareil et les tests réseau restent à faire.
- `[~]` Exporter puis valider iOS si la signature est disponible ; l’export Expo iOS local a réussi le 22/09/2026 (1297 modules, bundle Hermes 3,2 MB), mais la signature, l’installation et le test sur appareil restent ouverts.
- `[~]` Tester trois requêtes simultanées, changement de compte et reprise après coupure ; le budget provider local refuse la troisième requête au-delà de deux concurrentes, tandis que les scénarios mobile/réseau et PostgreSQL restent à qualifier.
- `[x]` Rédiger `docs/validation/B08.md` et ne pas appeler la solution « prête bêta » avant preuve complète.

### B09 — Embeddings après bêta

- `[ ]` Comparer les modèles d’embeddings sur le corpus français.
- `[ ]` Fixer dimension, version, hash, source et stratégie de réindexation.
- `[ ]` Ajouter pgvector de manière réversible et reconstruisible.
- `[ ]` Indexer uniquement les données confirmées et accessibles.
- `[ ]` Filtrer par owner/scope avant fusion lexical/vectoriel.
- `[ ]` Tester suppression immédiate, panne d’embedding, réindexation et rollback.
- `[ ]` Mesurer recall@5 contre la recherche SQL/plein texte et consigner le seuil avant validation.

### B10 — Compétences et connecteurs après bêta

- `[ ]` Créer un registre de compétences versionné, limité et explicitement activé.
- `[ ]` Ajouter consentement, révocation et expiration par compétence.
- `[ ]` Choisir un premier connecteur en lecture seule et documenter sa minimisation des données.
- `[ ]` Ajouter provenance, taille/type, rétention et suppression pour les documents.
- `[ ]` Faire passer toute écriture externe par proposition et exécution idempotente.
- `[ ]` Tester expiration, révocation, replay, suppression et isolation.
- `[ ]` Interdire shell, auto-déploiement et permissions obtenues depuis le contenu d’un document ou d’une skill.

## Fil d’implémentation technique

Cette section donne l’ordre concret de réalisation. Chaque étape doit produire un résultat utilisable par l’étape suivante. Ne pas commencer une étape suivante si son prérequis est seulement « présent dans le code » mais pas testé.

### Étape 0 — Préparer le poste et la preuve

1. Lire `README.md`, `VISION.md`, `PLAN.md`, `docs/PROJECT_AUDIT.md` et les instructions locales.
2. Depuis `apps/api`, installer ou vérifier l’environnement verrouillé avec `uv sync --locked --extra dev`.
3. Vérifier que la base de test est distincte de toute base personnelle ; utiliser un `.env` de test dédié.
4. Exécuter `alembic upgrade head` sur PostgreSQL de test, puis démarrer l’API et le worker séparément.
5. Exécuter pytest, Ruff et le typecheck mobile ; enregistrer les versions et sorties dans `docs/validation/B00.md`.
6. Vérifier l’état Git avec une commande en lecture seule ; ne pas modifier la configuration globale pour contourner un problème de propriétaire.
7. Créer le corpus de scénarios sous `docs/validation/B00-scenarios.md`, puis ajouter un test automatisé par comportement critique.

### Étape 1 — Cartographier le modèle d’accès avant toute nouvelle table

1. Lire `auth/dependencies.py`, `auth/models.py`, `conversations/models.py`, `family_spaces/models.py`, `personal/models.py`, `assistant/models.py` et `neural/models.py`.
2. Établir une table de décision : ressource, owner, scope, endpoint de lecture, endpoint d’écriture, source autorisée dans le contexte assistant.
3. Réutiliser `get_current_user`, `membership_or_not_found`, `visible_membership_or_not_found` et `owned_or_not_found` ; ne pas créer un second système d’autorisation.
4. Pour chaque nouvelle requête SQL, placer la contrainte d’owner/membership dans le `where` initial, avant pagination, ranking ou chargement relationnel.
5. Ajouter d’abord les tests négatifs : UUID d’un autre compte, compte non membre, session expirée, appareil révoqué et cache issu d’un autre compte.
6. Seulement après ces tests, préparer la migration de consentement et les éventuelles contraintes PostgreSQL.
7. Valider B01 avec deux utilisateurs et une famille réelle en base PostgreSQL de test.

### Étape 2 — Unifier le contrat de proposition

1. Comparer `assistant/models.py::AssistantProposal` et `neural/models.py::NeuralProposal` avec leurs routes respectives.
2. Définir le modèle canonique avant d’écrire un nouvel endpoint ; conserver les anciens endpoints comme façades temporaires.
3. Ajouter une migration pour `schema_version`, `idempotency_key`, `source_run_id`, `expires_at`, `execution_status` et `confirmed_resource_id` si absents.
4. Créer un service dédié, par exemple `assistant/proposals.py`, qui expose : `create`, `get_authorized`, `confirm`, `cancel`, `expire`.
5. Créer un exécuteur séparé, par exemple `assistant/executor.py`, qui reçoit une proposition déjà autorisée et retourne la ressource créée ou modifiée.
6. Encadrer confirmation et création métier par une transaction ; verrouiller la proposition avec `SELECT ... FOR UPDATE` sur PostgreSQL.
7. Traiter l’idempotence avant le code métier : si la clé a déjà produit un résultat, retourner le résultat existant sans nouvelle écriture.
8. Ajouter les tests de double clic, retry HTTP, deux confirmations simultanées, alternative concurrente, expiration et rollback.
9. Adapter ensuite `assistant/router.py` et `neural/router.py` pour appeler le service commun.

### Étape 3 — Transformer la capture en run durable

1. Conserver `neural/router.py::_capture` comme point de départ, mais déplacer sa logique transactionnelle dans `neural/service.py` ou un service `runs.py`.
2. Créer les tables `assistant_runs`, `assistant_jobs` et `assistant_run_events` seulement après avoir défini les statuts et transitions autorisées.
3. Un run doit contenir au minimum : `id`, `user_id`, `capture_id` ou message source, `status`, `idempotency_key`, `created_at`, `updated_at`, `cancelled_at` et `error_code` non sensible.
4. Un événement doit contenir : `run_id`, séquence monotone, type, payload sûr, date et owner indirect par le run.
5. Commiter la capture, le run et le job avant de renvoyer l’accusé HTTP ; ne jamais créer un job orphelin.
6. Faire prendre le job par le worker avec une lease et un nombre de tentatives borné ; un retry doit reprendre le même run.
7. Exposer `GET /api/runs/{run_id}` et `GET /api/runs/{run_id}/events` avec contrôle d’owner.
8. Faire évoluer `/api/captures/stream` vers SSE réel : `id`, `event`, `data`, reconnexion `Last-Event-ID`, fin explicite et erreur structurée.
9. Ajouter l’annulation vérifiée par le worker avant chaque étape coûteuse ; une annulation ne supprime pas la capture brute.
10. Remplacer les progrès « analyse/recherche/génération » par des événements émis uniquement lorsque l’étape correspondante a réellement démarré.

### Étape 4 — Stabiliser l’appel Ollama et l’abstraction provider

1. Lire `assistant/service.py::llm_chat`, `assistant/kernel.py` et `core/config.py` avant de modifier les prompts.
2. Créer une interface locale `LLMProvider` avec `chat`, `stream_chat` et `generate_structured` ; adapter l’implémentation existante sans changer le mobile.
3. Retourner un résultat explicite contenant au minimum `content`, `mode`, `provider`, `model` et une erreur normalisée ; ne jamais inclure de secret.
4. Garder la logique déterministe pour les dates, propriétaires, permissions, déduplication et confirmation.
5. Configurer des timeouts distincts : connexion, lecture inactive, annulation et limite de travail ; ne pas imposer une limite courte à la génération active.
6. Ajouter des tests avec provider simulé pour JSON valide, JSON entouré de Markdown, JSON invalide, indisponibilité et fallback.
7. Ajouter un test d’intégration local avec Ollama si le service est disponible et enregistrer le modèle réellement observé.
8. Ne pas déclarer `mode=llm` si le provider n’a pas effectivement renvoyé une réponse exploitable.

### Étape 5 — Construire les outils personnels dans Cocoon

1. Ne pas intégrer Hermes, son gateway, sa session, son protocole ou son catalogue dans le produit.
2. Définir un registre interne `ToolDefinition` avec nom, version, description, schéma d’entrée, niveau de lecture/écriture et service propriétaire.
3. Commencer avec des outils de lecture simples : tâches personnelles, événements autorisés et mémoires accessibles.
4. Faire retourner par chaque outil un résultat structuré borné, sans prompt, secret ou donnée d’un autre compte.
5. Pour toute écriture, faire retourner une proposition versionnée ; l’appel outil ne confirme jamais l’action.
6. Vérifier `current_user`, owner, scope et consentement dans le service métier, même si le LLM a reçu un contexte correct.
7. Ajouter budget par run, limite de profondeur, détection de boucle et annulation.
8. Ajouter des tests A/B/A, UUID étranger, tool inconnu, payload invalide, retry et service indisponible.
9. Faire un essai avec le runtime Ollama réel avant de cocher B04 ; les tests mocks ne suffisent pas.

### Étape 6 — Refondre la mémoire V1 sans embeddings

1. Définir les enums et valeurs autorisées dans `neural/models.py` ou un module mémoire dédié avant de changer les prompts.
2. Conserver `Capture` comme source brute et `MemoryItem` comme représentation durable ; ajouter les liens de provenance plutôt que copier le message entier.
3. Ajouter les champs nécessaires par migration additive : `owner_type`, `owner_id`, `scope_type`, `scope_id`, `memory_type`, `source`, `confidence`, `valid_from`, `valid_to`, `supersedes_id`, `deleted_at`.
4. Créer `memory/repository.py` pour les lectures/écritures autorisées et `memory/service.py` pour les règles métier.
5. Créer `memory/extractor.py` qui reçoit un message ou un run terminé et retourne des faits candidats validés par schéma.
6. Appliquer les règles déterministes avant le LLM : rendez-vous daté → proposition de rappel ; préférence explicite → mémoire candidate ; question simple → aucun souvenir.
7. Créer `memory/retriever.py` avec recherche SQL/plein texte bornée ; filtrer owner et scope dans la requête SQL initiale.
8. Créer `assistant/context.py` pour assembler message récent, contraintes, faits actuels, projet, préférences et épisodes, avec un budget de tokens mesuré.
9. Ajouter endpoints de consultation, correction et oubli uniquement pour les mémoires de l’utilisateur courant.
10. Lors d’un oubli, invalider mémoire active, épisodes dérivés et cache de contexte ; ne pas supprimer aveuglément la capture brute requise par la rétention légale/documentée.
11. Tester explicitement les cas VISION : Paul, préférence FastAPI, préférence non absolue, merci, Docker comme signal, Vue puis React, scope global/projet et A/B.

### Étape 7 — Brancher la voix au même pipeline

1. Vérifier `assistant/voice.py`, le schéma de transcription et le flux `expo-audio` côté mobile.
2. Ajouter validation de taille, type MIME, durée et fréquence avant de lire l’audio en mémoire.
3. Stocker temporairement l’audio hors répertoire public avec un identifiant de nettoyage garanti par `finally`.
4. Transcrire côté serveur privé ; renvoyer texte, langue, durée et avertissements, jamais les credentials du provider.
5. Afficher le texte dans le composer et exiger une validation ou correction avant création du run.
6. Réutiliser la même route/service de capture que le texte ; la voix ne doit pas créer une branche métier parallèle.
7. Tester microphone refusé, interruption, annulation, audio vide, panne STT, taille maximale et caractères français sur appareil réel.

### Étape 8 — Fiabiliser le scheduler et les notifications

1. Lire `commands/run_reminder_worker.py`, `RecurringReminder`, `NotificationOutbox` et la migration `20260915_07_notification_outbox.py`.
2. Stocker les échéances en UTC avec fuseau source et règles de récurrence versionnées.
3. Calculer les prochaines occurrences par code déterministe ; ne pas demander au LLM de calculer une date d’exécution.
4. Remplacer la comparaison exacte à la minute par une fenêtre de rattrapage et un état d’occurrence persistant.
5. Prendre une occurrence par verrou/lease, écrire l’outbox dans la même transaction que l’état, puis livrer hors transaction.
6. Ajouter retry, backoff, erreur terminale, compteur et dernière erreur non sensible.
7. Gérer plusieurs devices, tokens invalides, permissions et ouverture vers l’objet concerné.
8. Tester panne avant/après livraison, double worker, DST, modification, annulation et push indisponible.

### Étape 9 — Fermer la boucle mobile

1. Adapter `apps/mobile/src/services/api.ts` aux contrats versionnés de run, événements, propositions et mémoire.
2. Dans `apps/mobile/app/home.tsx`, conserver une entrée universelle et afficher les étapes réellement reçues.
3. Dans `apps/mobile/app/assistant.tsx`, empêcher double envoi, conserver le brouillon et afficher séparément réponse, proposition, confirmation et erreur.
4. Invalider les queries avec des clés contenant le compte courant ; vider cache et écran au logout.
5. Gérer reconnexion SSE, reprise d’un run, annulation et navigation vers la ressource confirmée.
6. Ajouter états de chargement, vide, indisponibilité LLM, capture conservée, action en attente et confirmation réussie ; l’accueil affiche la progression SSE, l’état mis en file, les erreurs et les propositions à confirmer, tandis que la reprise visuelle après redémarrage reste à faire.
7. Tester Android/iOS avec clavier, arrière-plan, coupure réseau et changement de compte.

### Étape 10 — Qualification et passage de lot

1. Pour chaque lot, créer ou mettre à jour `docs/validation/Bxx.md` avec prérequis, commandes, résultats, limites et date.
2. Rejouer les tests ciblés après chaque migration puis la suite complète avant de passer au lot suivant.
3. Vérifier les logs afin qu’aucun prompt, secret, token, contenu privé ou donnée familiale interdite ne soit imprimé.
4. Réaliser les tests PostgreSQL et concurrence avant de cocher une garantie transactionnelle.
5. Réaliser les tests Ollama/STT/push/appareil avant de qualifier une intégration réelle.
6. Mettre à jour `docs/PROJECT_AUDIT.md` dès qu’un comportement réel change.
7. Ne cocher le résultat d’un lot que lorsque toutes ses sous-tâches critiques et sa sortie sont prouvées.

## Fiches de mise en œuvre technique par lot

Ces fiches expliquent ce que chaque case doit produire techniquement. Elles ne remplacent pas les tests : une tâche est terminée seulement lorsque son résultat est démontré.

### B00 — Préparer une base de travail reproductible

#### B00.1 — Inventaire du dépôt

À mettre en place :

- inventorier `apps/api`, `apps/mobile`, `docker`, `packages`, les migrations et les workers ;
- identifier pour chaque module son propriétaire fonctionnel et ses dépendances ;
- vérifier les lockfiles et les versions réellement utilisées par `uv`, Python, Node et Expo ;
- rechercher les fichiers `.env`, certificats, tokens et credentials sans afficher leur contenu ;
- confirmer que les fichiers générés, caches et bases locales ne sont pas suivis par le dépôt ;
- utiliser `scripts/audit-reproducibility.ps1` pour rejouer cet inventaire sans modifier Git ni afficher de secret ;
- documenter les commandes d’installation et de démarrage dans `docs/CURRENT_ARCHITECTURE.md`.

Validation : une installation propre permet de lancer les contrôles de référence sans dépendre d’un état caché de la machine.

#### B00.2 — Cartographier l’architecture

À mettre en place :

- [x] décrire le flux authentification → route API → service → repository/SQL → réponse dans `docs/CURRENT_ARCHITECTURE.md` ;
- [x] décrire séparément les flux chat, capture, proposition, confirmation, voix et rappel dans `docs/CURRENT_ARCHITECTURE.md` ;
- [x] produire une matrice `KEEP / REFACTOR / REMOVE / REBUILD` pour les modules existants dans `docs/CURRENT_ARCHITECTURE.md` ;
- [x] noter les duplications entre `assistant/router.py`, `neural/router.py` et les services personnels dans `docs/CURRENT_ARCHITECTURE.md` ;
- ne pas créer un nouveau service si un service existant peut porter le contrat sans mélange de responsabilités.

Validation : `docs/CURRENT_ARCHITECTURE.md` permet à un autre développeur de retrouver le chemin d’une requête sans deviner.

#### B00.3 — Établir la preuve initiale

À mettre en place :

- créer une base PostgreSQL dédiée aux tests d’intégration ;
- exécuter toutes les migrations depuis zéro puis vérifier `alembic current` et `alembic heads` ;
- exécuter pytest, Ruff et le typecheck mobile ;
- enregistrer versions, commandes, durée et limites dans `docs/validation/B00.md` ;
- ajouter les 60 scénarios de référence avec identifiant stable, résultat attendu et statut automatisé.

Validation : les échecs de l’environnement sont distingués des échecs du code et aucune base personnelle n’est modifiée.

#### B00.4 — Mesurer le runtime LLM local

À mettre en place :

- vérifier l’URL Ollama configurée côté API et le modèle réellement chargé ;
- envoyer une requête minimale depuis `apps/api`, jamais depuis Expo ;
- mesurer temps de connexion, premier token, débit, durée totale et taille maximale de contexte ;
- mesurer deux puis trois requêtes simultanées ;
- documenter le comportement lorsque le modèle est indisponible ;
- séparer timeout de connexion, timeout d’inactivité et annulation utilisateur.

Validation : `mode=llm` n’est annoncé que lorsqu’une réponse du modèle local a réellement été reçue.

### B01 — Construire l’isolation avant la mémoire

#### B01.1 — Définir ownership et scope

À mettre en place :

- établir une table pour `User`, `FamilySpace`, `Conversation`, `Message`, `MemoryItem`, `PersonalTask`, `Run` et `Proposal` ;
- préciser si l’objet appartient à un utilisateur, à une famille ou à une conversation ;
- distinguer `owner` — à qui appartient la donnée — et `scope` — dans quel contexte elle est valable ;
- définir les données personnelles jamais injectées automatiquement dans l’assistant ;
- réserver le partage familial aux informations explicitement collectives.

Validation : chaque ressource a une règle de lecture et d’écriture écrite avant l’ajout d’une nouvelle route.

#### B01.2 — Renforcer les repositories

À mettre en place :

- utiliser `get_current_user` pour l’identité authentifiée ;
- réutiliser `owned_or_not_found` et `membership_or_not_found` lorsque leur contrat convient ;
- remplacer toute requête générale par une requête filtrée par `user_id`, `owner_id` ou membership ;
- appliquer le filtre d’accès dans le premier `select`, avant ranking, pagination ou chargement de relation ;
- retourner 404 pour ne pas révéler l’existence d’une ressource privée d’un autre compte ;
- tester également les routes secondaires, exports, notifications, WebSocket et fichiers.

Validation : connaître l’UUID d’un objet ne permet pas de le lire, le modifier, le confirmer ou le supprimer.

#### B01.3 — Ajouter consentements et cache sûr

À mettre en place :

- créer une table de consentement avec utilisateur, type, version, portée, date d’accord et date de révocation ;
- vérifier le consentement au moment de l’utilisation, pas uniquement à l’installation ;
- inclure `user_id` et version de contexte dans les clés de cache ;
- invalider les caches à la déconnexion et au changement de compte ;
- ne pas utiliser un simple verrou biométrique mobile comme preuve d’autorisation serveur.

Validation : une session, un cache ou un token réutilisé après changement de compte ne révèle aucune donnée.

### B02 — Unifier les propositions et l’exécution

#### B02.1 — Choisir le modèle canonique

À mettre en place :

- comparer les colonnes de `AssistantProposal` et `NeuralProposal` ;
- choisir un modèle source de vérité et planifier une migration additive ;
- conserver temporairement les anciens endpoints comme adaptateurs ;
- ajouter `schema_version`, `idempotency_key`, `source_run_id`, `expires_at`, `execution_status` et `confirmed_resource_id` si absents ;
- définir les statuts et transitions autorisées dans le code, pas seulement dans le prompt.

Validation : chaque proposition possède un owner, une action typée, une source et un état observable.

#### B02.2 — Créer le service d’exécution

À mettre en place :

- créer un service de proposition indépendant des routeurs HTTP ;
- valider le payload avec Pydantic avant toute écriture ;
- vérifier owner, scope, consentement et version attendue au moment de la confirmation ;
- déléguer la création à `personal`, `assistant` ou un service métier spécialisé ;
- retourner l’identifiant de la ressource créée et l’état de la proposition ;
- ne jamais accepter un `confirmed=true` fourni par le LLM ou le mobile.

Validation : une proposition non confirmée ne crée aucune tâche, mémoire, course, événement ou rappel.

#### B02.3 — Garantir l’idempotence

À mettre en place :

- verrouiller la proposition dans une transaction PostgreSQL ;
- créer une contrainte unique sur la clé d’idempotence dans la portée appropriée ;
- enregistrer le résultat d’exécution avant de répondre ;
- retourner le résultat existant en cas de retry ;
- annuler les alternatives incompatibles dans la même transaction ;
- retourner 409 en cas de conflit de version sans effet partiel.
- transformer toute erreur de payload métier en état terminal `FAILED` avec un code stable (`invalid_payload`) ; ne pas transformer un conflit temporaire d’agenda en échec définitif ; ne jamais exposer les détails Pydantic au client.
- exposer `payload_version` dans chaque proposition et accepter une version attendue facultative (`X-Proposal-Version`) ; verrouiller puis comparer la version avant validation ou mutation et retourner `409` si elle est obsolète.

Validation : double clic, retry réseau et deux confirmations simultanées produisent une seule mutation ; une proposition `FAILED` conserve son journal et refuse toute nouvelle confirmation.

### B03 — Rendre la conversation et la capture durables

#### B03.1 — Stabiliser le pipeline texte

À mettre en place :

- conserver le message utilisateur avant l’appel LLM ;
- charger l’historique autorisé avec une limite explicite ;
- construire le contexte dans un service et non dans le routeur ;
- sauvegarder réponse, fallback ou erreur dans un état identifiable ;
- empêcher une deuxième soumission tant que le premier run est actif ;
- conserver le brouillon mobile lors d’une erreur réseau.

Validation : un échec LLM ne supprime pas le message utilisateur et ne crée pas une réponse fictive.

#### B03.2 — Créer les runs et jobs

À mettre en place :

- créer les tables de run, job et événement avec owner indirect obligatoire ;
- définir les transitions `QUEUED`, `RUNNING`, `WAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, `CANCELLED` ;
- enregistrer une clé d’idempotence sur le run ;
- commiter capture, run et job avant l’accusé HTTP ;
- ajouter lease, tentative, prochaine reprise et erreur non sensible ;
- faire reprendre le même run après redémarrage du worker.

Validation : une coupure après l’accusé n’entraîne ni perte ni duplication de capture.

#### B03.3 — Implémenter SSE reprenable

À mettre en place :

- numéroter les événements par run ;
- supporter `Last-Event-ID` et la reprise depuis le dernier événement connu ;
- vérifier owner avant d’envoyer chaque événement ;
- envoyer une fin explicite et une erreur structurée ;
- ne pas émettre `Recherche` ou `Génération` avant l’exécution réelle de l’étape ;
- ajouter annulation serveur vérifiée par le worker.

Validation : fermeture/réouverture de l’application reprend le même run et ne lit pas les événements d’un autre compte.

#### B03.4 — Brancher l’entrée universelle mobile

À mettre en place :

- garder un seul champ d’entrée pour texte et transcription vocale ;
- envoyer le contenu relu vers `/api/captures/stream` avec fuseau et clé d’idempotence ;
- afficher sous le champ les étapes réellement reçues par SSE, sans inventer de progression ;
- conserver le texte tant que le traitement n’est pas accepté ;
- basculer la même capture vers `/api/captures/queue` après une panne réseau non liée à une erreur de validation ou d’autorisation ;
- rafraîchir l’accueil après résultat ou mise en file afin de présenter les propositions confirmables ;
- laisser la conversation générale accessible séparément depuis l’écran assistant, sans la confondre avec la capture universelle.

Validation : une capture texte ou vocale suit le même service, une panne transitoire ne perd pas le texte, une erreur 4xx n’est pas transformée en job silencieux, une capture mise en file reste visible dans l’état de l’accueil, un run connu peut être retrouvé après remontage de l’écran et une annulation confirmée côté serveur conserve la capture brute sans proposition tardive.

### B04 — Utiliser le runtime LLM local et des outils Cocoon

#### B04.1 — Abstraire le provider

À mettre en place :

- créer `LLMProvider` avec `chat`, `stream_chat` et `generate_structured` ;
- adapter `assistant/service.py::llm_chat` derrière cette interface ;
- conserver URL, modèle et clé dans `core/config.py` et l’environnement API ;
- normaliser `content`, `mode`, `model`, `usage` et les erreurs ;
- distinguer fallback déterministe, indisponibilité et réponse LLM valide ;
- tester JSON valide, Markdown parasite, sortie invalide, timeout et annulation.

Validation : le reste du domaine assistant ne connaît pas la bibliothèque HTTP ou le fournisseur concret.

#### B04.2 — Définir le registre d’outils interne

À mettre en place :

- créer une définition d’outil avec nom, version, description, schéma d’entrée, niveau d’accès et service appelé ;
- commencer par lectures personnelles : tâches, agenda, mémoires accessibles ;
- limiter les résultats par taille et par owner ;
- interdire shell, sous-agents, appels réseau arbitraires et outils non enregistrés ;
- journaliser run, outil, statut et durée sans journaliser les secrets ou le contenu privé complet.

Validation : un outil inconnu est refusé et un outil connu ne peut lire qu’un contexte autorisé.

#### B04.3 — Relier les écritures aux propositions

À mettre en place :

- faire retourner une proposition lorsqu’un outil demande une mutation ;
- interdire à l’outil et au LLM de confirmer eux-mêmes ;
- envoyer la proposition au service B02 ;
- afficher dans le mobile l’action, les données modifiées, la portée et l’expiration ;
- exécuter uniquement après clic utilisateur et revalidation des droits.

Validation : le LLM peut suggérer une tâche mais ne peut pas la créer seul.

### B05 — Construire la mémoire personnelle

#### B05.1 — Étendre `MemoryItem` proprement

À mettre en place :

- garder la capture brute comme source et la mémoire comme synthèse ;
- distinguer `kind` — working, episodic, semantic, procedural — et `type` — fact, preference, constraint, decision, goal, interest, habit ;
- ajouter owner, scope, source, confidence, validité, statut et provenance ;
- stocker `source_message_id` ou `source_capture_id` ;
- ajouter `supersedes_id` ou équivalent pour les corrections ;
- prévoir suppression logique et purge physique documentée.

Validation : on peut répondre à « pourquoi sais-tu cela ? » sans exposer une chaîne de pensée.

#### B05.2 — Implémenter l’extraction contrôlée

À mettre en place :

- créer un extracteur qui retourne une liste structurée de candidats ;
- appliquer les règles déterministes avant l’appel LLM ;
- transformer un rendez-vous explicite en proposition de rappel avec `reminder_at` ;
- ne pas mémoriser un simple merci ou une question isolée ;
- conserver les candidats non confirmés séparément des mémoires actives ;
- valider taille, type, contenu sensible et owner avant persistance.

Validation : une date explicite n’est pas réduite à une note générique et une préférence personnelle ne devient pas familiale.

#### B05.3 — Implémenter retrieval et contexte

À mettre en place :

- créer `MemoryRepository` pour les requêtes filtrées ;
- créer `MemoryRetriever` pour pertinence, fraîcheur et importance ;
- créer `ContextBuilder` pour l’ordre et le budget de tokens ;
- filtrer owner et scope dans SQL avant tout ranking ;
- privilégier contraintes, faits actuels, projet, préférences puis épisodes pertinents ;
- retourner un contexte vide honnête lorsqu’aucune mémoire n’est accessible.

Validation : User B ne retrouve pas la mémoire de User A et une préférence n’écrase pas une contrainte du projet courant.

#### B05.4 — Gérer contradictions et oubli

À mettre en place :

- marquer l’ancienne valeur comme historique lorsqu’une nouvelle valeur explicite arrive ;
- conserver les mémoires de scopes différents lorsqu’elles ne sont pas contradictoires ;
- proposer correction et suppression depuis une route autorisée ;
- invalider résumés, caches et index dérivés ;
- tester la non-résurrection après nouvelle session ou redémarrage.

Validation : « je préfère Vue » puis « maintenant React » produit un état actuel React et une trace historique Vue.

### B06 — Brancher la voix sur le pipeline texte

À mettre en place :

- gérer permission, appui, relâchement, annulation et interruption dans `apps/mobile` ;
- limiter durée, taille et MIME avant upload ;
- traiter l’audio dans un emplacement temporaire privé ;
- transcrire côté serveur via `assistant/voice.py` ;
- supprimer le fichier temporaire dans succès, erreur et annulation ;
- afficher la transcription dans le composer avant création du run ;
- réutiliser `/api/captures` plutôt que créer un workflow métier vocal parallèle ;
- proposer une alternative accessible à l’appui continu.

Validation : micro refusé, appel entrant, audio vide, panne STT, noms, dates et nombres français sont gérés sur appareil réel.

### B07 — Rendre les rappels fiables

#### B07.1 — Calculer les occurrences

À mettre en place :

- stocker instant UTC et fuseau de création ;
- calculer prochaine occurrence avec une bibliothèque temporelle déterministe ;
- couvrir récurrence simple, mois courts et changement DST ;
- séparer occurrence planifiée, occurrence livrée et occurrence lue ;
- recalculer les occurrences futures lors d’une modification.

#### B07.2 — Faire fonctionner le worker

À mettre en place :

- prendre une occurrence par verrou ou lease ;
- écrire l’état et l’outbox dans une transaction ;
- livrer hors transaction avec retries et backoff ;
- marquer l’échec terminal et conserver une erreur non sensible ;
- rattraper les occurrences manquées depuis le dernier heartbeat ;
- empêcher deux workers de livrer le même rappel.

#### B07.3 — Gérer les appareils

À mettre en place :

- associer plusieurs tokens à l’utilisateur ;
- supprimer ou désactiver les tokens refusés par le fournisseur ;
- gérer permission refusée et absence d’appareil ;
- ouvrir la tâche ou l’événement après contrôle de session ;
- appliquer les préférences et quotas propres à chaque utilisateur.

Validation : un rappel reste consultable même si le push échoue et n’est jamais livré deux fois par deux workers.

### B08 — Qualifier la bêta

À mettre en place :

- séparer environnements, bases, secrets, volumes et comptes de test ;
- démarrer le service de migration unique avant API et workers avec une sonde de santé utile ;
- automatiser lint, typecheck, tests, migrations et tests d’isolation ;
- exécuter le parcours E2E capture → proposition → confirmation ;
- tester trois requêtes simultanées et plusieurs comptes ;
- vérifier logs sans prompt complet, token, secret ou donnée privée interdite ;
- sauvegarder, restaurer et tester une procédure de rollback ;
- installer le build Android puis tester réseau local, réseau contrôlé et reprise ;
- valider iOS si la signature est disponible ;
- consigner les limites dans `docs/validation/B08.md` avant toute mention bêta.

### B09 — Ajouter les embeddings après la bêta

À mettre en place :

- définir un adaptateur d’embedding séparé du provider conversationnel ;
- versionner modèle, dimension, hash et source ;
- indexer uniquement les mémoires confirmées et accessibles ;
- filtrer owner/scope avant fusion avec la recherche lexicale ;
- rendre indexation, suppression et réindexation idempotentes ;
- tester panne du modèle, suppression propagée et rollback ;
- comparer recall@5 avec SQL/plein texte sur le corpus avant de retenir pgvector.

### B10 — Ajouter compétences et connecteurs en dernier

À mettre en place :

- créer un registre de compétences versionné et explicitement activable ;
- associer chaque compétence à des outils autorisés et à un scope ;
- demander consentement, permettre révocation et expiration ;
- commencer par un connecteur en lecture seule ;
- minimiser les champs synchronisés et enregistrer leur provenance ;
- faire passer toute écriture externe par proposition et exécution idempotente ;
- tester suppression, révocation, replay, expiration et isolation ;
- interdire qu’un document ou une compétence fournisse elle-même une permission.

## Contrôles de référence

Depuis `apps/api`, dans un environnement isolé :

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check app migrations tests
```

Depuis `apps/mobile`, avec Node et dépendances verrouillées disponibles :

```text
npm run typecheck
npm run lint
```

Ces contrôles lisent/vérifient le code et ne nécessitent pas de privilèges administrateur. Ils ne remplacent pas les migrations et tests de concurrence sur une **base PostgreSQL de test dédiée**, ni les essais réels des services et appareils. Ne pas exécuter de reset ou migration destructive sur la base personnelle. Les commandes d’intégration propres à chaque lot doivent être consignées avec leurs prérequis et leurs résultats, sans secrets.
