# Hermes dans Cocoon — moteur contrôlé, données personnelles dans Cocoon

Révision : 19 septembre 2026. Plan cible lié à [PLAN.md](PLAN.md), au [contrat de capture](CAPTURE_MODULE_PLAN.md) et aux lots B04/B05/B10 de [TASKS.md](TASKS.md).

**Statut au 8 octobre 2026 : plan historique.** Le prototype d'adaptateur a été retiré du code actif ; toute reprise doit repartir des contrats, permissions et tests décrits ici après vérification de la version Hermes visée. Le moteur conversationnel Cocoon actuel n'utilise pas Hermes.

## 1. Décision d’intégration

Réutiliser Hermes comme moteur d’exécution agent derrière FastAPI : sessions, boucle de lecture d’outils, clarification et compression du contexte. Cocoon garde comptes, droits, mémoire confirmée, propositions, effets métier et calendrier d’exécution. Ollama reste le fournisseur local de dialogue ; ce n’est pas un concurrent de Hermes, qui l’orchestre.

Pas de fork général de Hermes ni d’installation de son catalogue entier. Épingler une révision compatible, isoler l’intégration dans un adaptateur et un pont d’outils Cocoon. Conserver les notices MIT présentes dans `hermes-agent/LICENSE`. La copie fournie est la référence étudiée, pas une preuve qu’un serveur de même version tourne actuellement.

Le moteur local existant reste sélectionnable explicitement pendant la transition, mais utilise les mêmes politiques et propositions. En bêta cible, Hermes doit réussir les tests d’intégration avant activation. Si ce lot échoue, le signaler ; ne pas déclarer une simple conversation locale équivalente à l’agent multi-outils.

## 2. Ce que Hermes apporte et ce que Cocoon doit construire

| Capacité observée dans la source fournie | Usage cible Cocoon | Limite / complément |
| --- | --- | --- |
| Soumission de tours et événements (`tui_gateway/methods_prompt.py`) | Boucle contextuelle et progression | Adapter les événements, persister l’état du run et les délais |
| Création/reprise de session (`tui_gateway/methods_session.py`) | Continuité personnelle | Vérifier association compte/profil/session et sérialiser les tours |
| Profils et catalogue (`tui_gateway/methods_profiles.py`) | Configuration isolée | Contrôler la configuration effective à chaque démarrage/reprise |
| Fournisseurs de mémoire (`agent/memory_provider.py`, `agent/memory_manager.py`) | Point d’extension éventuel | Cocoon reste l’autorité ; aucune seconde mémoire autonome incontrôlée |
| Outils/skills (`tools/skills_tool.py`, `skills/`) | Procédures utiles réutilisables | Catalogue fermé en bêta, permissions hors texte des skills |
| Planification (`cron/scheduler.py`, `cron/`) | Inspiration pour suivi/automations | Un seul scheduler métier : Cocoon ; pas de doublon Hermes cron / rappels SQL |
| Recherche d’historique (`hermes_state_search.py`) | Inspiration pour rappel de contexte | Historique Hermes et mémoire sémantique Cocoon sont distincts |
| Compression de contexte (modules sous `agent/`) | Sessions longues | Résumés sourcés, nettoyage après révocation/oubli et budget |

Hermes peut apprendre des procédures ; cela ne signifie pas réentraîner les poids du modèle. Une compétence est une instruction versionnée, distincte d’un souvenir personnel et d’un outil exécutable.

## 3. Prototype retiré et corrections requises si reprise

Un ancien prototype `apps/api/app/modules/assistant/hermes_gateway.py` couvrait profils opaques, sessions et lecture de `::ask` ; il a été retiré du runtime Cocoon après vérification de l'absence d'import et de configuration active. Cette liste décrit des contrats à redéfinir et à tester si l'intégration Hermes est reprise, pas une capacité actuellement disponible. La colonne historique `AssistantThread.hermes_session_id` et sa migration sont conservées tant que les données existantes n'ont pas été inventoriées.

Limites relevées dans l'ancien prototype :

