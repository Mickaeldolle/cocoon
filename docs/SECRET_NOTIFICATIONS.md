# Notifications discrètes des conversations protégées

Un message envoyé dans une conversation protégée démarre un délai de 10 minutes pour chaque destinataire accepté. Un autre message reçu pendant ce délai le redémarre. Si le destinataire ouvre la liste des conversations protégées ou une conversation avant l'échéance, l'alerte est annulée. Sinon, le worker envoie « Votre assistant a du nouveau pour vous. » sans nom, message, identifiant de conversation ni lien vers la zone protégée. Dans cette zone, le superutilisateur voit un point discret sur chaque conversation qui contient des messages non lus.

Le délai est conservé en base de données. Le worker existant `app.commands.run_reminder_worker` doit rester actif. Sa fréquence `WORKER_INTERVAL_SECONDS` s'ajoute au délai de 10 minutes (60 secondes par défaut).

## Activer les notifications web

1. Appliquer les migrations Alembic jusqu'à la révision `20261002_38`.
2. Depuis `apps/api`, exécuter `uv run python -m app.commands.generate_web_push_keys` une seule fois pour l'environnement concerné. Conserver la clé privée dans les secrets du serveur, jamais dans le code ou la configuration Expo.
3. Définir `WEB_PUSH_PUBLIC_KEY`, `WEB_PUSH_PRIVATE_KEY` et `WEB_PUSH_SUBJECT` (par exemple `mailto:adresse-de-contact@example.com`) sur l'API et le worker. Ils doivent utiliser la même paire de clés. Conserver cette paire lors des redéploiements, sinon les abonnements des navigateurs devront être renouvelés.
4. Servir l'application web en HTTPS, puis activer les notifications depuis l'écran « Rappels » du navigateur. L'utilisateur doit autoriser les notifications. Sur iPhone/iPad, le site doit être installé comme application web pour recevoir les notifications web.

Les applications iOS et Android continuent d'utiliser leur jeton Expo. Un compte sans abonnement push ne reçoit aucune alerte externe ; aucun contenu de conversation n'est exposé dans l'historique ordinaire des rappels.

## Test rapide sur le navigateur du PC, sans Docker

1. Dans `apps/api/.env`, conserver la paire VAPID existante et définir `WEB_PUSH_SUBJECT=mailto:adresse-de-contact-valide@example.com` avec votre véritable adresse de contact. Ne pas publier la clé privée. Redémarrer l'API après la modification.
2. Dans un second terminal ouvert dans `apps/api`, lancer `uv run python -m app.commands.run_reminder_worker` et le laisser actif.
3. Ouvrir Cocoon sur `http://localhost` ou en HTTPS, se connecter, puis aller dans « Rappels » et cliquer sur « Envoyer une notification test ». Accepter la demande de permission du navigateur. Le bouton enregistre l'abonnement si nécessaire et crée une alerte générique pour ce navigateur ; le worker l'envoie à son prochain passage (60 secondes par défaut).

Si la notification reste « En attente », vérifier que le worker tourne. Si l'activation échoue, vérifier la permission du site dans le navigateur, la configuration VAPID et l'accès à `/sw.js`. Une adresse IP locale servie en HTTP n'est pas un contexte sécurisé pour Web Push ; utiliser `localhost` sur le même PC ou HTTPS.

## Site et API hébergés sur Vercel

Une Function Vercel ne garde pas le processus `run_reminder_worker` actif entre deux requêtes. Pour l'envoi automatique, Cocoon expose `POST /api/internal/notifications/run` sur **le projet API**. Ce point d'entrée reprend la file existante, traite au maximum trois notifications par appel et refuse toute requête sans le secret serveur `NOTIFICATION_WORKER_TOKEN` (au moins 32 caractères). Ne pas placer ce secret dans `EXPO_PUBLIC_*` ni dans le projet web Vercel.

1. Définir `WEB_PUSH_PUBLIC_KEY`, `WEB_PUSH_PRIVATE_KEY`, `WEB_PUSH_SUBJECT=mailto:...` et `NOTIFICATION_WORKER_TOKEN` dans les variables **Production du projet API Vercel**, puis redéployer l'API. Garder la paire VAPID déjà utilisée par les navigateurs.
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

La fréquence d'une minute est une cible de l'ordonnanceur, pas une garantie d'arrivée à la seconde. Tester depuis le site HTTPS avec « Envoyer une notification test » ; vérifier le statut dans « Rappels », la réponse HTTP dans `net._http_response` et les journaux de la Function API. Stopper le worker local pendant cet essai pour vérifier que l'envoi provient bien du déclenchement hébergé. Si le traitement dépasse régulièrement trois notifications par minute, ajuster la capacité après mesure et surveiller la file.

## Vérification

Envoyer plusieurs messages protégés à moins de 10 minutes d'intervalle : une seule notification doit arriver 10 minutes après le dernier message, au prochain passage du worker. Refaire l'essai en ouvrant la zone protégée avant l'échéance : aucune notification ne doit arriver. Vérifier sur un vrai navigateur HTTPS et un appareil installé ; les tests locaux simulent uniquement l'envoi aux fournisseurs.
