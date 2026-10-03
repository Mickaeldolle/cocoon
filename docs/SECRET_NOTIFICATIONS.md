# Notifications discrètes des conversations protégées

Un message envoyé dans une conversation protégée démarre un délai de 10 minutes pour chaque destinataire accepté. Un autre message reçu pendant ce délai le redémarre. Si le destinataire ouvre la liste des conversations protégées ou une conversation avant l'échéance, l'alerte est annulée. Sinon, le worker envoie « Votre assistant a du nouveau pour vous. » sans nom, message, identifiant de conversation ni lien vers la zone protégée. Dans cette zone, le superutilisateur voit un point discret sur chaque conversation qui contient des messages non lus.

Le délai est conservé en base de données. Le worker existant `app.commands.run_reminder_worker` doit rester actif. Sa fréquence `WORKER_INTERVAL_SECONDS` s'ajoute au délai de 10 minutes (60 secondes par défaut).

## Activer les notifications web

1. Appliquer les migrations Alembic jusqu'à la révision `20261002_38`.
2. Depuis `apps/api`, exécuter `uv run python -m app.commands.generate_web_push_keys` une seule fois pour l'environnement concerné. Conserver la clé privée dans les secrets du serveur, jamais dans le code ou la configuration Expo.
3. Définir `WEB_PUSH_PUBLIC_KEY`, `WEB_PUSH_PRIVATE_KEY` et `WEB_PUSH_SUBJECT` (par exemple `mailto:adresse-de-contact@example.com`) sur l'API et le worker. Ils doivent utiliser la même paire de clés. Conserver cette paire lors des redéploiements, sinon les abonnements des navigateurs devront être renouvelés.
4. Servir l'application web en HTTPS, puis activer les notifications depuis l'écran « Rappels » du navigateur. L'utilisateur doit autoriser les notifications. Sur iPhone/iPad, le site doit être installé comme application web pour recevoir les notifications web.

Les applications iOS et Android continuent d'utiliser leur jeton Expo. Un compte sans abonnement push ne reçoit aucune alerte externe ; aucun contenu de conversation n'est exposé dans l'historique ordinaire des rappels.

## Vérification

Envoyer plusieurs messages protégés à moins de 10 minutes d'intervalle : une seule notification doit arriver 10 minutes après le dernier message, au prochain passage du worker. Refaire l'essai en ouvrant la zone protégée avant l'échéance : aucune notification ne doit arriver. Vérifier sur un vrai navigateur HTTPS et un appareil installé ; les tests locaux simulent uniquement l'envoi aux fournisseurs.
