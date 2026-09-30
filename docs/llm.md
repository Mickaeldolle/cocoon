# Moteurs LLM de Cocoon

L'assistant existant garde ses routes `/api/assistant/chat` et
`/api/assistant/chat/stream`. Le mobile envoie seulement le texte à l'API.
L'API ajoute le contexte de **l'utilisateur authentifié**, puis `LLMService`
sélectionne un provider. Aucune URL ni clé LLM n'est embarquée dans Expo.
Les conversations secrètes restent hors du contexte assistant.

```text
Expo web / Android / iOS
          │ HTTPS + JWT
          ▼
FastAPI /api/assistant/{chat,chat/stream,status}
          │ contexte personnel / consentement / limites
          ▼
AssistantService → LLMService → ProviderFactory
                                  ├─ OllamaProvider → Ollama
                                  └─ OpenAICompatibleProvider → LM Studio / vLLM
```

## Configuration

Copier `apps/api/.env.example` pour un lancement natif, ou `.env.example`
à la racine pour Compose. Ne jamais commiter les valeurs réelles. Le backend
accepte encore `LLM_API_URL` comme alias de `LLM_BASE_URL`.
Le client HTTP évite les proxys hérités de l'environnement ; prévoir une
route réseau directe vers le moteur ou configurer un proxy explicite devant lui.

| Variable | Usage |
| --- | --- |
| `LLM_PROVIDER` | `ollama` ou `openai_compatible` |
| `LLM_BASE_URL` | Racine OpenAI-compatible, avec `/v1` |
| `LLM_API_KEY` | Clé facultative en local privé, requise par votre proxy distant |
| `LLM_MODEL` | Identifiant de modèle OpenAI-compatible |
| `OLLAMA_BASE_URL` | Racine Ollama, sans `/api` |
| `OLLAMA_MODEL` | Modèle téléchargé avec `ollama pull` |
| `LLM_CONNECTION_TIMEOUT` | Délai de connexion en secondes, défaut 20 |
| `LLM_READ_TIMEOUT` | Délai entre lectures, défaut 600 ; 0 désactive cette limite |
| `LLM_POOL_TIMEOUT` | Attente d'une connexion disponible, défaut 20 |
| `LLM_STREAMING` | `true` par défaut ; `false` renvoie la réponse d'un seul coup |
| `LLM_HEALTHCHECK_ENABLED` | Active la vérification de `/status` |
| `ASSISTANT_REQUESTS_PER_MINUTE` | Générations par compte et par processus API, défaut 30 |

Une configuration partielle ou une URL invalide arrête le démarrage avec une
erreur explicite. Sans URL et sans modèle OpenAI-compatible, le backend démarre
et l'assistant répond qu'il est indisponible.

### Ollama local

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

