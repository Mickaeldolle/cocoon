# Essai d’orbe neuronal — 6 octobre 2026

> Historique de l’essai initial : le rendu neuronal a ensuite été validé par l’utilisateur. L’ancien design, son image et le réglage de retour ont été supprimés. Les indications de retour et de secours classique ci-dessous décrivent uniquement l’état au moment de cet essai.

## Rendu

La matière de l’orbe est désormais dessinée par un shader Skia : grille de points projetée sur une sphère et déformée par plusieurs vagues indépendantes, filaments courbes croisés, jonctions et paquets lumineux qui suivent les connexions. Une transition de 500 ms augmente l’activité pendant une génération réelle. Les points ne deviennent pas des composants React individuels.

Le temps est alimenté par Reanimated et s’arrête hors écran, en arrière-plan, lorsque l’accès est désactivé ou en mode de réduction des animations. Le pas temporel est borné pour éviter un saut lors de la reprise. La sphère et les étoiles partagent l’agencement précédent ; le reste de l’accueil ne change pas.

## Retour au visuel précédent

Dans `apps/mobile/src/theme.ts`, remplacer `assistantVisual.style: 'neural'` par `'classic'`. Cela réactive `AssistantOrbClassic` avec le PNG initial conservé et les animations précédentes. Les deux écrans passent par le même composant. Ce réglage ne modifie aucun parcours ni aucune donnée.

Le composant classique sert aussi de secours pendant le chargement et en cas d’échec du moteur. Le chargement natif est différé et protégé pour conserver un accueil utilisable si un ancien client ne contient pas encore Skia.

## Installation et exploitation

- Skia 2.6.2 installé via Expo, avec le SDK 57 actuel.
- `npm install` / `npm ci` prépare le fichier CanvasKit local grâce au script `postinstall`.
- `npm run build:web` prépare à nouveau ce fichier avant l’export.
- `public/canvaskit.wasm` est généré depuis la dépendance verrouillée et ignoré par Git : il pèse environ 8 Mo non compressés. Aucun chargement depuis un CDN.
- Le nouveau moteur nécessite une reconstruction d’un client natif installé pour être effectivement utilisé. Aucun APK ni publication n’a été réalisé.

## Validation

- TypeScript, ESLint et formatage : succès.
- Export web de production : succès ; adresse d’API de démonstration temporaire uniquement pour l’export de test, aucun `.env` modifié.
- Suite mobile : 25 tests réussis.
- Audit UI strict : zéro constat (`home-orb-neural-premium-audit.json`).
- Navigateur réel : shader effectivement utilisé (canvas présent, PNG absent après chargement), thème sombre et clair, variante compacte en conversation, envoi initial, réponse simulée et arrêt de génération, accès désactivé avec rendu statique et champ en lecture seule. Pas d’erreur console observée.
- Les données et jetons du navigateur sont fictifs ; le serveur de démonstration est local et ne contacte pas le fournisseur LLM.

L’audit npm en ligne signale 37 entrées, contre 36 avant Skia. L’entrée supplémentaire de Skia est une propagation de l’alerte React Native déjà présente (`via: react-native`), pas une nouvelle faille propre au shader. Aucun downgrade incompatible ni `audit fix --force` appliqué. L’audit hors ligne ne constitue pas une vérification des vulnérabilités.

La fluidité, la consommation, le clavier et la réduction des animations doivent encore être qualifiés sur des appareils iOS/Android et en build de release. Le secours en cas de panne du moteur et les préférences de mouvement réduites restent à exercer explicitement sur appareil.
