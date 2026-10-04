# Lightning AI + vLLM + Vercel

## Objectif

Nous voulons obtenir cette architecture :

```text
Utilisateur
    │
    ▼
Application Vercel
    │
    │ appel serveur → serveur
    ▼
Endpoint HTTPS Lightning AI
    │
    ▼
Reverse proxy
    │
    ▼
vLLM
    │
    ▼
Modèle Hugging Face
```

L'application est déjà configurée pour utiliser une API OpenAI-compatible.

L'objectif final est donc simplement d'obtenir une URL de ce type :

```text
https://xxxxx.lightning.ai/v1
```

et de configurer Vercel avec :

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://xxxxx.lightning.ai/v1
LLM_API_KEY=...
LLM_MODEL=Qwen/Qwen3-4B
```

Aucune modification majeure de l'application ne doit être nécessaire.

---

# 1. Créer un compte Lightning AI

Se rendre sur :

```text
https://lightning.ai/
```

Créer un compte.

Lightning AI propose actuellement un Studio CPU gratuit et des crédits GPU de démarrage. La vérification du numéro de téléphone permet d'accéder aux crédits GPU promotionnels disponibles.

Les quotas et crédits peuvent évoluer.

---

# 2. Créer un Studio

Depuis Lightning AI :

```text
New Studio
```

Donner par exemple comme nom :

```text
vllm-server
```

Le Studio démarre normalement sur une machine CPU gratuite.

C'est un environnement Linux persistant.

Il possède notamment :

```text
terminal
VS Code
Jupyter
stockage
SSH
```

---

# 3. Préparer le Studio

Ouvrir le terminal intégré.

Vérifier Python :

```bash
python --version
```

Puis :

```bash
pip --version
```

Mettre pip à jour :

```bash
python -m pip install --upgrade pip
```

---

# 4. Choisir le GPU

Pour commencer, utiliser de préférence :

```text
NVIDIA L4
24 Go VRAM
```

Cette carte est suffisamment puissante pour tester confortablement des modèles de quelques milliards de paramètres sans consommer aussi rapidement les crédits qu'une A100.

Dans le Studio, modifier le type de machine et choisir une machine GPU L4 si elle est disponible.

Une fois le GPU démarré :

```bash
nvidia-smi
```

Tu dois voir une carte NVIDIA.

Par exemple :

```text
NVIDIA L4
24576 MiB
```

---

# 5. Installer vLLM

Dans le terminal :

```bash
pip install -U vllm
```

Puis vérifier :

```bash
vllm --version
```

Ou :

```bash
python -c "import vllm; print(vllm.__version__)"
```

---

# 6. Choisir un premier modèle

Pour commencer, utiliser un modèle relativement petit.

Par exemple :

```text
Qwen/Qwen3-4B
```

L'objectif initial est de valider :

```text
Lightning
+
GPU
+
vLLM
+
API
+
Vercel
```

Il sera toujours possible de choisir un modèle plus gros ensuite.

---

# 7. Tester l'accès à Hugging Face

Pour un modèle public, vLLM téléchargera directement les fichiers nécessaires.

Pour un modèle nécessitant une authentification Hugging Face :

```bash
pip install -U huggingface_hub
```

Puis :

```bash
huggingface-cli login
```

Ne jamais commiter le token Hugging Face.

Lightning permet également de gérer des secrets.

---

# 8. Générer une API key

Créer une clé suffisamment longue.

Dans le terminal :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Exemple :

```text
wE7fCjS...
```

Conserver cette valeur.

Par exemple :

```text
VLLM_API_KEY=<secret>
```

Cette clé sera également enregistrée dans Vercel.

---

# 9. Premier lancement de vLLM

Pour commencer, lancer vLLM directement :

```bash
vllm serve Qwen/Qwen3-4B \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "TON_API_KEY"
```

vLLM fournit directement un serveur HTTP compatible avec plusieurs endpoints OpenAI, notamment Chat Completions et Completions.

Le premier lancement peut être relativement long car vLLM doit :

```text
télécharger le modèle
charger les poids
initialiser CUDA
réserver la VRAM
initialiser le KV cache
lancer le serveur
```

---

# 10. Vérifier les logs

Lorsque vLLM est prêt, il devrait indiquer que son serveur écoute sur :

```text
0.0.0.0:8000
```

Ne pas fermer le terminal.

---

# 11. Tester `/v1/models`

Ouvrir un deuxième terminal Lightning.

Tester :

```bash
curl http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer TON_API_KEY"
```

Une réponse JSON doit être retournée.

---

# 12. Tester Chat Completions

Tester ensuite :

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer TON_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B",
    "messages": [
      {
        "role": "user",
        "content": "Réponds simplement : cela fonctionne."
      }
    ]
  }'
```

