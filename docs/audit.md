# Journal d'audit

L'API conserve des événements d'accès et d'action dans `audit_events`. Une connexion par mot de passe ou passkey, une inscription, un renouvellement et une déconnexion ont un nom d'action explicite. Les requêtes `POST`, `PUT`, `PATCH` et `DELETE` sur les autres routes API sont enregistrées avec leur méthode et leur **modèle de route**. Les lectures API sont aussi enregistrées, dont appareils, journal administrateur, mémoire, historique assistant et conversations. Les prévols CORS, événements de frappe, sondes de statut assistant et demandes de ticket temps réel ne sont pas enregistrés.

Chaque événement comporte l'heure UTC, l'identifiant du compte, de la session et de l'appareil quand l'authentification a réussi, l'identifiant de requête, l'action, le résultat, le code HTTP, la durée, la taille de réponse si connue, la plateforme et la famille de navigateur. Une tentative de connexion refusée reste sans compte identifié ; l'email tenté est corrélé par HMAC avec une séparation de domaine fondée sur `JWT_SECRET`, sans conserver l'email. L'IP est enregistrée seulement si elle est syntaxiquement valide. Sur Vercel (`VERCEL=1`), l'API utilise `x-vercel-forwarded-for`, fourni par la plateforme, et note `client_ip_source=vercel` ; un en-tête invalide fait revenir à l'IP du pair. Ailleurs, l'IP est celle du pair direct par défaut ; `X-Forwarded-For` n'est utilisé que si ce pair est dans `AUDIT_TRUSTED_PROXY_CIDRS`. Compose désactive la réécriture automatique des IP par Uvicorn pour que cette règle reste la source de vérité. L'adresse Caddy peut apparaître tant que son IP privée n'est pas configurée comme proxy de confiance ; vérifier le chemin réel du proxy dans chaque environnement avant d'utiliser cette IP pour une enquête.

`request_details`, `query_details` et `response_details` sont des objets JSONB dans PostgreSQL. Ils contiennent uniquement des champs sélectionnés : plateforme à l'inscription/connexion, version d'un consentement, longueur d'un message ordinaire ou d'un prompt, type de ressource créée, paramètres numériques `limit`/`offset`/`page`, type de réponse, classe d'erreur HTTP stable, et émission d'un jeton sans sa valeur. Les identifiants UUID présents dans les routes sont remplacés par des références HMAC corrélables ; aucune valeur brute de route protégée n'est conservée. Un HTTP 200 sur un flux signifie son acceptation, pas la réussite de toute la génération.

Aucun corps brut de requête ou de réponse, adresse email, mot de passe, jeton, contenu de message, prompt, réponse de l'assistant, en-tête libre ou paramètre d'URL non autorisé n'est stocké. Pour l'espace protégé, la route, les paramètres et les détails métier sont masqués ; les modifications portent le seul nom `secret.action`, les lectures `secret.read`, et les déverrouillages et verrouillages ont un nom dédié. Le code HTTP, la durée, l'IP et le type de réponse restent visibles.

Les références HMAC changent si `JWT_SECRET` change ; elles permettent de corréler les événements pendant la vie de cette clé, pas de retrouver la valeur originale. L'IP et ces métadonnées sont des données personnelles : informer les utilisateurs, restreindre la lecture et revoir la durée de conservation avant la mise en production. `AUDIT_TRUSTED_PROXY_CIDRS` doit viser seulement les adresses privées des proxys réellement contrôlés, jamais `0.0.0.0/0` ou `::/0`.

## Mise en service

Appliquer `uv run alembic upgrade head` depuis `apps/api` sur la base visée **avant** de déployer l'API modifiée. Vérifier ensuite `uv run alembic current`, qui doit indiquer `20261001_35`. Les tests locaux créent la table dans une base SQLite jetable ; ils ne qualifient pas une base PostgreSQL de production.

Un superadministrateur peut lire les événements avec `GET /api/admin/audit-events?limit=50`. Les filtres `actor_user_id=<UUID>` et `before=<UUID de l'ultime événement de la page>` permettent une lecture paginée. Les autres utilisateurs reçoivent `403`. Cette route renvoie uniquement les métadonnées ci-dessus : éviter de diffuser ses résultats hors de l'équipe d'exploitation.

Pour un premier tableau d'usage sans contenu personnel, une requête PostgreSQL agrège les actions réussies par jour et compte les comptes distincts :

```sql
SELECT date_trunc('day', occurred_at) AS jour, action,
       count(*) AS actions, count(DISTINCT actor_user_id) AS comptes
FROM audit_events
WHERE outcome = 'success'
  AND actor_user_id IS NOT NULL
  AND action NOT LIKE 'secret.%'
  AND COALESCE(request_details->>'ui_action', '') <> 'protected.press'
  AND occurred_at >= now() - interval '30 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

Cette requête reste un outil d'exploitation ; pour une interface de statistiques, exposer seulement ses agrégats et éviter les lignes individuelles.

Configurer `AUDIT_RETENTION_DAYS` (90 jours par défaut), puis exécuter quotidiennement `uv run python -m app.commands.prune_audit_events` depuis `apps/api`, avec la même configuration de base que l'API. La commande supprime les événements plus anciens que la durée configurée et affiche le nombre de lignes supprimées. Inclure cette table dans la politique de sauvegarde et limiter l'accès SQL aux rôles d'exploitation.

Les événements sont écrits dans une transaction distincte après le traitement de la requête. Une panne de base ou un arrêt brutal entre la modification métier et cette écriture peut donc laisser un événement manquant ; `cocoon.audit` émet `audit_write_failed` pour l'alerte d'exploitation. Si une traçabilité sans lacune est exigée, déplacer les événements critiques dans les mêmes transactions métier avant de s'appuyer sur ce journal comme preuve exhaustive. Le journal ne couvre pas encore les actions des workers ni les messages WebSocket.

## Appuis sur les boutons

Les boutons `Pressable` de l'application envoient `POST /api/audit/button-press` au moment de l'appui. L'API exige la session normale, accepte seulement une liste fermée d'identifiants d'action, puis écrit `ui.button.press` dans `audit_events`. L'identifiant stable apparaît dans `request_details.ui_action` : par exemple `home.profile.open` pour le bouton Profil. La ligne comporte les mêmes métadonnées de compte, session, appareil, IP, heure et code HTTP que les autres événements. Les confirmations d'oubli d'une mémoire dans la boîte de dialogue native sont aussi déclarées explicitement.

Seul l'identifiant fixe est envoyé : ni texte affiché, ni saisie, ni nom de conversation, ni identifiant de ressource. Les boutons des écrans protégés utilisent tous `protected.press` ; leur fonction précise n'est pas visible dans ce journal. Les interactions avant connexion ne sont pas envoyées faute de session attribuable ; les appels d'inscription et de connexion restent journalisés côté API. Les liens de ces écrans et les soumissions par clavier ne constituent pas des appuis sur un bouton `Pressable`.

L'envoi est asynchrone et sans nouvelle tentative : un appui hors ligne, pendant une fermeture immédiate de l'application ou après expiration de session peut manquer. Un HTTP 204 signifie seulement que la déclaration d'appui a été reçue, pas que l'action métier a réussi. Ces événements déclarés par le client servent aux statistiques d'usage et au recoupement ; pour une enquête de sécurité, vérifier l'action API correspondante, car un client modifié peut fabriquer des appuis. L'ajout d'un nouveau bouton nécessite un identifiant fixe dans l'application et dans la liste autorisée de `app/modules/audit/router.py`.