Installer Ollama, exécuter `ollama pull qwen3:8b`, puis lancer le serveur
Ollama. Avec l'API dans Docker, utiliser
`OLLAMA_BASE_URL=http://host.docker.internal:11434`. Sous Linux,
`extra_hosts: host-gateway` figure dans Compose. Le service hôte doit accepter
les connexions depuis le pont Docker ; garder ce port privé.
L'adaptateur utilise [l'API native Ollama](https://github.com/ollama/ollama/blob/main/docs/api.md).

### LM Studio local

Charger un modèle dans LM Studio, activer son serveur API, puis configurer :

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=
LLM_MODEL=qwen3-8b
```

Le nom de modèle doit correspondre à celui annoncé par le serveur. Avec
l'API dans Docker, utiliser `http://host.docker.internal:1234/v1` et autoriser
la connexion depuis le pont Docker sans ouvrir le port sur Internet.
Voir la [documentation du serveur LM Studio](https://lmstudio.ai/docs/developer/core/server)
et ses [routes OpenAI compatibles](https://lmstudio.ai/docs/developer/openai-compat/models).

### vLLM distant ou temporaire

Sur un hôte pris en charge, installer vLLM selon les
[instructions correspondant au GPU](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/).
La disponibilité dépend du matériel et de l'environnement ; CUDA NVIDIA est
un cas courant, et d'autres plateformes ont leurs propres prérequis.
Lancer, par exemple, `vllm serve Qwen/Qwen3-8B --host 127.0.0.1 --port 8000`.
La même configuration convient à un serveur GPU permanent ou temporaire :

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://llm.example.com/v1
LLM_API_KEY=valeur-secrete-cote-serveur
LLM_MODEL=Qwen/Qwen3-8B
```

Ne pas publier directement un serveur vLLM ouvert. Le placer derrière un
reverse proxy TLS avec authentification, contrôle d'accès et limitation de débit.
Un tunnel temporaire peut changer d'URL : modifier la variable et redémarrer
l'API et le worker de capture. Quand le GPU est arrêté, le web et l'API restent
disponibles ; seuls les appels IA échouent proprement. Aucun retry automatique
ne risque de dupliquer une génération coûteuse.

## Démarrage sans Docker

Il faut Python 3.12, Node.js et PostgreSQL. Sur Windows :

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
# Remplir apps/api/.env avec DATABASE_URL, JWT_SECRET et la configuration LLM.
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Sur Linux/macOS, remplacer l'activation par `source .venv/bin/activate`.
Dans un autre terminal :

```powershell
cd apps/mobile
# Remplir apps/mobile/.env avec EXPO_PUBLIC_API_URL=http://localhost:8002
npm ci
npm exec expo start -- --web
```

Pour un appareil physique, utiliser l'adresse du poste accessible sur le LAN.
L'URL publique Expo est celle de l'API, **sans** suffixe `/api`.

## Démarrage avec Docker

Copier `.env.example` en `.env`, choisir un mot de passe PostgreSQL, un
`JWT_SECRET` de 32 caractères minimum, le provider, et l'URL publique de
l'API dans `EXPO_PUBLIC_API_URL`. Cette dernière est injectée dans la
construction du web ; reconstruire l'image si elle change.

```powershell
docker compose up --build
# Les lancements suivants : docker compose up
```

Compose construit le frontend Expo web, lance Caddy, FastAPI, PostgreSQL,
Redis, les migrations et les workers. Le navigateur utilise l'adresse
`EXPO_PUBLIC_API_URL` ; depuis un téléphone elle doit être joignable.
En production, donner un nom de domaine à `CADDY_SITE_ADDRESS`, publier les
ports 80/443 et définir `EXPO_PUBLIC_API_URL` sur son origine HTTPS.
Le LLM reste externe au Compose. La même API peut joindre Ollama ou LM Studio
sur l'hôte, ou vLLM en HTTPS. Le frontend Expo natif peut continuer à être
lancé sans Docker pour tester Android/iOS.
vLLM fournit une [API Chat Completions compatible OpenAI](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html).
Le fichier `compose.yml` à la racine inclut l'unique définition dans
`docker/compose.yml`.
Si votre version de Compose ne comprend pas `include`, lancer
`docker compose -f docker/compose.yml --env-file .env up --build`.

## Streaming, état et erreurs

`POST /api/assistant/chat/stream` transmet les fragments SSE sans attendre
la fin du modèle. Le client conserve son contrat `started/delta/complete/error`.
`GET /api/assistant/status` requiert le JWT et renvoie seulement
`available`, `provider` et `model`. Ce contrôle ne décide pas de la santé
globale : `/health/ready` ne dépend que de la base. Une connexion refusée,
un timeout ou un HTTP 5xx devient un message français sans détail de
l'infrastructure ou du prompt. Les logs contiennent provider, modèle, durée,
statut et type d'erreur, jamais le contenu ni la clé.

## Validation

```powershell
cd apps/api
.venv\Scripts\pytest.exe -q
.venv\Scripts\ruff.exe check app tests migrations
cd ../mobile
npm run typecheck
docker compose -f ../../docker/compose.yml --env-file ../../.env config
```

Les tests de provider simulent HTTP ; ils ne prouvent pas un modèle réellement
chargé, le GPU, le réseau de production ou le comportement sur appareil
physique. Pour qualifier un déploiement, tester chaque provider réel, le
streaming interrompu, l'arrêt du moteur et le redémarrage du worker.
La limite de concurrence et la limite de débit par utilisateur sont en mémoire
du processus API. Avant d'exécuter plusieurs réplicas, remplacer cette limite
par un compteur partagé, par exemple dans Redis. L'audit des dépendances npm
du build Docker signale des alertes
à trier avant la production.
