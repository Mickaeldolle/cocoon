# Audit de l'assistant Cocoon et cadre de mesure

Date de référence : 24 septembre 2026. Cet audit compare le code et les preuves locales à [PLAN.md](../PLAN.md), [TASKS.md](../TASKS.md) et [VISION.md](../VISION.md). Il ne certifie ni une bêta sur appareil ni une exploitation en production.

## 1. Situation actuelle

**Verdict : prototype fonctionnel avancé, mais efficacité réelle inconnue.** L'assistant a une conversation personnelle avec streaming, une mémoire structurée confirmée par l'utilisateur, quelques lectures métier bornées et des propositions exécutées après confirmation. Il n'a pas encore démontré une aide fiable dans la durée sur les 60 scénarios, plusieurs comptes et des téléphones réels. Son « intelligence » perçue dépend aujourd'hui largement de la réponse du LLM local et de la pertinence du petit contexte fourni ; aucun score utilisateur n'est mesuré.

Échelle de maturité utilisée ci-dessous : **0** absent ; **1** présent dans le code ; **2** validé localement ; **3** validé avec les services, la base et les appareils visés ; **4** confirmé par l'usage longitudinal. Cette échelle décrit la preuve, pas une mesure d'intelligence humaine.

| Capacité attendue | État constaté et preuve | Niveau | Écart principal |
| --- | --- | ---: | --- |
| Dialogue contextualisé | Fil personnel, dix tours récents dans le prompt, streaming et arrêt ; tests API et appel ponctuel à Ollama documentés en B04 | 2 | Résolution des références, ambiguïtés et choix d'outils non évaluée sur le corpus complet |
| Mémoire personnelle | Souvenirs confirmés, source, correction, oubli logique, filtres owner/scope/validité avant ranking ; tests B05 | 2 | Recherche lexicale sur les 100 plus récents ; pas de mesure de rappel à distance ni de provenance visible dans la réponse |
| Utilité concrète | Lectures bornées de tâches, agenda, projets et mémoires ; propositions puis confirmation ; workers capture et rappels | 2 | Taux de tâches réellement accomplies, temps gagné et erreurs d'exécution non mesurés en usage réel |
| Confiance et confidentialité | Autorisations côté API, isolation locale A/B/A, confirmation obligatoire, secret exclu du contexte | 2 | Concurrence PostgreSQL, téléphone, révocation et restauration à qualifier ensemble |
| Voix | Contrat API/STT antérieur ; parcours actif : maintien affiche « Transcription audio indisponible. » | 1 | Le fournisseur et les essais sur appareils manquent ; la voix demandée par PLAN n'est pas disponible |
| Rappels | Règles, outbox, leases, reçus et états de lecture présents ; tests locaux B07 | 2 | Push réel, double worker PostgreSQL et sortie réseau du conteneur non validés |
| Ressenti d'intelligence | Aucun dispositif de mesure ou de retour en situation | 0 | Il faut un protocole utilisateur et des critères de succès indépendants du choix de modèle |
| Déploiement | Compose, Caddy, migration unique, readiness, métriques et scripts de sauvegarde | 1-2 | Aucun déploiement/restart/restauration de bêta ni build signé installé |

Vérification du 24/09/2026 : **120 tests API réussis, 2 avertissements**, Ruff réussi, typecheck mobile réussi. Le lint mobile échoue avec **2 erreurs et 3 avertissements**, dont les 2 erreurs dans `use-secret-gesture.ts`. La copie Git a **zéro commit et zéro fichier suivi**. Ces résultats ne remplacent pas une qualification PostgreSQL complète, un test sur appareil ou une mesure avec plusieurs utilisateurs. Les validations datées par lot sont dans `docs/validation/B00.md` à `B08.md`.

### Écarts concrets qui diminuent le ressenti

