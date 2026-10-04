---
version: alpha
name: Cocoon
description: "Une application mobile privée, calme et technologique, pensée pour alléger la charge mentale."
colors:
  ink: "#F4F5F7"
  spruce: "#6E7DEB"
  moss: "#454A58"
  linen: "#181A1F"
  clay: "#B8C0FF"
  berry: "#FF758F"
  focus: "#C8CEFF"
  spruce-soft: "#292C3A"
  spruce-on: "#E4E7FF"
  moss-soft: "#22242B"
  linen-muted: "#1E2026"
  clay-soft: "#343749"
  clay-ink: "#D4D9FF"
  berry-soft: "#3D242D"
typography:
  sans:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
rounded:
  DEFAULT: "1rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.5rem"
spacing:
  screen-gutter: "1.5rem"
  content-gap: "1rem"
components:
  button: {}
  input: {}
  card: {}
---

# Cocoon Design System

## Overview

### Creative North Star

Un espace de pilotage personnel en graphite doux : des surfaces superposées, une lumière indigo mesurée et des signaux précis. L’interface doit inspirer le contrôle serein, sans noir cyberpunk ni effets néon décoratifs.

### Product context and register

- **Audience and primary job:** membres d’une même famille qui veulent partager et retrouver des nouvelles dans un espace privé.
- **Target market(s) and evidence:** marché francophone en premier lieu ; cette décision est fondée sur le plan et les libellés initiaux, pas sur une hypothèse géographique plus large.
- **Locale(s) and language policy:** français (`fr-FR`) par défaut ; le texte visible reste centralisé dans les fonctionnalités lorsqu’une internationalisation est ajoutée.
- **Usage scene:** téléphone personnel, souvent à une main, de façon détendue ou rapide ; densité faible à moyenne et cibles tactiles généreuses.
- **Register:** produit privé, rassurant et concret.
- **Memorable signature:** une ligne de signal indigo sur les surfaces utiles et des cartes très courtes, qui évoquent une intelligence discrète sans codes cyberpunk.
- **Restraint:** la connexion, les erreurs et toutes les surfaces pouvant conduire vers du contenu sensible restent particulièrement simples et explicites.
- **Anti-references:** pas de noir “cybersécurité”, de rouge d’alerte omniprésent, ni de codes visuels de messagerie secrète qui révéleraient des données privées.
- **Token ownership/runtime mapping:** ce fichier est la source de vérité de l’intention ; `apps/mobile/src/theme.ts` est l’adaptateur de tokens React Native.

## Colors

`linen` est un graphite adouci de fond, `white` les surfaces légèrement relevées et `ink` le texte. `spruce` porte l’action indigo, tandis que `berry` reste réservé aux erreurs. Les teintes `*-soft` créent de la profondeur sans brillance. Les contrastes doivent rester conformes à WCAG 2.2 AA. `apps/mobile/src/theme.ts` expose les équivalents clairs ; le choix est mémorisé localement par l’appareil.

## Typography

La police système assure une lecture fiable sur iOS et Android. Les titres utilisent un poids semibold, le corps un poids regular avec une hauteur de ligne aérée. Les phrases sont en casse normale ; aucun texte n’est entièrement en majuscules pour transmettre une alerte.

## Layout

Les écrans ont une marge horizontale de 24 px, des cibles tactiles d’au moins 44 px et respectent les safe areas. Le dashboard commence par des cartes de synthèse : chacune porte une catégorie, un signal, une priorité et une action. Les listes détaillées restent masquées jusqu’à ce que la personne ouvre la catégorie. Les états chargement, erreur et vide conservent la même largeur de contenu afin d’éviter les sauts visuels.

## Elevation & Depth

La hiérarchie vient d’abord de la tonalité et de fines bordures vert-gris. Une ombre discrète est autorisée pour les boutons principaux et les surfaces transitoires, jamais pour suggérer un statut de sécurité.

## Shapes

Les contrôles gardent des angles souples (`sm` à `lg`), les séparateurs sont fins et les icônes sont toujours accompagnées d’un libellé lorsque leur sens n’est pas universel.

## Components

### Foundational visual states

Les boutons et champs possèdent des états normal, pressé, désactivé, occupé, erreur et focus perceptible. Les erreurs sont formulées clairement et à proximité de l’action de correction. Les indicateurs de chargement ne modifient pas la taille d’un bouton.

### Buttons and actions

`spruce` porte l’action principale, les actions secondaires utilisent une bordure, et les actions destructrices utilisent `berry` avec un libellé explicite. Une action occupée est désactivée pour empêcher le double envoi.

Le composeur de l’assistant reprend le bouton unique de la messagerie : appui court pour envoyer, maintien pour expliquer la disponibilité vocale, et arrêt pendant la génération. Le champ reste arrondi, compact et stable au-dessus du clavier.

### Forms and overlays

Les champs ont un libellé visible, une aide ou erreur textuelle et ne journalisent jamais les valeurs sensibles. Les futurs écrans d’authentification renforcée devront suivre le même langage visuel sans révéler l’existence d’un espace secret.

### Motion

Les transitions sont courtes et fonctionnelles ; la réduction des animations système doit être respectée lors de l’ajout d’animations.

## Do's and Don'ts

- **Do:** privilégier des libellés directs tels que « Se connecter » et « Créer mon compte ».
- **Do:** conserver le même vocabulaire et les mêmes états pour l’authentification sur tous les écrans.
- **Don't:** conserver en cache durable du contenu sensible dans le mobile.
- **Don't:** utiliser des ornements visuels pour signaler ou dévoiler la messagerie cachée.
