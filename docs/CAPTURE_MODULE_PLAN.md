# Capture universelle — contrat fonctionnel et technique

Révision : 19 septembre 2026. Spécification cible ; état réel dans [l’audit](docs/PROJECT_AUDIT.md), exécution dans [TASKS.md](TASKS.md). Le [plan directeur](PLAN.md) fixe le périmètre.

## 1. Une seule entrée, plusieurs résultats possibles

L’accueil présente un champ texte et un bouton micro à maintenir. Aucun choix préalable entre note, tâche, agenda et assistant. La réponse, la clarification et les actions apparaissent sous le champ, sans redirection obligatoire. Historique et gestion des données restent accessibles séparément ; aucun tableau de bord obligatoire dans l’état initial.

Après capture, le système peut : répondre, retrouver une information, poser une question courte, proposer une ou plusieurs actions, ou expliquer une indisponibilité. Ne pas forcer toute phrase dans « tâche / rappel / pensée ». Trois boutons visibles maximum par étape est une contrainte de lisibilité, pas une limite au catalogue métier.

Une réponse suggérée complète le dialogue ; elle ne confirme jamais implicitement une action. Un bouton « Créer le rappel mardi 22 septembre à 18 h » confirme exactement la proposition affichée. Une confirmation par message libre sera traitée ultérieurement ; en bêta, le bouton explicite reste l’autorité.

## 2. Parcours texte

1. Saisie conservée en mémoire locale tant que le serveur n’a pas accusé réception.
2. Envoi avec UUID client stable pour une même tentative logique. Capture brute enregistrée avant toute inférence.
3. Affichage honnête : « Enregistré », « En attente », « Recherche dans votre agenda » uniquement si cette étape s’exécute réellement.
4. Réponse progressive et sources ; pas de raisonnement interne ni de traces brutes d’outils.
5. Si ambigu : une question, réponse rattachée au même contexte et à un nouveau tour. Pas d’objet métier créé.
6. Si action : affichage du contenu exact, date locale/fuseau, ressources concernées et effets du lot.
7. Au clic de confirmation : création transactionnelle, statut réel, lien vers l’objet. En cas de conflit, nouvelle proposition à confirmer.

« Arrêter » demande l’annulation du run ; cela ne supprime ni capture ni résultat déjà commis. Fermer l’écran interrompt seulement l’observation ; le résultat reste récupérable. Les deux comportements doivent être distincts.

## 3. Voix par maintien du bouton

- Première utilisation : permission micro. Si refus, expliquer comment la réactiver et garder la saisie texte disponible.
- Appui : démarrer l’enregistrement après permission ; indicateur visuel, durée et état accessibles.
- Relâchement : arrêter. Geste d’annulation ou bouton Annuler : abandonner l’audio sans upload.
- Durée cible maximale 60 s, taille maximale 8 Mio ; limites client ET serveur, y compris lecture bornée du corps HTTP.
- Interruption système, appel téléphonique ou passage en arrière-plan : arrêter proprement et permettre de reprendre sans enregistrement caché.
- Transcription en français via STT privé, puis texte modifiable. L’utilisateur appuie sur Envoyer ; seule cette action déclenche le parcours de capture.
- Le texte envoyé a `source=voice`, même s’il a été corrigé ; conserver la provenance sans conserver l’audio brut.
- Nettoyer le fichier/cache audio après succès, annulation, erreur définitive et fermeture ; audio serveur en mémoire/temporaire borné, supprimé après traitement. Le service STT doit respecter la même politique.
- Transcription vide ou incertaine : ne rien envoyer automatiquement. Demander de corriger, surtout noms, nombres et dates.
- Alternative accessible au maintien : contrôle démarrer/arrêter pour les technologies d’assistance, sans changer le parcours principal.

`expo-audio` est déjà déclaré ; la présence d’une dépendance ne prouve pas ce parcours. Le STT reste distinct d’Ollama. La synthèse vocale, déjà envisagée, est facultative après la bêta.

## 4. États durables

| Objet | États cibles | Règle |
| --- | --- | --- |
| Audio mobile | idle, recording, transcribing, review, failed | Pas de capture avant envoi du texte revu |
| Run | queued, running, awaiting_input, awaiting_confirmation, completed, failed, cancelled | Les états finaux sont persistés, pas déduits de la connexion SSE |
| Proposition | pending, confirmed, cancelled, expired, superseded | Modification du contenu = nouvelle version/proposition |
| Job | pending, leased, succeeded, retryable_failed, dead | Bail expiré récupérable, tentatives bornées |

Un run en attente de précision finit son calcul. La réponse crée un nouveau run lié à `reply_to_run_id`, dans le même thread. Un run en attente de confirmation ne garde pas de connexion LLM ouverte. Un résultat persistant reste consultable après expiration du flux.

## 5. Contrats API cibles

Ces routes sont à implémenter, sauf mention « existant ». Ne pas les annoncer comme disponibles dans le README avant livraison.

| Route | Entrée / sortie | Usage |
| --- | --- | --- |
| `POST /api/assistant/voice/transcriptions` (existant) | Audio brut, type MIME → texte modifiable | Durcir tailles, formats réels et délais |
| `POST /api/captures` (existant à faire évoluer) | `{text, source, timezone, client_request_id, thread_id?, reply_to_run_id?}` → `{capture_id, run_id, status}` | 202 après persistance, sans attente LLM |
| `GET /api/assistant/runs/{id}` | Statut, réponse, sources, clarification, propositions, erreur sûre | Reprise et polling |
| `GET /api/assistant/runs/{id}/events?after={sequence}` | SSE authentifié | Événements incrémentaux persistés |
| `POST /api/assistant/runs/{id}/cancel` | Identifiant → état | Annulation idempotente du calcul |
| `POST /api/assistant/proposals/{id}/confirm` (existant à étendre) | `{expected_version}` → résultat et objets | Autorité transactionnelle unique |
| `POST /api/assistant/proposals/{id}/cancel` (existant) | Identifiant → état | Refuser une proposition |

