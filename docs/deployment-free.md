# Déploiement d'essai à coût nul : Vercel, Supabase et ZeroGPU

État au 24 septembre 2026. **Procédure préparatoire, pas déploiement effectué.** Cible : quelques testeurs, priorité au texte, aucun abonnement payant. Garder [la qualification bêta](../TASKS.md) séparée de cet essai. Les quotas et conditions des fournisseurs peuvent changer : les vérifier avant activation.

## Architecture et verdict

```text
Navigateur (site Vercel) ─┐
                          ├─ HTTPS → FastAPI (autre projet Vercel) → Supabase PostgreSQL
APK Android ───────────────┘                            │
                                                       └─ HTTPS → Space Gradio ZeroGPU (LLM)
```

Le navigateur et l'APK n'ont que l'URL publique de FastAPI. Seule l'API détient les secrets Supabase et Hugging Face. Le web statique et l'APK ne contiennent jamais `DATABASE_URL`, `JWT_SECRET` ou un jeton HF. La base reste celle de Cocoon, **Supabase Auth n'est pas utilisé** : remplacer l'authentification existante ajouterait un chantier de migration.

Ce montage est **adapté à un prototype texte à faible usage**, sous réserve des adaptations ci-dessous. Il ne satisfait pas encore la bêta familiale complète : workers permanents, rappels précis, notifications, WebSocket, essais PostgreSQL et données privées réelles ne sont pas qualifiés. Le fournisseur LLM distant change la frontière de confidentialité : utiliser des comptes et données fictifs jusqu'à décision explicite sur les données admissibles.