- Catalogue fixé à `memory` et MCP vide : pas d’accès aux outils métier Cocoon.
- Les deltas sont accumulés avant retour ; pas de streaming jusqu’au mobile.
- `::ask` produit des chaînes de réponse suggérée, pas des propositions métier identifiées.
- Le provisionnement demande `mirror_credentials=True` ; remplacer par des credentials strictement nécessaires au runtime.
- Le client ne vérifie pas `result.ok` et chaque entrée `applied` de `profiles.configure`.
- Le chemin de reprise ne reconfigure pas le profil ; contrôler les droits effectifs et la dérive.
- L’erreur 4062 est tolérée comme profil existant alors qu’elle peut aussi signaler une entrée invalide ; vérifier l’existence et la configuration attendue.
- L’authentification peut placer le token dans l’URL WebSocket : protéger/redacter les logs et préférer un mécanisme d’en-tête/ticket si le protocole épinglé le permet.

Particularité de la source Hermes : une liste `enabled_toolsets` vide peut supprimer l’épinglage, et un serveur MCP inconnu peut être ignoré. Ne pas utiliser une liste vide comme preuve de refus de tous les outils. Vérifier catalogue effectivement exposé avec la version retenue et échouer fermé si inattendu.

## 4. Frontière de confiance

```text
Utilisateur authentifié → Cocoon RunService → adaptateur Hermes
                                             ↓
                                   profil/session du compte
                                             ↓
                                    MCP cocoon-personal
                                             ↓
                 API interne : identité du run + droits + schémas
                                             ↓
                         services de lecture / proposition
```

Le nom `cocoon-{UUID}` est un repère de stockage ; il ne suffit pas à autoriser un accès. Pour chaque run, Cocoon délivre un jeton de service court signé, lié à `sub`, `run_id`, profil, audience et outils autorisés. Il n’est accessible ni au modèle dans son contexte ni au mobile. Le pont transmet cette identité ; l’API vérifie expiration, run actif, correspondance serveur et consentements actuels. `user_id` ne figure pas comme argument libre d’un outil.

Séparer credentials de provisionnement et credentials de tour. Pour un pont durable par profil, transmettre une capacité de run par canal de contrôle hors prompt ; ne pas changer un environnement global partagé entre utilisateurs. Interdire l’usage d’une capacité de A sur un run B.

La séparation des profils est logique, pas une sandbox OS. En bêta : processus non privilégié, volumes dédiés, absence de montages hôte sensibles, outils et egress fermés. Si des outils fichiers/code sont un jour autorisés, exiger des workers/sandboxes isolés par utilisateur avant leur activation.

## 5. Catalogue minimal d’outils

Les outils ci-dessous sont des contrats à implémenter, pas des outils actuellement branchés.

| Outil | Entrées principales | Sortie / effet |
| --- | --- | --- |
| `personal.search_memory` | texte, limite bornée | Faits actifs consentis, sources et versions |
| `personal.list_tasks` | période, statut, pagination | Tâches et rappels personnels |
| `personal.list_events` | intervalle borné | Agenda interne et plages occupées |
| `personal.list_groceries` | identifiant de liste autorisée | Articles existants |
| `personal.get_object` | type et identifiant | Objet du compte et version, sinon absence |
| `personal.propose_actions` | actions validées, références et versions | Proposition persistée, aucun effet métier |

Actions typées de départ : créer/modifier/terminer une tâche, conserver/corriger/supprimer une note ou préférence, créer/modifier/annuler un événement ou rappel, ajouter/modifier un article. Une modification d’objet sélectionne une référence réelle ; aucun identifiant inventé n’est accepté.

Chaque outil définit : nom/version, schémas Pydantic, permission, classification lecture/proposition, timeout, nombre de résultats, coût et audit minimal. Refuser propriétés inconnues et tailles excessives. Une proposition est validée côté serveur même si Hermes déclare ses arguments corrects.

Aucun outil `confirm` accessible au LLM. Seul le client utilisateur authentifié confirme l’objet affiché. Aucun accès famille/messagerie, shell, fichiers arbitraires, navigateur, réseau générique, installation de plugin ou nouveaux MCP. Une source non consentie produit un refus explicite, jamais un contournement par un autre outil.

## 6. Contrat du runtime et limites

Interface logique à développer : `run_turn(context, cancellation) -> événements typés`, `resume_session(binding)`, `cancel_run(run_id)`, `health()`. Implémentations `HermesRuntimeAdapter` et adaptateur local transitoire ; les endpoints ne contiennent pas les politiques métier.

