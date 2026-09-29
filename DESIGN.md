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

`apps/mobile/src/theme.ts` reste la source exécutable des couleurs, des espacements et des rayons communs. Les valeurs ci-dessus documentent les choix actuels. Les dimensions propres aux bulles et au compositeur vivent dans l'écran de conversation tant qu'elles n'ont pas été reprises ailleurs.

## Messagerie

- En-tête compact avec retour, initiale et nom de la discussion.
- Bulles alignées selon l'auteur, fond indigo pour l'envoi et fond neutre pour la réception. L'heure reste secondaire, la coche indique l'envoi ; l'avatar du destinataire apparaît à gauche de la bulle seulement après lecture.
- Message ajouté dès l'action d'envoi. Un échec conserve la bulle et propose « Réessayer ».
- Saisie basse, à une ligne au départ, qui suit le clavier et respecte la zone sûre.
- Le signal « écrit un message » reflète une activité récente ; il disparaît automatiquement s'il n'est plus renouvelé. Dans les discussions cachées, il est récupéré par une requête protégée et temporaire.
- Le compositeur n'affiche qu'une action : micro lorsque le champ est vide, envoi lorsque du texte est saisi. Maintenir le micro lance l'enregistrement, le relâcher le termine. Le brouillon local peut être écouté ou supprimé ; l'interface indique clairement que son envoi n'est pas encore disponible.

## Règles d'usage

Les libellés sont en français et décrivent une action ou un état réel. Les icônes seules portent un nom accessible. Le thème sombre conserve un contraste suffisant sur les bulles indigo. Les discussions cachées utilisent le même affichage, mais leur accès reste conditionné à la session secrète. Leur indicateur de saisie ne passe jamais par le canal temps réel des conversations visibles ; l'accusé de lecture n'est visible qu'aux membres acceptés après déverrouillage.
