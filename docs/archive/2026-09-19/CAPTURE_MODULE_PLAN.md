# Module de capture universelle — réponse progressive et choix confirmables

## Résumé

Transformer la zone de capture de l’accueil en un flux conversationnel compact : Cocoon reçoit la pensée, montre une progression lisible, diffuse une réponse courte, puis propose jusqu’à trois choix d’actions explicites. Un toucher crée immédiatement et une seule fois la ressource choisie.

Les libellés visibles décrivent l’avancement sans exposer de raisonnement interne du modèle : « Je comprends votre demande », « Je repère le temps », « Je prépare vos choix ».

## Changements clés

- Conserver la capture brute dès l’envoi, avec date, fuseau et provenance ; ne pas créer de tâche, rappel ni pensée structurée avant le choix de l’utilisateur.
- Unifier l’orchestration de capture : analyse temporelle déterministe d’abord, puis Gemma local pour une réponse courte et des propositions structurées validées côté serveur.
- Ajouter un flux SSE `POST /api/captures/stream` :
    - événements de progression sûrs ;
    - fragments de réponse utilisateur ;
    - événement final contenant la capture et les propositions ;
    - repli déterministe si Ollama est indisponible, sans bloquer la capture.
- Limiter chaque capture à trois propositions mutuellement exclusives :
    - `Créer une tâche` ;
    - `Créer une tâche avec rappel` ;
    - `Conserver comme pensée`.
- Une proposition peut être un lot atomique, par exemple tâche + rappel. Le choix crée immédiatement les ressources, marque les autres choix comme écartés et reste idempotent.
- Réutiliser `PersonalTask.reminder_at` : un rappel confirmé crée une tâche personnelle avec date/heure de rappel ; aucune ressource de rappel indépendante n’est ajoutée à cette étape.
- Une pensée confirmée crée une mémoire personnelle active reliée à la capture ; les captures non retenues restent traçables comme signal brut, sans devenir une mémoire active supposée.
- Faire évoluer la confirmation des propositions existantes pour valider strictement le type, le titre et les dates, puis exécuter la création dans une transaction.

## Accueil

- Après l’envoi, afficher sous la capture une carte temporaire stable avec état, réponse progressive et bouton « Arrêter ».
- À la fin du flux, remplacer cette carte par la réponse concise et les boutons d’action explicitement libellés, par exemple « Créer le rappel demain à 18 h ».
- Désactiver l’envoi concurrent, conserver le texte si une erreur survient et permettre une nouvelle tentative.
- Après création, afficher une confirmation brève et actualiser les trois signaux de l’accueil ; aucune proposition ne doit encombrer l’écran au-delà de cette interaction.
- Utiliser `expo/fetch` et son `ReadableStream`, compatible Expo Go sur mobile et web, pour lire le flux. [Documentation Expo](https://docs.expo.dev/versions/latest/sdk/expo/)

## Validation

- Capture claire : réponse diffusée, trois choix maximum, création immédiate et idempotente du choix sélectionné.
- Capture ambiguë : une unique question courte, sans création.
- Rappel : création d’une tâche avec `reminder_at`, puis traitement par le worker de rappels existant.
- Pensée : mémoire active créée uniquement après sélection.
- Ollama indisponible, réponse JSON invalide, annulation ou coupure réseau : capture brute conservée, interface récupérable, aucune action créée.
- Tests SSE avec modèle simulé, tests de validation et d’isolation par utilisateur, test réel Ollama, puis validation Expo Go sur Android/iOS.

## Hypothèses retenues

- L’expérience reste directement sur l’accueil, sans page assistant séparée.
- Le bouton d’action explicite vaut confirmation finale ; aucun écran de confirmation supplémentaire.
- La réponse diffusée est une formulation utilisateur courte ; Cocoon ne révèle jamais le raisonnement interne du modèle.
- Les conversations cachées, leurs métadonnées et leurs pièces jointes restent exclues du contexte transmis au modèle.