Les événements doivent distinguer texte destiné à l’utilisateur, outil en cours, source, clarification, proposition, fin et erreur. Ne pas diffuser de raisonnement interne, arguments sensibles ou traces RPC. Une proposition visible vient du service Cocoon, pas du parsing d’une phrase libre. Garder `::ask` pour les réponses suggérées seulement.

Budgets initiaux proposés : 8 appels d’outils maximum par tour, 2 tentatives maximum d’inférence après erreur transitoire, 90 s par tour, résultats de lecture bornés, une exécution active par session. Fixer un budget de contexte adapté au modèle mesuré, garder une réserve de sortie et compresser avant saturation. Détecter une boucle répétant le même outil avec les mêmes arguments. Les quotas et délais ne peuvent pas être changés par un skill.

Interruption : propager au runtime, terminer le bail et conserver l’état sûr. Une connexion perdue n’autorise pas un second tour concurrent aveugle. Rejouer un tour peut répéter une lecture/proposition ; dédupliquer par run et clé logique. L’idempotence métier reste dans Cocoon.

## 7. Mémoire : une autorité, pas deux vérités

Cible : `memory_items` et services Cocoon comme mémoire durable de référence. Mémoire Hermes native en écriture autonome désactivée pour la bêta intégrée ; accès par `personal.search_memory` et `personal.propose_actions`. Si la version exige un provider, adapter `MemoryProvider` à ces mêmes services, sans stockage parallèle.

Distinguer : historique de session, résumé de travail, faits/préférences confirmés, données structurées (tâches/agenda), compétences. Une préférence proposée ne devient pas active avant confirmation ; les captures non confirmées restent seulement dans l’historique autorisé et selon rétention.

Migration : inventorier les mémoires locales/Hermes déjà présentes par compte, proposer leur import/validation, dédupliquer avec provenance. Ne pas les réimporter silencieusement comme consenties. Lors d’un oubli : supprimer/invalider mémoire, embeddings futurs, résumés et copies de session concernées ; redémarrer le contexte s’il contient encore la donnée. Tester qu’elle ne réapparaît pas à la prochaine session.

Consentements par source : tâches/rappels expliqués dans l’onboarding ; mémoire explicite via confirmation ; agenda et courses activés par choix utilisateur. L’activation autorise les lectures utiles, jamais les mutations automatiques. Révocation immédiatement appliquée même si les instructions Hermes sont mises en cache ; invalider la session si nécessaire.

## 8. Compétences après la bêta

Première étape : compétences déclaratives écrites et versionnées dans Cocoon, par exemple « préparer un dîner », « organiser ma semaine ». Elles composent le catalogue existant, sans code, URL arbitraire, secret ou permission nouvelle.

Ensuite Hermes peut proposer une compétence à partir d’un usage répété : brouillon lié au compte, provenance, version, outils requis, jeux d’essai, validation et activation explicite par l’utilisateur. Ceci remplace l’ancienne activation automatique des compétences jugées en lecture seule : le risque d’instruction persistante n’est pas couvert par une simple recherche de mots interdits.

La revue superadmin porte sur les capacités techniques génériques, pas sur une lecture implicite des données personnelles. Toute élévation de droits reste bloquée jusqu’à conception explicite. Pas d’auto-modification du code, installation de dépendances ou réentraînement en bêta.

## 9. Tests et intégration réelle

- Épingler révision Hermes, versions de modèles et dépendances ; exécuter des tests de contrat RPC sur cette révision.
- Deux profils temporaires réellement séparés : A → B → A, session reprise, redémarrage, concurrence et profil inexistant.
- Configuration partiellement appliquée, MCP inconnu et catalogue imprévu : refus de lancer le tour.
- Pont : identité expirée, profil/run incohérents, argument malveillant, source révoquée, objet d’un autre compte.
- Scénario réel : question → lecture agenda → proposition → clic mobile → création unique vérifiée → reprise de session.
- Mémoire : rappel sourcé, correction, oubli, absence de résurrection ; aucune donnée familiale dans les requêtes modèle.
- Streaming/cancel : deltas utiles, délai, coupure, erreur et reprise sans double exécution.
- Modèle local : qualité des appels d’outils français, hallucination d’arguments, ambiguïtés et budget sous charge.

Le lot B04 est terminé uniquement avec ces preuves réelles et les tests automatisés ; la présence de `hermes-agent/` ou d’un adaptateur simulé ne suffit pas.