1. `MemoryRepository.active_for_user` limite la sélection aux **100 mémoires actives les plus récentes**, puis `MemoryRetriever` classe ce sous-ensemble par mots communs. Une mémoire ancienne pertinente peut être invisible ; synonymes et reformulations sont peu couverts. Le `ContextBuilder` s'arrête lorsque la prochaine mémoire dépasse le budget de caractères au lieu d'essayer les suivantes.
2. Les réponses du chat reçoivent les **dix derniers tours**, jusqu'à **douze résumés mémoire** et quatre blocs de contexte personnel. Le prompt reçoit des résumés sans identifiants ou dates de source : il est difficile pour l'assistant de citer précisément « d'où il sait cela ».
3. Le registre d'outils est borné et sûr, mais le chat injecte systématiquement listes de tâches, événements à venir et projets ; il ne choisit pas encore une recherche ciblée selon la question. Une ancienne tâche ou un événement hors des listes bornées peut manquer.
4. `docs/validation/B00-scenarios.md` possède 60 cas, mais `test_scenario_corpus.py` vérifie surtout la structure du fichier et trois classifications déterministes. Le seuil de 90 % du PLAN n'a donc pas de score mesuré.
5. `UX-CONTRACT.md` décrit un accueil qui ouvre la conversation assistant avec la saisie ; `app/home.tsx` traite encore directement une capture via le flux neural. Cette divergence doit être décidée et corrigée avant de mesurer un parcours « universel » unique.
6. La voix reste volontairement désactivée dans le parcours actif, conformément à la décision consignée dans B06. Le seuil « texte et voix sur iOS/Android » de PLAN demeure donc ouvert.
7. La configuration Compose ne contient aucun service LLM ou STT et n'atteste pas que leur URL privée est joignable depuis l'API. Le worker de rappels n'est rattaché qu'au réseau Docker `internal: true`, alors qu'il doit appeler Expo Push sur Internet : valider puis corriger son chemin de sortie avant de compter sur les notifications.

## 2. Benchmark Cocoon indépendant du modèle

Le benchmark porte sur **l'issue du parcours utilisateur de bout en bout**, avec le modèle, la version du code, les données de départ et le matériel enregistrés pour rendre deux campagnes comparables. Il contient aussi une mesure déterministe du retrieval, qui peut être rejouée sans LLM. Une hausse liée au seul changement de modèle sera présentée séparément.

### Jeu d'essai et protocole

- Transformer les 60 lignes du corpus existant en scénarios exécutables : identité et consentements fictifs, état initial PostgreSQL, tours successifs, résultat attendu, effets interdits, source qui doit être retrouvée, latence et preuve capturée. Inclure dates/fuseaux, ambiguïté, contradiction, oubli, panne et comptes A/B/A.
- Ajouter au moins 20 scénarios de continuité sur D+1 et D+7 : fait confirmé, préférence modifiée, projet ancien, rappel réalisé, information oubliée. Prévoir un lot de plus de 100 souvenirs pour tester la borne actuelle. Garder des cas hors mémoire où la bonne réponse est « je ne sais pas ».
- Rejouer d'abord les assertions sans modèle : filtrage et **recall@5** du souvenir pertinent, absence de souvenir supprimé, état des propositions, idempotence, isolation. Rejouer ensuite le parcours complet avec le modèle figé et ses sorties conservées sans donnée personnelle réelle.
- Faire utiliser la bêta à **6 à 10 personnes consentantes** pendant deux semaines, sur leurs propres téléphones ; une tâche courte au premier jour et un retour sur les mêmes sujets plusieurs jours plus tard. Collecter le minimum nécessaire, sans corps de conversation dans la télémétrie. Noter les observations qualitatives séparément du score automatisé.

### Indice proposé sur 100

| Axe | Poids | Calcul observable |
| --- | ---: | --- |
| Mémoire utile | 35 | 15 points recall@5 des sources attendues ; 10 pour rappel correct après délai ; 10 pour correction/oubli sans résurrection |
| Utilité | 30 | 15 points tâches abouties avec état métier vérifié ; 10 temps/effort économisés déclarés ; 5 bonne clarification quand la demande est ambiguë |
| Ressenti d'intelligence | 20 | Après chaque tâche : « Cocoon a compris mon contexte », « m'a aidé sans me répéter », « m'a donné confiance » sur 1–7 ; moyenne normalisée de 0 à 100 et verbatims analysés |
| Fiabilité et confiance | 15 | 5 états exacts (proposé/exécuté/échoué) ; 5 récupération après panne ou double envoi ; 5 réponse honnête en l'absence d'information |

