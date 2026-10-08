---
version: alpha
name: Cocoon
description: Messagerie personnelle calme, directe et lisible sur téléphone.
colors:
  dark-background: "#181A1F"
  dark-surface: "#24262D"
  dark-accent: "#6E7DEB"
  light-background: "#F4F4F2"
  light-surface: "#FFFFFF"
  light-accent: "#5968CE"
typography:
  body:
    fontFamily: "system"
  symbols:
    fontFamily: "MaterialSymbols_400Regular"
rounded:
  card: "16px"
  input: "12px"
  message: "18px"
spacing:
  screen: "24px"
  content: "16px"
  compact: "8px"
components:
  message: {}
  composer: {}
  button: {}
---

# Cocoon : repères de design

## Direction

La conversation doit évoquer un carnet de messages personnel : le contenu reste au premier plan, les actions sont proches du pouce et les états d'envoi sont discrets mais explicites. Les thèmes clair et sombre conservent la palette indigo déjà définie dans `apps/mobile/src/theme.ts`.

## Source des couleurs et des dimensions

`apps/mobile/src/theme.ts` reste la source exécutable des couleurs, des espacements et des rayons communs. Les valeurs ci-dessus documentent les choix actuels. Les dimensions propres aux bulles et au compositeur de conversation vivent dans `apps/mobile/src/components/conversation-detail-styles.ts` ; celles du chat assistant vivent dans `apps/mobile/features/assistant/assistant-styles.ts` tant qu'elles n'ont pas été reprises ailleurs.

## Messagerie

- En-tête compact avec retour, initiale et nom de la discussion.
- Bulles alignées selon l'auteur, fond indigo pour l'envoi et fond neutre pour la réception. L'heure reste secondaire, la coche indique l'envoi ; l'avatar du destinataire apparaît à gauche de la bulle seulement après lecture.
- Message ajouté dès l'action d'envoi. Un échec conserve la bulle et propose « Réessayer ».
- Saisie basse, à une ligne au départ, qui suit le clavier et respecte la zone sûre.
- Sur l’accueil, la saisie reprend la capsule claire et le contour discret du compositeur. Dans une discussion cachée, la saisie reste sur une ligne et défile horizontalement pour un texte long.
- Un dégradé indigo très léger habille le fond de l’accueil et des écrans cachés sans réduire le contraste du contenu.
- L’accueil met en scène un orbe d’énergie violet et indigo entouré d’étoiles, sur les fonds clair et sombre existants. Le rendu neuronal dessine sa matière avec Skia : points ondulants sur une sphère, filaments courbes, jonctions et impulsions électriques douces. Les teintes du shader vivent dans `neural-orb-shader.ts` ; les étoiles utilisent `assistantVisual` dans le thème. Le titre et les actions restent sobres, en typographie système.
- Le composant partagé `AssistantOrb` conserve la dérive lente au repos. Pendant une réponse, ses filaments s'éclairent, les étoiles autour de la sphère se déplacent davantage et la vitesse augmente progressivement, sans redémarrer le mouvement. Il reste compact dans l’en-tête de la conversation. Le mouvement se suspend hors écran, en arrière-plan et lorsque la réduction des animations est activée. Le temps du shader est mis à jour sur le moteur d’animation ; aucun point ne déclenche une mise à jour React par image.
- Le rendu neuronal est le seul design d’orbe. `OrbScene` conserve son halo, ses étoiles et sa dérive ; l’ancienne image et le sélecteur de design sont supprimés. Pendant le chargement ou si le moteur graphique échoue, un emplacement vide préserve la mise en page et l’accès à l’assistant. Le moteur web est servi localement (`canvaskit.wasm`), généré depuis la dépendance verrouillée lors de l’installation et du build, sans CDN.
- Sur l’accueil, la saisie à une ligne reste ancrée en bas, hors du contenu défilant, et suit le clavier comme dans la messagerie. « Voir la conversation » donne accès à l’assistant sans envoyer de message. La section « Ce qui mérite votre attention » et l’ancien texte d’introduction sont retirés.
- Lors d’un envoi depuis l’accueil, l’orbe s’active et le statut indique « Votre assistant prépare sa réponse… ». L’accueil reste affiché jusqu’à la réponse complète, puis la conversation présente l’échange sans le renvoyer. Pendant cette attente, l’action d’envoi devient un arrêt ; une erreur ou une annulation conserve le brouillon. L’accès « Voir la conversation » attend la fin de cet envoi.
- Le signal « écrit un message » reflète une activité récente ; il disparaît automatiquement s'il n'est plus renouvelé. Dans les discussions cachées, il est récupéré par une requête protégée et temporaire.
- Le compositeur n'affiche qu'une action : micro lorsque le champ est vide, envoi lorsque du texte est saisi. Maintenir le micro lance l'enregistrement, le relâcher le termine. Le brouillon local peut être écouté ou supprimé ; l'interface indique clairement que son envoi n'est pas encore disponible.
- Après déverrouillage, ouvrir une discussion acceptée directement. Une invitation en attente garde la liste visible ; son acceptation ouvre la discussion. Seul le superutilisateur peut créer une discussion cachée, avec contrôle côté API.
- Dans l’APK Android, le premier accès caché demande le mot de passe et active la biométrie forte de l’appareil si elle est disponible. Les accès suivants ouvrent directement la vérification biométrique ; une annulation ou indisponibilité laisse le mot de passe utilisable.
- Dans Expo Go en développement, le geste déclenche aussi directement la biométrie locale lorsque l’API de développement l’autorise ; le mot de passe reste accessible si le simulateur ne dispose pas de biométrie ou si la vérification échoue.
- Depuis une discussion cachée, le retour du superutilisateur mène à la liste. Pour les autres membres, il reverrouille l’accès et mène à l’accueil.
- Le compositeur flotte sur un fond transparent avec un espace visible au-dessus du clavier et du bord inférieur.

## Règles d'usage

Dans l'assistant, le choix d'un modèle gratuit OpenRouter est un contrôle secondaire
compact sous l'en-tête. La liste se charge depuis l'API et affiche un état de
chargement ou une action de reprise en cas d'erreur. Le message et son envoi
restent le centre de l'écran ; le modèle choisi s'applique aux nouveaux messages.

Les libellés sont en français et décrivent une action ou un état réel. Les icônes seules portent un nom accessible. Le thème sombre conserve un contraste suffisant sur les bulles indigo. Les discussions cachées utilisent le même affichage, mais leur accès reste conditionné à la session secrète. Leur indicateur de saisie ne passe jamais par le canal temps réel des conversations visibles ; l'accusé de lecture n'est visible qu'aux membres acceptés après déverrouillage.