| Élément | Disponible aujourd'hui | Travail avant essai bout en bout |
| --- | --- | --- |
| Web Expo | Export statique local réussi le 24/09/2026 ; `vercel.json` ajouté | Vérifier le site Vercel, chaque route profonde, la session et le flux de chat dans un vrai navigateur |
| APK | Profil `preview` configuré pour produire un APK | Construire, signer, installer et tester sur Android réel ; voir [procédure APK](android-apk.md) |
| API | FastAPI et point d'entrée `apps/api/index.py` | Déployer le projet Vercel, prouver l'import et les routes, tester la taille du bundle et les délais réels |
| PostgreSQL | SQLAlchemy et migrations Alembic présents | Tester les migrations sur Supabase isolé, adapter les connexions au pooler transactionnel, vérifier concurrence et restauration |
| LLM | Contrat OpenAI `/chat/completions` uniquement | Créer/choisir un Space Gradio, définir son contrat de messages, ajouter l'adaptateur ZeroGPU côté API, tester quota, queue, erreurs et timeouts ; **ne pas renseigner `LLM_API_URL` avec l'URL d'un Space Gradio** |
| Temps réel | Route `/api/ws` dans l'API ; les conversations mobiles interrogent actuellement l'API toutes les 8 s | [Vercel annonce des WebSockets en bêta publique depuis juin 2026](https://vercel.com/changelog/websocket-support-is-now-in-public-beta), mais les exemples publiés utilisent Node.js : vérifier par déploiement que le runtime Python/FastAPI accepte l'upgrade. Même si oui, Cocoon conserve les tickets et connexions en mémoire de chaque instance : authentification et diffusion peuvent échouer entre instances ; prévoir un stockage/bus partagé et la reconnexion avant de promettre du temps réel |
| Workers | Deux processus séparés pour captures et rappels ; la capture en flux peut aussi traiter la demande dans HTTP | Vercel ne lance pas ces boucles permanentes. Désactiver/retirer du parcours la mise en file `/api/captures/queue` sans worker ; l'API fournit un traitement borné des notifications à déclencher par Supabase Cron, à configurer et qualifier en réel |

## Limites gratuites à dimensionner

- [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu) : 5 minutes GPU par jour pour un compte gratuit, file d'attente, et au plus deux Spaces ZeroGPU pour un compte personnel éligible (compte en règle, email vérifié et ancienneté indiquée par HF). Le quota est celui du **compte qui appelle** : si FastAPI utilise un seul jeton serveur, tous les testeurs le partagent. Une fois épuisé, afficher une erreur compréhensible et réessayer le lendemain ; aucune promesse de disponibilité continue. ZeroGPU exige un Space Gradio avec fonction `@spaces.GPU`, mais n'impose pas vLLM.
- [Vercel Hobby](https://vercel.com/docs/plans/hobby) est gratuit pour un usage personnel non commercial, sous quotas. Les [Functions Python](https://vercel.com/docs/functions/limitations) ont une limite de 4,5 Mo par corps de requête/réponse et, avec Fluid Compute, une durée maximale Hobby de 300 s. Le délai de queue ZeroGPU + génération doit rester sous cette limite ; prévoir un état d'attente ou un job asynchrone si ce n'est pas le cas. Le code vocal accepte actuellement jusqu'à **8 Mio**, donc un upload vocal de cette taille échouerait avant FastAPI (`413`). La voix est hors périmètre de cet essai.
- Le [cron Hobby Vercel](https://vercel.com/docs/cron-jobs/usage-and-pricing) fonctionne au maximum une fois par jour avec une précision d'environ une heure : il ne peut pas fournir les rappels à l'heure. [Supabase Cron](https://supabase.com/docs/guides/cron) peut appeler le point d'entrée borné de Cocoon chaque minute, selon la procédure [notifications web](SECRET_NOTIFICATIONS.md#site-et-api-hébergés-sur-vercel). Disponibilité, quota, secret d'appel et concurrence doivent être vérifiés sur le projet réel. Aucun rappel n'est déclaré fiable avant test.
- [Supabase Free](https://supabase.com/docs/guides/platform/billing-on-supabase) fournit notamment 500 Mo de base par projet et deux projets gratuits ; un [projet peu actif peut être mis en pause](https://supabase.com/docs/guides/platform/free-project-pausing). Prévoir dump/restauration externe avant les essais importants ; une base gratuite ne remplace pas une sauvegarde opérée et testée.

## Ordre de mise en place

### 0. Préparer la révision et les comptes

1. Figer une révision Git identifiable et vérifier que `.env`, jetons, sauvegardes et APK signés ne sont pas publiés. Cette copie du dépôt n'avait aucun commit suivi lors de l'audit.
2. Créer des comptes gratuits distincts pour Vercel, Supabase, Hugging Face et Expo. Choisir une région Vercel proche de la région Supabase pour réduire la latence, puis relever les URL exactes : `https://<api>.vercel.app` et `https://<web>.vercel.app`.
3. Lancer les contrôles locaux de `scripts/validate-mvp.ps1` et noter les erreurs restantes. Utiliser une base **neuve**, des comptes fictifs et aucun secret familial ou donnée de santé.

### 1. Supabase PostgreSQL

1. Créer un projet Supabase Free vide. Dans **Connect**, copier les URI de connexion : **Transaction pooler** pour les fonctions Vercel (port 6543) et **Direct** pour les migrations depuis un environnement qui joint IPv6. Si IPv6 est indisponible, utiliser le pooler **Session** (port 5432) pour la migration. [Supabase recommande le mode transactionnel pour le serverless et le direct pour migrations et dumps](https://supabase.com/docs/guides/database/connecting-to-postgres).
2. Employer le schéma SQLAlchemy `postgresql+psycopg://.../postgres?sslmode=require` et encoder les caractères spéciaux du mot de passe dans l'URI. Conserver ces URI uniquement dans les secrets d'environnement. Le mode transactionnel [ne prend pas en charge les prepared statements](https://supabase.com/docs/guides/troubleshooting/disabling-prepared-statements-qL8lEL) : régler Psycopg `prepare_threshold=None` et une stratégie de connexions adaptée avant de l'utiliser sous charge. La configuration actuelle `create_engine(..., pool_pre_ping=True)` n'est **pas encore qualifiée** pour ce pooler ; ne pas présenter `/health/ready` seul comme preuve. Après le déploiement de l'API, appliquer les migrations Alembic, y compris celle des [passkeys web](web-passkeys.md).
3. Depuis `apps/api`, dans un terminal où `DATABASE_URL` pointe vers la **base de test choisie**, exécuter `alembic upgrade head`, puis `alembic current`. Ne jamais migrer automatiquement à chaque démarrage de Function. Tester lecture, écriture, deux sessions concurrentes et reconnexion après interruption du pooler.
4. Exporter un dump hors Supabase et restaurer dans un second projet/une base de test. Les scripts `scripts/backup-postgres.ps1` ciblent le Compose local : ils ne sont pas directement la procédure Supabase.

### 2. API FastAPI sur Vercel

1. Créer un projet Vercel depuis le dépôt, **Root Directory = `apps/api`**, preset Python/FastAPI. Le fichier `index.py` à cette racine expose `app` depuis `app.main`. Vercel [reconnaît les points d'entrée FastAPI](https://vercel.com/docs/frameworks/backend/fastapi), mais le déploiement réel de Cocoon reste à tester. Ne pas lancer de migration dans le build ou la Function.
2. Configurer les variables serveur : `APP_ENV=production`, `JWT_SECRET` long et aléatoire, `DATABASE_URL` du pooler transactionnel après adaptation/validation, `CORS_ORIGINS=["https://<web>.vercel.app"]`, et les futures variables du provider ZeroGPU côté serveur uniquement. `REDIS_URL` n'est actuellement lu par aucun module métier ; créer Redis pour ce montage n'apporterait rien.
3. Déployer l'API, vérifier `GET /health` puis `GET /health/ready`, un compte de test, une connexion et une route protégée. Tester les erreurs 401/403, une seconde instance à froid, trois requêtes et la reconnexion DB. Protéger `/internal/metrics` avec `METRICS_TOKEN` si utilisé ; ne jamais imprimer les valeurs secrètes dans les journaux.
4. Garder la route WebSocket et les workers hors critères de succès de ce prototype. Les conversations mobiles utilisent actuellement un rafraîchissement HTTP toutes les 8 s et peuvent être testées ainsi. Pour garantir le temps réel, tester l'upgrade WebSocket de **FastAPI/Python sur Vercel**, ajouter une distribution inter-instances et une reconnexion cliente ; les notifications à l'heure restent bloquées sans remplacement du worker.

### 3. Space ZeroGPU pour le texte

1. Choisir un modèle instruction francophone compatible avec les ressources ZeroGPU et sa licence. Créer un Space **Gradio** éligible ZeroGPU ; exposer une fonction `@spaces.GPU` recevant un tableau de messages `role/content` et renvoyant du texte, avec une limite de tokens et de durée. D'abord l'éprouver avec les scénarios fictifs du [benchmark](ASSISTANT_EFFECTIVENESS_AUDIT.md).
2. Dans le Space, ouvrir **Use via API** pour relever le `api_name`, les paramètres et le format de sortie. Les [Spaces Gradio exposent une API](https://huggingface.co/docs/hub/spaces-api-endpoints), y compris les Spaces privés avec jeton. Choisir un Space privé si le cas l'autorise ; garder le jeton HF dans l'environnement Vercel API. Ne jamais l'inclure dans `EXPO_PUBLIC_*`.
3. Implémenter un provider `ZeroGPUProvider` dans FastAPI qui transforme les messages Cocoon en contrat Gradio, gère queue/quota/timeout/annulation, et normalise la réponse en `ProviderResult`. Prévoir le comportement sans streaming si le Space ne produit qu'une réponse finale. Tester les erreurs et la sortie structurée/fallback ; le provider actuel attend `/chat/completions` et ne peut pas appeler un Space directement.
4. Mesurer le temps jusqu'à la première réponse, le temps total, le taux de 429/503 et la consommation quotidienne avec un seul puis deux testeurs. Réduire le contexte envoyé ; ne transmettre ni conversation cachée/familiale ni santé par défaut.

### 4. Site web sur Vercel

1. Créer un **second projet** Vercel sur le même dépôt, **Root Directory = `apps/mobile`**, framework `Other`. Le `vercel.json` fourni exporte Expo Web dans `dist` et réécrit les routes de la SPA. La [procédure Expo officielle](https://docs.expo.dev/guides/publishing-websites/) utilise cette configuration.
2. Définir dans les **variables de build** web `EXPO_PUBLIC_API_URL=https://<api>.vercel.app` sans slash final, puis déployer. Cette valeur est intégrée au bundle : tout changement d'URL API exige un nouveau build web. Vérifier `dist/index.html`, la page d'accueil, le rechargement d'une URL profonde, l'inscription/connexion et le chat.
3. Ajouter l'origine finale du site dans `CORS_ORIGINS` de l'API et redéployer l'API. Les URLs de preview Vercel ont une origine différente ; les ajouter explicitement pour les previews que l'on teste, sans joker général. Ne pas activer `Access-Control-Allow-Origin: *` avec des identifiants.

### 5. Android hors Play Store

Suivre [la procédure de build et d'installation APK](android-apk.md). L'APK doit être construit avec **la même URL API HTTPS finale** que le site. Le navigateur impose CORS, alors que l'APK natif n'en a pas besoin ; les deux exigent une API publiquement joignable et un certificat TLS valide.

## Vérification des communications et diagnostic

| Flux | Test minimal | Échec probable / action |
| --- | --- | --- |
| Web → API | Depuis le navigateur, `OPTIONS /api/auth/login` avec `Origin: https://<web>.vercel.app`, puis appel réel | `CORS_ORIGINS` vide/mal formé, preview non inscrite, préflight refusé, API URL embarquée incorrecte |
| APK → API | Ouvrir connexion sur Wi-Fi puis données mobiles | `localhost` dans l'APK, DNS/TLS, URL d'API incorrecte, API froide ou DB en pause |
| API → Supabase | `/health/ready`, puis login/écriture/lecture | URI IPv6 directe depuis environnement IPv4, SSL, mot de passe non encodé, `prepared statement` avec pooler transactionnel, trop de connexions |
| API → ZeroGPU | Appel fictif depuis la Function, temps et code d'erreur | contrat Gradio ≠ OpenAI, Space endormi, queue/quota partagé, durée Function dépassée |
| Notification / temps réel | Test ciblé séparé | workers absents, cron Hobby insuffisant, support WebSocket Python non vérifié et diffusion inter-instances absente, identifiant EAS/FCM manquant |
| Preview Vercel → API | Charger une preview web et exécuter un appel réel | URL de preview différente de la production dans `CORS_ORIGINS` ; éventuelle protection d'accès Vercel sur la preview API |

Commande de préflight à adapter sans aucun jeton utilisateur :

```powershell
curl.exe -i -X OPTIONS "https://<api>.vercel.app/api/auth/login" -H "Origin: https://<web>.vercel.app" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: authorization,content-type"
```

Attendu : réponse 2xx avec `Access-Control-Allow-Origin` égal à l'origine web et les en-têtes demandés autorisés. Un `GET /health` réussi ne prouve pas CORS, le login, la base ou le fournisseur IA. Le stockage du refresh token web se fait aujourd'hui dans `localStorage` : un audit XSS et une stratégie de session web plus robuste sont requis avant données personnelles réelles. Les URL `vercel.app` publiques et les comptes de test doivent être considérés exposés à Internet.

## Validation de sortie, maintenance et retour arrière

Pour déclarer l'**essai texte** opérationnel, conserver les preuves suivantes : build web et APK signés pour une même révision, `/health/ready`, préflight CORS, inscription/connexion web et Android, capture/chat avec ZeroGPU, changement de compte A/B/A, panne/quota HF affiché correctement, restauration DB de test, et vérification qu'aucun secret n'est dans le bundle. Mesurer la latence et le quota pendant plusieurs jours. Pour revenir en arrière, redéployer la révision Vercel précédente et l'APK précédent **si le schéma reste compatible** ; ne jamais inverser une migration destructive sans sauvegarde et procédure validée. Garder les alertes de pause Supabase, d'échec API et de quota HF visibles. Cela reste un environnement d'essai, sans promesse de rappels ou d'inférence privée.
