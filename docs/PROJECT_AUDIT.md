# Audit de recadrage Cocoon — 19 septembre 2026

## Méthode et limites

Lecture des plans, du suivi, des modèles/routes/services API, du worker, de l’accueil et de la page assistant, du Compose et des tests. Hermes est conservé uniquement comme référence historique et n’est pas une dépendance du runtime MVP. Les constats ci-dessous portent sur les fichiers locaux, pas sur un déploiement supposé.

Validation exécutée depuis `apps/api` : `.\.venv\Scripts\pytest.exe -q` → **42 passed, 2 warnings, 34.95 s**. Avertissements de dépréciation Starlette/httpx et AnyIO. Les fixtures principales utilisent SQLite en mémoire (`tests/conftest.py`) ; les tests Hermes utilisent notamment un client simulé. Cette réussite ne démontre ni isolation concurrente PostgreSQL, ni RPC Hermes réel, ni STT/push/appareils. Aucune migration sur la base personnelle, aucun déploiement et aucun changement de code applicatif dans ce recadrage.

La commande `git status` ne trouve pas de dépôt Git à la racine de cette copie. Ne pas affirmer un commit ou un diff Git vérifié ; vérifier/restaurer la gestion de versions au lot B00 avant travaux applicatifs.

## Matrice état / écart / destination

| Domaine | Preuve locale | État observé et écart cible | Lot |
| --- | --- | --- | --- |
| Socle | `apps/api/pyproject.toml`, `apps/mobile/package.json`, migrations | Expo/FastAPI/SQLAlchemy/Alembic présents ; conserver | B00 |
| Authentification | `modules/auth/*`, tests auth | Sessions/appareils et tests de base ; invitations et durcissement bêta à valider | B01/B08 |
| Accueil | `apps/mobile/app/home.tsx` | Champ texte qui pousse vers `/assistant` ; signaux existants ; pas de maintien vocal dans cet écran | B03/B06 |
| Conversation | `app/assistant.tsx`, `assistant/router.py::create_chat_turn` | `/chat`, historique, choix textuels ; pas de proposition métier dans ce parcours | B02/B03/B04 |
| Capture | `neural/router.py::_capture` | Capture brute commise avant analyse ; trois capacités limitées, parcours distinct de `/chat` | B03 |
| Streaming | `neural/router.py::stream_capture` | Progrès et résultat final ; runs persistés et lisibles, mais pas encore de deltas LLM réels ni de reprise `Last-Event-ID` | B03/B04 |
| Erreur capture | Même route | Message « capture brute conservée » dans le catch global, même si l’échec a précédé son commit ; rendre l’accusé exact | B03 |
| Propositions | `NeuralProposal`, `AssistantProposal`, routes confirm | Deux modèles/chemins ; owner, verrouillage et expiration présents, service commun, clés d’idempotence et concurrence à consolider | B02 |
| Alternatives | `neural/router.py::confirm` | Verrou sur proposition puis annulation des sœurs ; concurrence entre alternatives distinctes à tester sur PostgreSQL | B02 |
| Mémoire locale | `assistant/kernel.py`, `create_chat_turn`, `neural/models.py` | Derniers 10 messages et 12 mémoires ; souvenirs extraits persistés automatiquement en mode local, mémoire active par défaut | B05 |
| Mémoire durable | `MemoryItem` | Origine et validité partiellement modélisées ; pas de recherche sémantique ni cycle complet correction/oubli/consentement | B05/B09 |
| Runtime LLM | `assistant/service.py`, `assistant/kernel.py`, `core/config.py` | Provider OpenAI-compatible côté serveur ; Ollama réel et abstraction provider complète restent à valider | B04 |
| Agenda/récurrences | `assistant/models.py`, schémas et routes | Objets et propositions déjà présents, conflits partiellement traités ; à relier au parcours unique | B02/B07 |
| Voix | `assistant/voice.py`, `/voice/transcriptions`, `expo-audio` | Adaptateur STT privé existant ; pas de maintien vocal branché dans les deux écrans inspectés ; moteur réel et nettoyage à prouver | B06 |
| Notifications | `run_reminder_worker.py`, `NotificationOutbox` | File persistée ; envoi jugé réussi sur statut HTTP sans tickets/reçus ; pas de suivi par appareil, retries bornés ni leases | B07 |
| Brief | Worker : comparaison exacte HH:MM | Une panne sur la minute attendue peut faire manquer le brief ; planifier une occurrence avec rattrapage | B07 |
| Infrastructure | `docker/compose.yml` | API et worker migrent tous deux au démarrage ; worker seulement sur réseau internal ; runtime LLM local/STT et paramètres bêta non assemblés | B08 |
| Push mobile | `apps/mobile/package.json`, `eas.json` | Configuration EAS présente, `expo-notifications` absent des dépendances déclarées ; distribution réelle non vérifiée | B07/B08 |
| Tests | Six fichiers de tests API, fixture SQLite | 42 réussites ; pas de preuve suffisante de transactions concurrentes PostgreSQL ni parcours matériel | Tous |
| Famille / secret | Domaines séparés, `TASKS.md` historique | Fondations à conserver ; capacités incomplètes à fermer dans la bêta assistant | B01/B08 |

## Contradictions supprimées dans les nouveaux plans

1. Ancien PLAN : famille/messagerie cachée au centre, assistant en phase 6. Nouveau : assistant au centre, surfaces familiales non essentielles différées.
2. Ancien plan capture : trois choix exclusifs quel que soit le texte. Nouveau : réponse, clarification, actions indépendantes ou lot selon le besoin.
3. L’idée d’un assistant à mémoire reste une référence produit ; aucun runtime Hermes n’est intégré. La mémoire métier et les compétences restent dans Cocoon, avec confirmation explicite.
4. Parcours local : écrit automatiquement des mémoires ; capture : attend confirmation. Cible unique : brut/historique conservés après envoi, mémoire structurée active après confirmation.
5. Deux stockages de propositions et plusieurs endpoints de dialogue. Cible : service commun et migration additive, façades temporaires.
6. Ancien « streaming » présenté largement ; code actuel : progression indicative et résultat final. Cible : événements réels et état durable, vérifiés sur téléphone.
7. Anciens souvenirs de développement : `/organize` persistait des tâches. Le code actuel le décrit comme endpoint de compatibilité sans persistance ; ne pas recycler ce constat obsolète.
8. Statuts `[x]` historiques : ils documentent des réalisations, pas une qualification bêta actuelle. Conservés en archive ; nouvelle roadmap mesure des résultats complets.

## Priorités techniques

P0 avant bêta : isolation/consentements, exécuteur commun, capture/run durable, pont d’outils sécurisé, mémoire contrôlée, voix réelle, rappels fiables, déploiement/restauration et builds validés.

P1 après bêta : embeddings et recherche hybride, compétences contrôlées, puis connecteurs. Une base vectorielle ne remplace ni les droits, ni le catalogue d’outils, ni le scheduler. Le changement de modèle seul ne résout pas ces écarts.

Ce diagnostic permet de conserver le socle et de concentrer le développement sur l’assemblage. Il ne constitue pas une attestation de production.

## Addendum — 21 septembre 2026

- La suite actuelle est à **39 tests réussis, 2 avertissements** ; Ruff et le typecheck mobile passent.
- Le runtime actif ne contient plus de branche Hermes ; les fichiers historiques Hermes ne sont pas appelés par l’application MVP.
- Les migrations `20260921_11` et `20260921_12` ajoutent l’expiration des propositions et les runs de capture.
- La messagerie secrète n’a pas été modifiée.
