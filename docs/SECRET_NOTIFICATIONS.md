# Notifications discrètes des conversations protégées

Chaque nouveau message dans une conversation protégée déclenche immédiatement une tentative d'envoi à chaque destinataire accepté. L'alerte externe dit seulement « Votre assistant a du nouveau pour vous. » : aucun nom, message, identifiant de conversation ou lien vers la zone protégée n'est transmis. Dans cette zone, le superutilisateur voit un point discret sur chaque conversation qui contient des messages non lus.

Le message et son alerte générique sont enregistrés ensemble en base, puis l'API tente l'envoi avant de répondre. Un échec du fournisseur n'annule pas le message. Le statut de l'envoi reste en base ; les tentatives automatiques après un échec demandent le worker planifié. Les rappels personnels programmés et le briefing quotidien demandent toujours ce worker.

## Activer les notifications web

1. Appliquer les migrations Alembic jusqu'à la révision `20261002_38`.
2. Depuis `apps/api`, exécuter `uv run python -m app.commands.generate_web_push_keys` une seule fois pour l'environnement concerné. Conserver la clé privée dans les secrets du serveur, jamais dans le code ou la configuration Expo.
3. Définir `WEB_PUSH_PUBLIC_KEY`, `WEB_PUSH_PRIVATE_KEY` et `WEB_PUSH_SUBJECT` (par exemple `mailto:adresse-de-contact@example.com`) sur l'API. Conserver cette paire lors des redéploiements, sinon les abonnements des navigateurs devront être renouvelés.
4. Servir l'application web en HTTPS, puis activer les notifications depuis l'écran « Rappels » du navigateur. L'utilisateur doit autoriser les notifications. Sur iPhone/iPad, le site doit être installé comme application web pour recevoir les notifications web.

Les applications iOS et Android continuent d'utiliser leur jeton Expo. Le bouton « Envoyer une notification test » cible également l'appareil mobile courant. Un compte sans abonnement push ne reçoit aucune alerte externe ; aucun contenu de conversation n'est exposé dans l'historique ordinaire des rappels.

Pour Android, créer un build installé (Expo Go ne reçoit pas les push distants), configurer Firebase/FCM V1 pour le projet Expo, puis enregistrer le fichier `google-services.json` dans la configuration Android et la clé de service FCM V1 dans EAS Credentials. La clé de service reste secrète. Sans ces éléments, l'API peut accepter la demande d'envoi sans qu'une notification arrive sur le téléphone.

## Test rapide sur le navigateur du PC, sans Docker

1. Dans `apps/api/.env`, conserver la paire VAPID existante et définir `WEB_PUSH_SUBJECT=mailto:adresse-de-contact-valide@example.com` avec votre véritable adresse de contact. Ne pas publier la clé privée. Redémarrer l'API après la modification.
2. Ouvrir Cocoon sur `http://localhost` ou en HTTPS, se connecter, puis aller dans « Rappels » et cliquer sur « Envoyer une notification test ». Accepter la demande de permission du navigateur. Le bouton enregistre l'abonnement si nécessaire et tente immédiatement une alerte générique pour ce navigateur.

Si l'activation échoue, vérifier la permission du site dans le navigateur, la configuration VAPID et l'accès à `/sw.js`. Une adresse IP locale servie en HTTP n'est pas un contexte sécurisé pour Web Push ; utiliser `localhost` sur le même PC ou HTTPS. Le statut « Transmise » confirme l'acceptation par le fournisseur push, pas l'affichage sur l'appareil.

## Site et API hébergés sur Vercel

Les notifications de messages protégés et le bouton de test sont envoyés directement par l'API Vercel, sans cron ni `NOTIFICATION_WORKER_TOKEN`. Les rappels programmés, le briefing quotidien et les nouvelles tentatives après un échec ont toujours besoin d'un traitement périodique. Cocoon expose pour eux `POST /api/internal/notifications/run` sur **le projet API**. Ce point d'entrée traite au maximum trois notifications par appel et refuse toute requête sans le secret serveur `NOTIFICATION_WORKER_TOKEN` (au moins 32 caractères). Ne pas placer ce secret dans `EXPO_PUBLIC_*` ni dans le projet web Vercel.

1. Définir `WEB_PUSH_PUBLIC_KEY`, `WEB_PUSH_PRIVATE_KEY` et `WEB_PUSH_SUBJECT=mailto:...` dans les variables **Production du projet API Vercel**, puis redéployer l'API. Garder la paire VAPID déjà utilisée par les navigateurs. Si les rappels programmés ou les nouvelles tentatives sont souhaités, ajouter aussi `NOTIFICATION_WORKER_TOKEN`.
Si les rappels programmés ou les nouvelles tentatives sont nécessaires :

2. Dans Supabase, activer les extensions **pg_cron** et **pg_net**. Ajouter dans **Vault** deux secrets : `cocoon_api_url` contenant l'URL HTTPS du projet API Vercel sans `/` final, et `cocoon_worker_token` contenant exactement le même jeton que `NOTIFICATION_WORKER_TOKEN`.
3. Dans le SQL Editor Supabase, créer le déclenchement périodique suivant :

```sql
select cron.schedule(
  'cocoon-notifications',
  '* * * * *',
  $$
    select net.http_post(
      url := (select decrypted_secret from vault.decrypted_secrets where name = 'cocoon_api_url')
             || '/api/internal/notifications/run',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' ||
          (select decrypted_secret from vault.decrypted_secrets where name = 'cocoon_worker_token')
      ),
      body := '{}'::jsonb,
      timeout_milliseconds := 120000
    );
  $$
);
```

La fréquence d'une minute est une cible de l'ordonnanceur, pas une garantie d'arrivée à la seconde. Pour les messages protégés et le bouton de test, arrêter le worker local puis vérifier l'envoi immédiat depuis le site HTTPS. Pour les rappels programmés, vérifier la réponse HTTP dans `net._http_response` et les journaux de la Function API. Si le traitement dépasse régulièrement trois notifications par minute, ajuster la capacité après mesure et surveiller la file.

## Vérification

Envoyer un message protégé : l'alerte doit arriver sans attendre un cron. Réessayer la même requête avec le même `client_message_id` : aucune deuxième alerte ne doit être créée. Vérifier sur un vrai navigateur HTTPS et un appareil installé ; les tests locaux simulent uniquement l'envoi aux fournisseurs.