Faire évoluer le POST captures avec version de contrat explicite ou nouvelle route transitoire : ne pas casser les anciens clients qui attendent un résultat synchrone. Les routes `/captures/stream`, `/assistant/chat`, `/assistant/turn` et `/neural-proposals/*` deviennent des façades du même service, puis sont dépréciées après migration du mobile. Pas de deux moteurs métier actifs derrière deux écrans.

Utiliser le client fetch authentifié pour SSE ; ne pas mettre le token dans l’URL. Chaque événement porte `run_id`, `sequence`, `type`, `created_at`, `payload`. Types autorisés : accepted, progress, text_delta, source, clarification, proposal, completed, failed, cancelled. Aucun événement brut de pensée du modèle. Le client déduplique les séquences ; l’API revérifie le propriétaire sur lecture/reconnexion.

Codes attendus : 401 session invalide, 404 objet absent/hors compte, 409 conflit de version ou clé réutilisée avec un autre contenu, 413 audio trop gros, 422 entrée invalide, 429 quota avec délai de réessai. Une panne moteur produit un run failed ou en attente bornée ; jamais une fausse réponse réussie.

## 6. Idempotence, concurrence et reprise

- Unicité `(user_id, client_request_id)` ; même contenu/clé retourne le run existant. Stocker une empreinte canonique pour détecter une réutilisation incorrecte.
- Une confirmation retourne le résultat déjà commis, même après timeout réseau. Une contrainte unique protège chaque exécution d’action.
- Verrouiller le parent commun d’un groupe d’alternatives avant les propositions, dans un ordre stable ; verrouiller seulement deux lignes alternatives distinctes ne suffit pas.
- Lot atomique : toutes les écritures SQL réussissent ensemble ou aucune. Plusieurs intentions indépendantes peuvent produire plusieurs propositions distinctes ; un lot ne mélange pas des choix incompatibles.
- Revalider état/versions/droits/conflits avant commit. Si le contexte a changé : 409, proposition remplacée, nouvelle confirmation.
- Ne jamais conserver une transaction SQL ouverte pendant LLM, STT ou réseau externe.
- Un job rejoué ne recrée pas la capture ni les effets. Reprise après crash : retrouver le résultat du provider local terminé si possible, sinon nouvelle tentative sans exécution métier automatique.
- Coupure SSE : le serveur poursuit ; le mobile recharge le run. Annulation demandée au serveur : interrompre le provider local, marquer la fin effective ; les actions déjà confirmées restent visibles.
- Hors ligne : garder le brouillon en mémoire et afficher non envoyé. Une file locale durable chiffrée est une évolution, pas une promesse de la bêta.

## 7. Temps, contexte et propositions

Le fuseau vient du compte et peut être précisé lors de la capture ; dates stockées en UTC avec fuseau et expression d’origine. Une échéance sans heure reste une date, pas un faux rendez-vous à 09 h. Heure manquante pour un rappel : demander ou afficher explicitement une valeur proposée avant confirmation. Ce point remplace l’ancienne convention implicite de 09 h.

Préserver les dates/actions explicites face au LLM, mais ne pas prétendre résoudre toute langue naturelle avec quelques expressions régulières. Détecter date passée, jour/date contradictoires, « vendredi prochain », changement d’année et heures ambiguës/inexistantes au changement d’heure. Demander une précision si nécessaire.

Pour récurrence : date/heure locale + fuseau + règle simple validée ; calculer les occurrences en heure locale, convertir chacune en UTC. Un rappel hebdomadaire à 20 h doit rester à 20 h après changement d’heure.

Contexte prioritaire : objet mentionné au tour précédent, objets actuels autorisés, faits confirmés pertinents, historique borné. La mémoire ne permet pas d’inventer un rendez-vous ; les données métier sont interrogées directement. Aucun accès à la famille ni aux salons cachés.

## 8. Validation de bout en bout

| Cas | Assertion attendue |
| --- | --- |
| Note / préférence | Capture durable, mémoire inactive avant confirmation, retrouvable après |
| Question personnelle | Réponse avec source existante, aucun effet métier |
| Rendez-vous daté | Date et heure justes, rappel séparé et explicite |
| Multi-intentions | Lot cohérent ou propositions indépendantes, pas d’annulation indue |
| « Décale-le » | Bonne référence ou clarification, revalidation au clic |
| Double clic / deux appareils | Une exécution, même résultat au rejeu |
| Deux alternatives simultanées | Une seule confirmée ; pas de double effet ni deadlock non géré |
| Coupure / redémarrage worker | Même capture et run récupérables, résultat consultable |
| Modèle invalide / indisponible | Capture conservée si commit réussi, erreur honnête, aucun effet |
| Échec DB initial | Ne pas afficher « capture conservée » ; garder la saisie |
| Voix refusée / vide / interrompue | Retour texte utilisable, pas d’enregistrement caché ni fichier oublié |
| Audio avec noms et dates | Texte corrigeable, pas d’action avant revue et confirmation |
| Compte B lit le run A | 404 et aucun événement/source divulgué |
| Révocation d’une source | Contexte invalidé, lecture et confirmation bloquées |

Tests de services et API déterministes, transactions sur PostgreSQL réel, tests du flux et des erreurs réseau, puis parcours sur appareils iOS/Android avec le provider local/Ollama/STT réels. L’ancienne émission de messages de progression avant analyse ne constitue pas une preuve de streaming réel.
