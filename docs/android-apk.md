# Construire et installer Cocoon sur Android avec un APK

État au 24 septembre 2026. Cette procédure produit une application installable **sans Google Play**. Aucun APK signé n'a encore été construit ou installé sur un téléphone dans cette copie. Le profil `preview` d'`apps/mobile/eas.json` est prévu pour un APK autonome ; le profil `development` produit un client de développement qui nécessite Metro et ne convient pas à une distribution simple.

## Préparer le build

1. Installer Node.js et utiliser `npm ci` dans `apps/mobile`. Installer l'[EAS CLI](https://docs.expo.dev/build/setup/) et se connecter au compte Expo :

   ```powershell
   cd apps/mobile
   npm ci
   npm install --global eas-cli
   eas login
   eas build:configure
   ```

   `eas build:configure` rattache le projet à Expo et renseigne son identifiant EAS ; vérifier que le nouvel `extra.eas.projectId` figure dans la configuration. Le fichier `app.json` contient actuellement `android.package = com.example.cocoon` : choisir **avant la première signature** un identifiant Android stable et propre au projet (par exemple un domaine que vous contrôlez en ordre inverse). Un changement ultérieur de package installe une autre application et ne met pas à jour l'ancienne.

2. Déployer et vérifier d'abord l'API HTTPS. Configurer dans l'[environnement EAS `preview`](https://docs.expo.dev/eas/environment-variables/manage/) la seule URL publique de l'API, par exemple :

   ```powershell
   eas env:set --environment preview --name EXPO_PUBLIC_API_URL --value https://<api>.vercel.app --visibility plaintext
   eas env:list --environment preview
   ```

   Remplacer `<api>` par le vrai nom. Pas de slash final, de `localhost`, d'adresse privée ni de secret. Expo [intègre `EXPO_PUBLIC_*` au bundle](https://docs.expo.dev/eas/environment-variables/usage/) : corriger l'URL nécessite un nouveau build de l'APK. Pour le site web sur Vercel, définir la même variable **séparément** dans les réglages du projet web.

3. Lancer `npm run typecheck` et `npm run lint`. À la date de l'audit, le typecheck passe mais le lint échoue avec deux erreurs et trois avertissements ; corriger ces erreurs avant de qualifier la version. Vérifier dans `app.json` les permissions micro et notifications souhaitées pour ce prototype.

## Construire et conserver la signature

Depuis `apps/mobile` :

```powershell
eas build --platform android --profile preview
```

Le profil `preview` combine `distribution: internal` et `android.buildType: apk`, conformément à la [procédure APK Expo](https://docs.expo.dev/build-reference/apk/). Le build EAS Free passe dans une file de priorité basse et utilise le quota gratuit actuel (voir [tarifs Expo](https://expo.dev/pricing)). Au premier build, laisser EAS générer une clé de signature si aucune clé existante n'est utilisée ; **conserver l'accès au compte Expo et à cette clé**. Pour les mises à jour, garder le même `android.package` et la même clé, puis augmenter `expo.version`/`android.versionCode` avant la nouvelle livraison. Une signature différente empêche la mise à jour sur les appareils déjà installés.

À la fin, télécharger le `.apk` depuis le lien de build EAS et le conserver dans un emplacement privé avec le numéro de version et la révision Git. Ne publier ni keystore, ni jeton, ni APK de test contenant des accès dans le dépôt.

## Installer sur le téléphone

### Installation directe

1. Transférer le fichier `.apk` par un canal privé sur le téléphone Android.
2. Ouvrir le fichier ; autoriser ponctuellement l'installation d'applications de cette source lorsque Android le demande, puis confirmer. Désactiver cette autorisation si elle n'est plus utile.
3. Ouvrir Cocoon. Vérifier l'écran de connexion puis un aller-retour API. Si l'application cherche `localhost` ou une adresse LAN, l'URL du build était incorrecte : reconstruire l'APK.

### Installation par câble USB

Activer les options développeur et le débogage USB sur le téléphone, installer Android Platform Tools sur le PC, autoriser la clé de débogage sur le téléphone, puis exécuter :

```powershell
adb devices
adb install -r C:\chemin\vers\cocoon-preview.apk
```

`adb devices` doit montrer l'appareil comme `device`. `-r` remplace l'application installée en conservant ses données si package et signature correspondent. Si Android affiche `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, vérifier la signature et le package **avant** de désinstaller : une désinstallation peut effacer les données locales et le refresh token. N'utiliser `adb uninstall` qu'après sauvegarde/consentement de l'utilisateur. Le [guide Expo](https://docs.expo.dev/build-reference/apk/) confirme l'installation par `adb install`.

## Tests à effectuer sur l'APK installé

- Sur Wi-Fi puis données mobiles : connexion, renouvellement de session après fermeture/réouverture, chat texte, historique/mémoire, compte A puis B puis A et séparation des données.
- Coupure réseau, API froide ou indisponible, base Supabase en pause et quota ZeroGPU épuisé : vérifier les messages d'erreur et l'absence de double envoi. Les demandes peuvent prendre du temps en file ZeroGPU.
- Une mise à jour signée : installer un second APK par-dessus le premier, vérifier que la session et les données restent cohérentes. En cas de migration, vérifier la compatibilité avant rollback.
- Notifications : le code demande un `extra.eas.projectId` et des identifiants [FCM v1 configurés dans EAS](https://docs.expo.dev/push-notifications/fcm-credentials/). Le simple APK ne garantit aucun push ; le worker de rappels n'est pas hébergé sur Vercel Hobby. Ne pas annoncer les notifications comme fonctionnelles sans envoi/réception réels.

## Problèmes fréquents

| Symptôme | Vérification |
| --- | --- |
| Build échoue immédiatement | `npm ci`, version Node/Expo, identifiant Android, compte EAS, variable `EXPO_PUBLIC_API_URL` |
| App installée mais écran d'erreur API | URL HTTPS embarquée, DNS/TLS, `/health/ready`, compte Supabase actif ; le CORS du navigateur ne s'applique pas à l'APK natif |
| L'ancienne app ne se met pas à jour | Même package, même clé de signature, `versionCode` augmenté |
| Notification impossible | `projectId`, permission Android, FCM v1, token Expo, worker actif et reçu de livraison ; plusieurs conditions manquent actuellement |

La distribution directe convient à un petit groupe de testeurs qui acceptent d'installer manuellement chaque nouvelle version. Elle n'assure pas les mises à jour automatiques du Play Store.
