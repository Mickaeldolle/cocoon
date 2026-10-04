# Contrat d’expérience — Cocoon

Ce document fixe les comportements partagés des flux mobiles actuels. Les règles de sécurité
et d’autorisation restent définies dans `PLAN.md` et appliquées par l’API.

## Navigation et accès

- La racine restaure la session puis redirige vers la connexion ou l’accueil. Quand le jeton de renouvellement est expiré ou révoqué, elle efface la session locale et ouvre la connexion. Un navigateur compatible propose directement la passkey ; le formulaire reste accessible si elle est absente ou annulée. Sur Android, la biométrie locale propose directement la reprise tant que le jeton de renouvellement est encore valide.
- L’accueil expose le profil via un bouton circulaire en haut à droite. Il ne contient pas de section « Rester en lien » ni de titre intermédiaire avant les cartes de fonctions.
- Après connexion, l’accueil est un filtre personnel : le champ principal ouvre désormais la conversation assistant et envoie directement le texte saisi ; les anciens signaux (`Maintenant`, `À vérifier`, `À confirmer`) restent des destinations secondaires tant que le pipeline de capture est conservé.
- Chaque signal explique en une phrase pourquoi il apparaît et indique sa source. La capture brute est personnelle, datée et conservée ; aucune action durable n’est créée sans confirmation.
- La liste des discussions s’affiche pleine largeur, sans titre ni texte d’introduction. Sa barre haute contient seulement le retour et une action circulaire `+` pour créer une discussion.
- Les priorités, courses, séances et mesures de profil sont privées et persistées pour le seul compte connecté. Les cochages attendent l’accusé de réception de l’API et restent lisibles en cas d’échec.
- Les éléments du tableau de bord utilisent les tags personnels `École`, `Travail`, `Courses` et `Famille`. L’utilisateur peut les suggérer ; le service peut les compléter à partir de la pensée. Une tâche ou un rappel confirmé est enregistré dans les priorités du compte.
- Chaque carte d’accueil reste volontairement concise : un seul libellé et une flèche. Les détails appartiennent à la page de destination.
- La zone « Déposer une pensée » ouvre l’assistant personnel avec la saisie intacte. Son historique est le seul propriétaire du défilement ; le composeur suit le même contrat que la messagerie et respecte la safe area basse. Chaque tour est historisé pour le seul compte connecté ; le modèle reçoit le fil récent, peut proposer jusqu’à trois suites et peut soumettre un fait durable comme souvenir à confirmer. Les actions métier restent dans leur parcours de proposition puis confirmation séparé.
- Le brief quotidien est facultatif, configuré avec l’heure et le fuseau de l’appareil. Les notifications de rappel et de brief ont un contenu générique ; elles ne révèlent jamais une conversation ni du contenu caché.
- L’accueil expose un accès explicite à « Rappels ». Cette inbox personnelle liste les échéances conservées par l’API, y compris lorsqu’un push n’a pas pu être livré ; elle distingue l’état fournisseur de la lecture utilisateur et permet de marquer un élément comme lu.
- Sans provider local configuré ou disponible, l’Assistant affiche une indisponibilité claire ; aucune réponse générique de remplacement n’est fabriquée et aucune bascule silencieuse n’a lieu. Le provider OpenAI-compatible reste derrière FastAPI. Aucun runtime externe, aucune conversation familiale ou cachée et aucune mesure de santé n’entre dans le contexte assistant.
- L’assistant utilise un bouton unique : appui court pour envoyer le texte, appui long pour signaler que la transcription audio est indisponible, et arrêt pendant la génération. Le texte saisi reste conservé en cas d’erreur.
- Le tableau de bord et l’assistant sont strictement personnels : ils ne doivent jamais récupérer, indexer, transmettre ni déduire l’existence de conversations cachées.
- La demande de menu envoie un instantané explicite des seuls ingrédients de la liste à l’API ; le menu proposé n’est pas sauvegardé et ne révèle aucune autre donnée du compte.
- La section santé enregistre les séances et mesures renseignées par la personne. Elle affiche seulement une cible de poids déclarative, ne fournit pas de conseil médical et n’envoie jamais les mesures au LLM.
- Le profil permet de modifier les informations personnelles de base, taille, poids actuel et cible. Les clés de fournisseurs IA sont uniquement configurées côté serveur et ne sont jamais renvoyées au mobile.
- Le profil donne accès aux projets personnels : création avec nom et description, consultation des projets du compte uniquement et changement explicite entre actif, pause et terminé. Les projets terminés restent consultables mais ne sont plus injectés dans le contexte assistant.
- Les écrans de détail reviennent toujours à leur liste parente.
- À l’ouverture d’une conversation, le composeur reçoit le focus pour ouvrir le clavier sans action supplémentaire ; il conserve les safe areas haute et basse.
- Une ressource privée indisponible est présentée comme introuvable, sans révéler son existence.

## États et retours