Si tu reçois une réponse du modèle :

```text
Lightning → vLLM → modèle
```

fonctionne.

---

# 13. Important : ne pas exposer directement vLLM sans protection supplémentaire

vLLM possède bien :

```bash
--api-key
```

mais sa documentation précise que cette protection ne concerne pas tous les endpoints.

Elle protège notamment :

```text
/v1
/v2
/inference
```

mais certains autres endpoints du serveur ne sont pas couverts.

Pour une exposition publique, vLLM recommande donc une protection supplémentaire avec un reverse proxy.

Nous allons donc ajouter un proxy devant.

Architecture :

```text
Internet
   │
   ▼
Lightning endpoint
   │
   ▼
Nginx :8080
   │
   ▼
vLLM :8000
```

---

# 14. Installer Nginx

Dans le Studio :

```bash
sudo apt update
sudo apt install nginx -y
```

---

# 15. Configurer Nginx

Créer :

```bash
sudo nano /etc/nginx/sites-available/vllm
```

Ajouter :

```nginx
server {
    listen 8080;
    server_name _;

    client_max_body_size 10M;

    location /v1/ {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header Authorization $http_authorization;

        proxy_buffering off;
        proxy_cache off;

        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    location / {
        return 404;
    }
}
```

Cette configuration est volontairement restrictive.

Elle expose uniquement :

```text
/v1/*
/health
```

Tout le reste retourne :

```text
404
```

---

# 16. Activer la configuration

Supprimer éventuellement le site par défaut :

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

Créer le lien :

```bash
sudo ln -s /etc/nginx/sites-available/vllm /etc/nginx/sites-enabled/vllm
```

Tester :

```bash
sudo nginx -t
```

Puis :

```bash
sudo systemctl restart nginx
```

---

# 17. Tester le reverse proxy

Tester maintenant :

```bash
curl http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer TON_API_KEY"
```

Puis :

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer TON_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B",
    "messages": [
      {
        "role": "user",
        "content": "Bonjour"
      }
    ]
  }'
```

---

# 18. Exposer le port avec Lightning

Nous devons maintenant rendre :

```text
localhost:8080
```

accessible sur Internet.

Lightning permet d'exposer un serveur tournant dans un Studio, puis éventuellement d'activer un démarrage automatique lorsque l'endpoint reçoit une requête. Cette approche est utilisée dans leurs exemples officiels d'API.

Dans l'interface du Studio, chercher la fonctionnalité permettant :

```text
Expose port
Endpoint
Open port
Expose to internet
```

selon la version actuelle de l'interface.

Sélectionner :

```text
port : 8080
```

---

# 19. Rendre l'endpoint accessible

Lightning doit alors fournir une URL HTTPS ressemblant à :

```text
https://xxxxx.lightning.ai
```

Le nom exact du domaine dépend de la configuration Lightning utilisée.

Notre base URL devient :

```text
https://xxxxx.lightning.ai/v1
```

---

# 20. Tester depuis ton ordinateur

Depuis Windows PowerShell :

```powershell
curl.exe https://xxxxx.lightning.ai/v1/models `
  -H "Authorization: Bearer TON_API_KEY"
