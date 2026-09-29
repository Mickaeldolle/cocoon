# Builds mobiles de Cocoon

Ce dossier est la racine du projet Expo. Les commandes ci-dessous se lancent depuis
`apps/mobile`. Elles préparent un APK Android installable sans Google Play et un build
iOS pour simulateur sur EAS Build. Aucun profil de ce guide ne soumet l'application
à un store.

## Prérequis communs

1. Installer Node.js, puis exécuter `npm ci`.
2. Choisir des identifiants propres au projet dans `app.json` avant le premier build
   destiné à être conservé : `android.package` et `ios.bundleIdentifier` valent encore
   `com.example.cocoon`. Un changement de package Android crée une autre application
   au lieu de mettre à jour celle déjà installée.
3. Installer la CLI EAS, se connecter à son compte Expo et lier ce dépôt au bon projet.
   Si un projet Cocoon existe déjà sur Expo, le sélectionner au lieu d'en créer un second.

   ```powershell
   cd apps/mobile
   npm ci
   npm install --global eas-cli
   eas login
   eas whoami
   eas init
   ```

4. Vérifier que `app.json` contient alors `extra.eas.projectId`. Dans l'environnement
   EAS `preview`, définir l'URL HTTPS publique de FastAPI, sans `/api` final :

   ```powershell
   eas env:set --environment preview --name EXPO_PUBLIC_API_URL --value https://api.exemple.fr --visibility plaintext
   eas env:list --environment preview
   ```

   Remplacer l'adresse d'exemple par l'API réellement déployée. `localhost`, une adresse
   du réseau local et le `.env` de développement ne conviennent pas au build partagé.
   Les variables `EXPO_PUBLIC_*` sont lisibles dans l'application : aucun secret ne doit
   y être placé. Un changement d'URL nécessite un nouveau build.

5. Avant l'envoi des sources à EAS, lancer `npm run typecheck`, `npm run lint` et
   `npm test`. Ces contrôles ne remplacent pas un essai sur appareil.

## Android : APK installable

Le profil `preview` de `eas.json` contient `distribution: internal` et
`android.buildType: apk`. Il inclut le code JavaScript dans l'APK : Metro n'est pas
nécessaire une fois l'application installée.

```powershell
eas build --platform android --profile preview
```

Lors du premier build, laisser EAS créer la clé de signature si aucune clé n'existe.
Télécharger l'APK depuis le lien donné par EAS, puis l'ouvrir sur le téléphone Android
ou utiliser `adb install -r chemin\vers\cocoon.apk`. Conserver le même compte Expo,
le même `android.package` et la même clé pour les mises à jour. Le profil incrémente
le numéro de build Android dans EAS ; `expo.version` reste la version visible à
modifier lors d'une nouvelle version fonctionnelle.

Après installation, tester sur Wi-Fi puis sur données mobiles : connexion, chat,
réouverture de session et changement de compte. Les notifications push exigent encore
leur configuration Firebase/FCM et un test réel ; la présence de `expo-notifications`
ne suffit pas.

## iOS : ce que permet un compte Apple gratuit

Le profil `ios-simulator` construit dans le cloud Expo **sans abonnement Apple
Developer** :

```powershell
eas build --platform ios --profile ios-simulator
```

Le résultat est une application pour **simulateur iOS uniquement**. Elle ne peut pas
être installée sur un iPhone. Depuis Windows, ce build ne fournit pas non plus un
simulateur local ; il faut un Mac ou un service de simulateur distant pour l'exécuter.

Pour utiliser Cocoon sur un iPhone avec les comptes gratuits actuels :

- **Expo Go** : installer la version de l'App Store compatible avec Expo SDK 57,
  se connecter au même compte Expo sur l'iPhone et dans la CLI, puis lancer
  `npm run start:go` et ouvrir le QR code. Le serveur de développement doit rester
  accessible. Expo Go ne représente pas un build Cocoon autonome ; Face ID et les
  notifications push de Cocoon n'y sont pas qualifiés.
- **PWA** : ouvrir le site Cocoon publié en HTTPS dans Safari et l'ajouter à l'écran
  d'accueil. La PWA utilise les possibilités du navigateur, qui diffèrent de celles
  de l'application native.

Un compte Apple gratuit ne permet pas de signer avec EAS Cloud un fichier installable
sur un iPhone. Apple réserve la distribution ad hoc et TestFlight à l'Apple Developer
Program. La signature gratuite « Personal Team » existe dans Xcode sur un Mac, avec
des profils expirant après sept jours ; elle ne résout pas le besoin de build cloud
depuis Windows. Si un abonnement Apple Developer est souscrit plus tard, ajouter un
profil iOS `distribution: internal` et enregistrer l'iPhone, ou passer par TestFlight.

## Références

- [APK avec EAS Build](https://docs.expo.dev/build-reference/apk/)
- [Build iOS pour simulateur](https://docs.expo.dev/build-reference/simulators/)
- [Distribution interne iOS](https://docs.expo.dev/build/internal-distribution/)
- [Compte Apple gratuit et Xcode](https://developer.apple.com/help/account/basics/about-your-developer-account/)
- [Expo Go SDK 57 sur iPhone](https://expo.dev/changelog/expo-go-57-login)