Calcul : score de chaque axe = points obtenus / points applicables × poids ; publier aussi chaque axe, le nombre de scénarios, la médiane et la dispersion par utilisateur. Aucun score global n'est publiable si une fuite intercompte, un accès secret non autorisé ou une mutation sans confirmation est observé ; ce sont des **portes de sécurité à 100 %**, et non des points compensables. Cibles initiales : au moins **90 %** des 60 scénarios fonctionnels de PLAN, **100 %** des assertions de sécurité/confirmation, recall@5 **≥ 85 %** sur le corpus personnel annoté, et ressenti **≥ 5/7** sur les trois questions. Ces deux dernières cibles sont des hypothèses à figer avant la première campagne, puis à réviser avec un motif explicite si le panel révèle une mauvaise calibration.

Comparer les versions par cohortes et cas identiques ; ne pas entraîner ou régler les règles sur le jeu tenu à l'écart. Signaler le taux de réponse des testeurs et l'incertitude d'un petit panel. Une amélioration du ressenti qui augmente les erreurs factuelles ou les effets involontaires est rejetée.

## 3. Améliorations proposées, dans l'ordre

| Priorité | Travail | Effet recherché et preuve de sortie |
| --- | --- | --- |
| P0, 1–2 jours | Instrumenter le corpus et figer un premier score ; ajouter un retour simple après réponse (« utile ? », motif facultatif) uniquement avec consentement | Baseline reproductible, aucun contenu privé dans les métriques, taux de réponses connu |
| P0, 2–4 jours | Lever la limite des 100 souvenirs via requête SQL filtrée et recherche textuelle bornée ; classer sur l'ensemble des candidats admissibles, gérer les synonymes simples et ne pas couper au premier item trop long | Recall@5 mesuré sur 10, 100 et 500 souvenirs, coût/latence observés, isolation inchangée |
| P0, 2–4 jours | Faire répondre à partir de sources métier identifiées : tâche, événement ou mémoire avec date/identifiant ; montrer une référence compréhensible, et demander une précision si plusieurs objets concordent | Moins de réponses inventées ; questions datées et « finalement » passent le corpus |
| P1, 2–3 jours | Unifier le parcours accueil/assistant selon PLAN et UX-CONTRACT ; conserver les statuts honnêtes et une action de reprise claire | Test utilisateur : une pensée unique atteint la bonne réponse/proposition, sans changement de catégorie |
| P1, 2–4 jours | Mesurer attente, premier texte utile, résultat, confirmation et reprise ; améliorer les messages pendant le calcul et après échec, sans faux progrès | Latences p50/p95 et perception recueillies sur appareils, état réel compréhensible |
| P1, 3–5 jours | Qualifier PostgreSQL concurrent, notification externe, deux workers, backup/restauration ; corriger le lint du geste secret sans changer son contrat | Portes B01/B07/B08 vérifiées, aucune régression de confidentialité |
| P2 | Brancher STT privé seulement après choix du fournisseur et validation iOS/Android ; embeddings seulement si le retrieval mesuré plafonne | Voix réellement utilisable ou explicitement reportée ; gain vectoriel démontré contre SQL |

Les durées sont des tailles de travail indicatives, pas une promesse de livraison. Aucun changement de modèle ou ajout de connecteurs ne précède la mesure de la boucle mémoire/utilité. Les chemins B00 à B08 restent ceux de `TASKS.md` ; B09/B10 restent après bêta.

## 4. Décisions et validation de suite

1. Conserver FastAPI comme frontière de confiance et PostgreSQL comme source de vérité ; ne pas exposer les outils, secrets, conversations familiales/cachées ou données de santé au modèle.
2. Ajouter le benchmark à B00 et B08, puis utiliser son résultat pour ordonner B04/B05 plutôt que déclarer l'assistant « intelligent » sur la base d'une démo.
3. Fixer le parcours principal accueil/assistant lors du premier test utilisateur ; appliquer une seule règle dans `UX-CONTRACT.md` et le code.
4. Garder la bêta fermée tant que les six portes du PLAN ne sont pas prouvées, notamment appareil, voix si exigée, sécurité et restauration. La procédure et les options d'hébergement sont dans [deployment-options.md](deployment-options.md).
