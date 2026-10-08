# Déploiement initial

Pour la mémoire personnelle, l'extension pgvector et les trois cibles actuelles
(développement local, Vercel/Supabase, VPS Docker), suivre le
[plan de déploiement mémoire](deployment-memory.md). Il précise que Vercel ne lance pas
le worker permanent et que l'activation vectorielle y reste désactivée sans runtime
d'embedding privé et authentifié.

Pour l'essai gratuit demandé, suivre d'abord [Vercel + Supabase + ZeroGPU](deployment-free.md) et [la procédure APK Android](android-apk.md). Les [autres options](deployment-options.md) concernent une étape ultérieure. Les commandes Compose ci-dessous décrivent seulement le socle auto-hébergé actuel ; elles ne prouvent pas un déploiement fonctionnel.

## Préparation

- Créez un `.env` hors du contrôle de version à partir de `.env.example`.
- Générez `JWT_SECRET` avec une source cryptographiquement sûre (au moins 32 octets aléatoires).
- Utilisez un mot de passe PostgreSQL unique et long.
- Configurez `CADDY_SITE_ADDRESS` avec le nom DNS public (par exemple `api.example.com`) avant un déploiement Internet.

## Validation locale reproductible

Depuis la racine du dépôt, après installation des dépendances API et mobile :

```powershell
.\scripts\validate-mvp.ps1
```

Cette commande exécute les tests API, Ruff, la lecture de la tête Alembic, le typecheck
mobile, l’audit de reproductibilité et la validation syntaxique de Compose avec les valeurs
d’exemple. Elle ne lance aucune migration sur une base personnelle et ne contacte aucun
fournisseur externe.

## Lancement

```text
docker compose -f docker/compose.yml --env-file .env up -d --build
```

Le service Compose `migrate` applique `alembic upgrade head` au lancement ; l’API et les
workers attendent sa réussite avant de démarrer. La commande peut être relancée manuellement,
elle est idempotente sur un schéma compatible. Le worker mémoire est facultatif et utilise le
profil Compose `memory`. En local, Cocoon utilise par défaut les ports 8080/8443
afin de ne pas entrer en conflit avec un autre reverse proxy. Sur le VPS, configurez
`COCOON_HTTP_PORT=80` et `COCOON_HTTPS_PORT=443`.

## Création du premier super-administrateur

Après la migration, créez le compte depuis le conteneur API privé. Le mot de passe est demandé dans le terminal et n'est ni enregistré dans le dépôt, ni affiché :

```text
docker compose -f docker/compose.yml --env-file .env exec -it api python -m app.commands.create_superadmin --email vous@example.com --display-name "Votre nom"
```

Pour promouvoir un compte existant, seule l'adresse email est nécessaire :

```text
docker compose -f docker/compose.yml --env-file .env exec api python -m app.commands.create_superadmin --email vous@example.com
```

Ce rôle ne contourne pas les autorisations métier ordinaires. Il donne uniquement accès aux endpoints explicitement protégés par `require_superadmin`, dont `/api/admin/status` sert actuellement de sonde pour la future interface d'administration.

Seul Caddy (80/443 selon la configuration) doit être exposé sur Internet. PostgreSQL et l’API restent sur le réseau Docker privé. Sauvegardez régulièrement PostgreSQL et testez une restauration avant la mise en production. L'ancien service Redis inutilisé a été retiré de Compose ; son volume déclaré est conservé et ses données éventuelles doivent être inventoriées avant toute suppression physique.

### Métriques internes

Les compteurs HTTP agrégés sont disponibles sur `/internal/metrics` uniquement lorsque
`METRICS_TOKEN` est configuré avec au moins 32 caractères. Le scraper interne doit envoyer
ce secret dans `X-Metrics-Token`. Sans cette variable, la route renvoie 404 ; aucun compteur
ou contenu de requête n’est exposé publiquement.

Une sonde PowerShell prête à être appelée par le planificateur de la machine ou un superviseur
externe vérifie la readiness, le nombre de requêtes en cours et les réponses HTTP 5xx :

