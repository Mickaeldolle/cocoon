# Cocoon

Application mobile familiale privée, construite comme un monorepo Expo + FastAPI.

## État du projet

Le MVP assistant comprend la capture universelle texte, les propositions confirmables, la mémoire
personnelle avec provenance/correction/oubli, le provider local OpenAI-compatible, la voix via
STT privé, les rappels récurrents et leur outbox durable. Les bases familiales et la messagerie
normale existent séparément ; la messagerie secrète est conservée hors du contexte assistant et
n’est pas modifiée. Le suivi détaillé et cochable est dans [`TASKS.md`](TASKS.md), tandis que
[`PLAN.md`](PLAN.md) conserve les choix d’architecture et de sécurité.

## Démarrage local sans Docker

Prérequis : Python 3.12, Node.js LTS et une instance PostgreSQL accessible depuis le poste.
Une instance PostgreSQL lancée dans WSL convient si elle est exposée sur `localhost:5432`.

1. Créez une base et un utilisateur PostgreSQL locaux, par exemple `cocoon`.
2. Copiez `apps/api/.env.example` vers `apps/api/.env`, puis renseignez votre URL PostgreSQL
   et un `JWT_SECRET` local d’au moins 32 caractères. Ce fichier n’est pas versionné.
   Pour connecter l’assistant à votre modèle auto-hébergé, renseignez aussi `LLM_API_URL`,
   `LLM_API_KEY` (facultatif sur un réseau privé) et `LLM_MODEL`. `LLM_API_URL` doit être
   l’URL interne d’une API compatible OpenAI Chat Completions ; le mobile ne reçoit jamais
   cette URL ni aucune clé.
3. Dans `apps/api`, installez les dépendances, appliquez les migrations et démarrez l’API :

```text
python -m pip install -e ".[dev]"
alembic upgrade head
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

L’API est alors disponible sur `http://localhost:8002/health`.

Pour vérifier le socle sans lancer de service externe :

```powershell
pwsh -NoProfile -File .\scripts\validate-mvp.ps1
```

Cette validation exécute les tests API, Ruff, le typecheck mobile, la tête Alembic et la
configuration Compose. Hermes n’est pas requis ni utilisé par le MVP.

4. Dans un second terminal, copiez `apps/mobile/.env.example` vers `apps/mobile/.env`, puis
   depuis `apps/mobile`, exécutez :

```text
npm install
npm exec expo start -- --web
```

L’aperçu web est disponible sur `http://localhost:8081`. Pour tester depuis un téléphone,
remplacez `localhost` dans `apps/mobile/.env` par l’adresse IP du poste joignable depuis le
téléphone.

## Démarrage avec Docker (optionnel)

1. Copiez `.env.example` vers `.env`, puis remplacez les valeurs de démonstration, en particulier `POSTGRES_PASSWORD` et `JWT_SECRET`.
2. Lancez les services : `docker compose -f docker/compose.yml --env-file .env up --build`.
3. Vérifiez l’API via Caddy sur `http://localhost:8080/health`. Les ports locaux sont
   configurables avec `COCOON_HTTP_PORT` et `COCOON_HTTPS_PORT`; utilisez `80` et `443`
   uniquement sur le serveur de production.

Les migrations Alembic sont appliquées automatiquement avant le démarrage de l’API. Elles
restent idempotentes et peuvent aussi être lancées explicitement avec
`docker compose -f docker/compose.yml --env-file .env exec api alembic upgrade head`.

Pour l’application mobile, installez Node.js LTS, puis depuis `apps/mobile` exécutez `npm install` et `npm exec expo start --dev-client`. Les fonctionnalités natives sensibles seront utilisées avec un development build Expo/EAS, pas Expo Go.

## Tests API

Dans `apps/api` :

```text
python -m pip install -e ".[dev]"
pytest
```

Les variables de production ne doivent jamais être ajoutées au dépôt. Les consignes de déploiement sont dans [`docs/deployment.md`](docs/deployment.md).