```

Ou Linux/WSL :

```bash
curl https://xxxxx.lightning.ai/v1/models \
  -H "Authorization: Bearer TON_API_KEY"
```

Tu dois obtenir la liste des modèles.

---

# 21. Tester une génération depuis Internet

```bash
curl https://xxxxx.lightning.ai/v1/chat/completions \
  -H "Authorization: Bearer TON_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B",
    "messages": [
      {
        "role": "user",
        "content": "Explique en une phrase ce qu est vLLM."
      }
    ]
  }'
```

À ce stade :

```text
Internet
→ Lightning
→ Nginx
→ vLLM
→ GPU
→ modèle
```

fonctionne.

---

# 22. Tester avec un client OpenAI

Tu peux également vérifier avec le SDK OpenAI.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://xxxxx.lightning.ai/v1",
    api_key="TON_API_KEY",
)

response = client.chat.completions.create(
    model="Qwen/Qwen3-4B",
    messages=[
        {
            "role": "user",
            "content": "Bonjour"
        }
    ],
)

print(response.choices[0].message.content)
```

Si cela fonctionne, ton endpoint est bien OpenAI-compatible.

---

# 23. Configurer Vercel

Dans :

```text
Vercel
→ Project
→ Settings
→ Environment Variables
```

ajouter ou modifier :

```env
LLM_PROVIDER=openai_compatible
```

Puis :

```env
LLM_BASE_URL=https://xxxxx.lightning.ai/v1
```

Puis :

```env
LLM_API_KEY=TON_API_KEY
```

Puis :

```env
LLM_MODEL=Qwen/Qwen3-4B
```

---

# 24. Environnements Vercel

Configurer au minimum :

```text
Production
```

et éventuellement :

```text
Preview
Development
```

selon les besoins.

Par exemple :

```text
Production → Lightning
Development → LM Studio
```

Attention :

les variables Vercel Development sont utilisées notamment par :

```bash
vercel env pull
```

mais ton développement local peut continuer à utiliser ton propre `.env`.

---

# 25. Redéployer Vercel

Après modification des variables :

```text
Deployments
→ Redeploy
```

ou déclencher un nouveau déploiement Git.

Les nouvelles variables seront alors disponibles côté serveur.

---

# 26. Flux final

Nous obtenons :

```text
┌─────────────────────┐
│       Browser       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       Vercel        │
│                     │
│ Frontend            │
│ Backend/API         │
└──────────┬──────────┘
           │
           │ HTTPS
           │ Bearer API KEY
           ▼
┌─────────────────────┐
│    Lightning AI     │
│                     │
│ public endpoint     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│        Nginx        │
│       :8080         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│        vLLM         │
│       :8000         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    Qwen / Llama     │
│      GPU L4         │
└─────────────────────┘
```

---

# 27. Ne jamais appeler Lightning directement depuis le navigateur

Ne pas faire :

```text
Browser
   ↓
Lightning
```

Sinon :

```text
LLM_API_KEY
```

risque de finir dans le JavaScript envoyé au navigateur.

Le flux doit rester :

```text
Browser
↓
Vercel backend
↓
Lightning
```

La clé API reste alors uniquement dans :

```text
Vercel Environment Variables
```

---

# 28. Attention aux variables `NEXT_PUBLIC_*`

Dans une application Next.js, ne jamais faire :

```env
NEXT_PUBLIC_LLM_API_KEY=...
```

car les variables `NEXT_PUBLIC_*` sont destinées à être exposées au navigateur.

Utiliser simplement :

```env
LLM_API_KEY=...
```

---

# 29. Vérifier le streaming

vLLM supporte le streaming OpenAI-compatible.

Tester :

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://xxxxx.lightning.ai/v1",
    api_key="TON_API_KEY",
)

stream = client.chat.completions.create(
    model="Qwen/Qwen3-4B",
    messages=[
        {
            "role": "user",
            "content": "Explique-moi le fonctionnement d'un LLM."
        }
    ],
    stream=True,
)