| Opération                      | Pendant l’action                          | Succès                              | Échec                                            |
| ------------------------------ | ----------------------------------------- | ----------------------------------- | ------------------------------------------------ |
| Créer un espace                | Bouton stable et désactivé                | Ouvre le nouvel espace              | Erreur dans le formulaire, saisie conservée      |
| Ajouter un membre              | Bouton stable et désactivé                | Saisie email vidée                  | Erreur dans le formulaire                        |
| Créer une conversation         | Bouton stable et désactivé                | Ouvre la conversation               | Erreur dans le formulaire                        |
| Envoyer un message             | Bouton stable et désactivé                | Saisie vidée, historique actualisé  | Erreur près du composeur                         |
| Envoyer à l’assistant          | Envoi désactivé, saisie visible           | Réponse, choix et mémoire historisés | Saisie conservée, indisponibilité près du composeur |
| Confirmer une proposition      | Deux actions désactivées                  | Donnée personnelle enregistrée      | Proposition et message restent visibles          |
| Configurer le brief            | Bouton stable et désactivé                | Heure et état enregistrés           | Valeurs conservées, aide près du bouton          |
| Proposer un menu               | Bouton désactivé, composition visible     | Menu contextualisé par la liste     | Liste conservée, erreur près du bouton           |
| Planifier une séance           | Action locale immédiate                   | Séance ajoutée à la progression     | Saisie du moment conservée, aide près du bouton  |
| Cocher une tâche/course/séance | Contrôle désactivé pendant la mise à jour | État enregistré et liste actualisée | État précédent conservé, erreur près de la liste |
| Enregistrer le profil          | Bouton stable et désactivé                | Profil et objectif actualisés       | Valeurs conservées, erreur près du formulaire    |

Toutes les mutations attendent la confirmation de l’API. Les listes conservent une zone de
chargement, un état vide et un message d’erreur explicite.

## Confidentialité et autorisations

- Le mobile ne filtre jamais les autorisations : l’API retourne uniquement les données visibles
  au membre connecté.
- Les salons dont l’adhésion est cachée ne sont ni listés ni ouverts par les routes standard.
- Depuis l’accueil ou la liste des discussions, trois glissements distincts et amples `→ → ↑`, réalisés en moins de trois secondes, ouvrent une vérification renforcée. Le détecteur natif n’intercepte que les directions attendues, afin de conserver le défilement vertical. Le geste ne constitue jamais une preuve : hors adaptateur biométrique de développement, le mot de passe du compte crée un jeton opaque, conservé seulement en mémoire, valable cinq minutes et lié à la session normale courante. Les routes `/api/secret/*` exigent simultanément le jeton normal et ce jeton secret.
- L’écran de vérification ne révèle aucune destination de messagerie. Chaque nouveau geste révoque d’abord une éventuelle session renforcée en mémoire. Les déplacements à l’intérieur de l’espace déjà ouvert ne redemandent pas de vérification ; un verrouillage explicite, le passage en arrière-plan, l’expiration ou la perte de session imposent une nouvelle vérification.
- En développement natif uniquement, Touch ID / empreinte Android peut associer une preuve aléatoire à la session déjà connectée, sans ressaisir le mot de passe. Cette preuve est isolée par compte et persiste dans le stockage chiffré de l’appareil afin d’imiter la persistance d’une passkey, puis la biométrie locale la libère pour demander un nouveau jeton renforcé au serveur. Ce n’est pas une passkey et n’est jamais activé en production.
- La vérification propose toujours le mot de passe du compte en alternative. Un appareil sans biométrie forte ou Face ID dans Expo Go affiche une explication et la saisie du mot de passe. Les erreurs natives ne sont plus masquées par un message générique ; les exigences serveur et le niveau biométrique fort restent inchangés.
- L’espace renforcé se verrouille explicitement, au passage de l’application en arrière-plan, à l’expiration du jeton ou à la perte de session. À chaque verrouillage, ses requêtes et son cache TanStack Query sont supprimés ; aucun contenu ou jeton secret n’est stocké durablement.
- Seuls `OWNER` et `ADMIN` voient le formulaire d’ajout de membre.
- Les tokens d’accès restent en mémoire ; seul le refresh token est stocké durablement.

## Accessibilité et langue

- Langue visible : français (`fr-FR`).
- L’apparence claire ou sombre est choisie depuis le profil, appliquée immédiatement et mémorisée sur l’appareil avant l’affichage des routes. Le mode sombre emploie un graphite doux, jamais un fond noir pur.
- Les actions utilisent des contrôles natifs React Native avec un libellé accessible.
- Les actions occupées empêchent le double envoi et gardent leur géométrie.
- Les cibles tactiles font au moins 44 px ; les erreurs sont textuelles et proches de l’action.

## Limites connues du MVP

- Les conversations sont actualisées toutes les huit secondes dans le mobile ; la reconnexion
  WebSocket sera la prochaine amélioration temps réel.
- Publications, médias et pièces jointes ne sont pas encore exposés. Les messages affichent désormais l’heure ; les accusés de lecture détaillés restent à exposer côté API.
- Sur le web, une passkey WebAuthn peut être créée depuis le profil après vérification du mot de passe du compte. Elle permet ensuite la connexion au compte depuis `/sign-in` sans saisir d’adresse email et le déverrouillage séparé de l’espace protégé. Chaque opération vérifie côté API un défi à usage unique, l’origine, le domaine, la signature, le compte lié à la passkey et la validation de l’utilisateur. Le déverrouillage protégé émet un jeton distinct de cinq minutes. Le mot de passe reste disponible. La passkey WebAuthn native nécessite encore un pont Expo ; une biométrie locale seule ne constitue jamais une preuve serveur.