```powershell
.\scripts\check-metrics.ps1 -BaseUrl http://127.0.0.1:8000 -MetricsToken $env:COCOON_METRICS_TOKEN
```

Le token n’est jamais affiché par le script. Un code de sortie différent de zéro doit être
relié à l’alerte de l’environnement ; Cocoon ne prétend pas fournir un scraper ou un système
d’astreinte intégré dans ce MVP.

### Sauvegarde et restauration PostgreSQL

Le dépôt fournit un chemin chiffré avec [`age`](https://age-encryption.org/) ; `age` doit être
installé séparément sur la machine d’exploitation. Depuis la racine du dépôt, avec un `.env`
réel et le service PostgreSQL démarré :

```powershell
.\scripts\backup-postgres.ps1
```

Le script produit un dump PostgreSQL custom chiffré et supprime son fichier temporaire en clair.
La restauration est volontairement destructive et exige une confirmation explicite :

```powershell
.\scripts\restore-postgres.ps1 -InputPath .\backups\cocoon-YYYYMMDD-HHMMSS.dump.age -ConfirmText "RESTORE COCOON"
```

Après restauration, exécutez `alembic upgrade head`, `/health/ready` et les contrôles de
cohérence applicatifs avant de remettre l’API et le worker en service. Cette procédure n’a pas
encore été exécutée sur un PostgreSQL bêta dans l’environnement courant.

## Assistant et rappels

Pour vérifier ponctuellement le runtime local sans afficher de credential, utilisez le script
de qualification suivant :

```powershell
.\scripts\validate-ollama.ps1 -BaseUrl http://127.0.0.1:11434 -Model gemma4:e4b -Requests 3
```

Il vérifie que le modèle est installé, exécute des réponses réelles et retourne les durées en
JSON. Il ne remplace pas une mesure de premier token ou une qualification après redémarrage.

- Hébergez le runtime de modèle open source sur le réseau privé, sans port publié. Configurez
  `LLM_API_URL` avec son URL interne compatible OpenAI (par exemple `http://llm:8000/v1`) et
  `LLM_MODEL` ; `LLM_API_KEY` est facultative lorsqu’un reverse proxy privé n’en exige pas.
- Ne branchez jamais le mobile directement au runtime. L’API Cocoon limite le contexte à la
  pensée envoyée et aux titres des priorités récentes ; elle n’envoie jamais la messagerie, les
  salons cachés, leurs fichiers ou les mesures de santé.
- Pour la transcription vocale, configurez un runtime de reconnaissance compatible OpenAI,
  également privé, avec `STT_API_URL` et `STT_MODEL` (et `STT_API_KEY` seulement si nécessaire).
  Cocoon transmet seulement un enregistrement court créé explicitement par la personne, ne le
  persiste ni dans PostgreSQL ni dans les journaux, et retourne le texte à modifier avant envoi.
- Les services `capture-worker` et `reminder-worker` démarrent avec Compose. Le worker mémoire
  s'ajoute uniquement avec `--profile memory`, après qualification d'Ollama et de pgvector.
  Le worker de capture reprend les captures placées en file après une coupure réseau ou un
  redémarrage ; celui de rappel prépare les rappels confirmés et le brief quotidien dans une
  outbox durable, puis les transmet à Expo Push uniquement pour les
  appareils ayant enregistré un token. Les contenus de push restent génériques.
- Configurez les appareils réels avec un development build et un token Expo avant de compter
  sur les notifications. Testez l’arrivée d’un rappel, la désactivation du brief, la modification
  d’heure et le comportement écran verrouillé sur iOS et Android.

## À faire avant production

- utiliser un domaine public et laisser Caddy gérer TLS ;
- placer les sauvegardes dans un stockage séparé et chiffré ;
- ajouter métriques, logs structurés et alertes ;
- ajouter rate limiting et vérification d’email ;
- tester le worker de notifications et la restauration de son outbox ;
- exécuter une revue de sécurité avant la phase de messagerie cachée.