for chunk in stream:
    if chunk.choices:
        print(
            chunk.choices[0].delta.content or "",
            end="",
            flush=True,
        )
```

Nginx contient :

```nginx
proxy_buffering off;
```

précisément pour éviter de casser ce streaming.

---

# 30. Streaming Vercel

Si ton backend Vercel transmet la réponse du LLM au frontend, il est fortement conseillé de conserver le streaming.

Architecture :

```text
vLLM
 ↓ tokens
Lightning
 ↓
Vercel
 ↓
Browser
```

Cela évite d'attendre que toute la génération soit terminée.

Vercel recommande également le streaming pour les appels backend longs ; ses Functions modernes avec Fluid Compute sont adaptées aux réponses IA longues.

---

# 31. Attention aux cold starts

Si Lightning est configuré pour arrêter le GPU en l'absence d'utilisation :

```text
requête
↓
démarrage GPU
↓
démarrage environnement
↓
chargement modèle
↓
vLLM prêt
↓
réponse
```

La première requête peut être beaucoup plus longue que les suivantes.

Il faut donc prévoir côté application :

```text
IA en cours de démarrage...
```

ou :

```text
Le service IA démarre, veuillez patienter.
```

---

# 32. Ne pas utiliser de timeout trop court

Ton backend doit distinguer :

```text
connection timeout
```

et :

```text
read timeout
```

Par exemple :

```env
LLM_CONNECTION_TIMEOUT=30
LLM_READ_TIMEOUT=600
```

Un modèle peut mettre plusieurs secondes avant le premier token, surtout après un cold start.

---

# 33. Health check

Ton application devrait pouvoir tester :

```text
GET /api/ai/status
```

qui fait derrière :

```text
GET Lightning/v1/models
```

ou un health check équivalent.

Réponse applicative :

```json
{
    "available": true,
    "provider": "openai_compatible",
    "model": "Qwen/Qwen3-4B"
}
```

---

# 34. Automatiser le lancement de vLLM

Une fois le POC validé, ne pas lancer manuellement :

```bash
vllm serve ...
```

à chaque démarrage.

Créer par exemple :

```text
~/vllm/start.sh
```

Contenu :

```bash
#!/usr/bin/env bash

set -e

MODEL="${VLLM_MODEL:-Qwen/Qwen3-4B}"
PORT="${VLLM_PORT:-8000}"

exec vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --api-key "$VLLM_API_KEY"
```

Puis :

```bash
chmod +x ~/vllm/start.sh
```

---

# 35. Utiliser des variables d'environnement Lightning

Au lieu de mettre :

```text
TON_API_KEY
```

dans les scripts, créer un secret Lightning :

```text
VLLM_API_KEY
```

Puis :

```text
VLLM_MODEL=Qwen/Qwen3-4B
```

Le script devient indépendant de la configuration.

---

# 36. Vérifier au démarrage

Tester :

```bash
echo "$VLLM_MODEL"
```

Ne jamais afficher :

```bash
echo "$VLLM_API_KEY"
```

dans des logs de production.

---

# 37. Passer ensuite à un Lightning Deployment

Une fois le Studio parfaitement fonctionnel, Lightning propose de le convertir en véritable Deployment.

Le principe officiel est :

```text
Studio fonctionnel
↓
snapshot
↓
Deployment
```

Le snapshot conserve notamment l'environnement, les paquets et les ports. Lightning prend ensuite en charge lancement, monitoring, autoscaling et cold starts.

---

# 38. Installer le plugin Deployment

Dans ton Studio :

```text
Plugins
→ Deployment
```

Installer le plugin si nécessaire.

Puis :

```text
New Deployment
```

Sélectionner :

```text
Source → Studio
```

---

# 39. Commande du Deployment

Pour une architecture directe sans Nginx :

```bash
vllm serve Qwen/Qwen3-4B \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "$VLLM_API_KEY"
```

Port exposé :

```text
8000
```

Cependant la variante avec reverse proxy reste préférable si le Deployment rend directement le serveur accessible sur Internet.

---

# 40. Variante Deployment avec reverse proxy

Le Deployment peut lancer plusieurs commandes.

Conceptuellement :

```text
vLLM :8000
+
Nginx :8080
```

et seul :

```text
8080
```

est exposé.

---

# 41. Health check du Deployment

Configurer un health check sur :

```text
/health
```

et sur le port public du serveur.

Lightning supporte explicitement les health checks HTTP dans ses Deployments.

---

# 42. Pourquoi le Deployment est intéressant

Le Studio est parfait pour :

```text
développement
tests
POC
debug
```

Le Deployment devient plus approprié pour :

```text
endpoint stable
autoscaling
monitoring
versions
rollback
cold start géré
```

Il n'est pas nécessaire de faire cette étape immédiatement.

---

# 43. Workflow recommandé

## Phase 1

Créer :

```text
Studio
+
L4
+
vLLM
```

Tester localement.

---

## Phase 2

Ajouter :

```text
Nginx
```

Tester :

```text
localhost:8080
```

---

## Phase 3

Exposer :

```text
port 8080
```

avec Lightning.

Tester depuis ton PC.

---

## Phase 4

Configurer Vercel :

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://<endpoint>/v1
LLM_API_KEY=<secret>
LLM_MODEL=Qwen/Qwen3-4B
```

---

## Phase 5

Tester l'application complète :

```text
browser
→ Vercel
→ Lightning
→ vLLM
→ modèle
```

---

## Phase 6

Une fois stable :

```text
Studio
↓
Snapshot Deployment
```

---

# 44. Changement futur de fournisseur

Grâce à ton architecture actuelle, migrer ensuite vers RunPod pourrait simplement devenir :

Avant :

```env
LLM_BASE_URL=https://lightning.example/v1
```

Après :

```env
LLM_BASE_URL=https://runpod.example/v1
```

La logique applicative reste identique.

---

# 45. Configuration finale Vercel

Configuration recommandée :

```env
LLM_PROVIDER=openai_compatible

LLM_BASE_URL=https://TON_ENDPOINT_LIGHTNING/v1

LLM_API_KEY=TON_SECRET

LLM_MODEL=Qwen/Qwen3-4B

LLM_CONNECTION_TIMEOUT=30

LLM_READ_TIMEOUT=600

LLM_STREAMING=true
```

---

# 46. Checklist finale

Avant de considérer l'installation terminée :

- [ ] Studio Lightning créé
- [ ] GPU L4 activé
- [ ] `nvidia-smi` fonctionne
- [ ] vLLM installé
- [ ] modèle téléchargé
- [ ] vLLM démarre sur `8000`
- [ ] `/v1/models` fonctionne
- [ ] `/v1/chat/completions` fonctionne
- [ ] API key activée
- [ ] Nginx installé
- [ ] Nginx expose uniquement `/v1/`
- [ ] Nginx écoute sur `8080`
- [ ] endpoint Lightning créé sur `8080`
- [ ] endpoint testé depuis Internet
- [ ] variables Vercel ajoutées
- [ ] aucune clé dans `NEXT_PUBLIC_*`
- [ ] Vercel redéployé
- [ ] appel Vercel → Lightning fonctionnel
- [ ] streaming testé
- [ ] comportement LLM indisponible testé
- [ ] comportement cold start testé

---

# Résultat attendu

Au terme de cette procédure :

```text
Vercel
   │
   │ OpenAI-compatible HTTP API
   ▼
Lightning AI
   │
   ▼
Nginx
   │
   ▼
vLLM
   │
   ▼
GPU L4
   │
   ▼
Qwen
```

Ton application reste totalement indépendante de Lightning AI.

Elle sait uniquement qu'elle parle à :

```text
une API OpenAI-compatible
```

C'est exactement ce qui permettra ultérieurement de remplacer Lightning par RunPod, Scaleway, un serveur personnel ou n'importe quel autre hébergeur vLLM simplement en modifiant les variables d'environnement.
