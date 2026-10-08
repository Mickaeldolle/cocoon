# Architecture courante de Cocoon

Date de référence : 2026-10-08 (infrastructure Redis retirée du Compose).

Ce document décrit le chemin réel des requêtes dans le MVP. Il complète
[`architecture.md`](architecture.md), qui décrit les décisions générales, et
ne remplace pas la matrice d'accès de [`security/access-matrix.md`](security/access-matrix.md).

## 1. Frontières des composants

```text
Application Expo
  ├─ authentification, assistant, capture, mémoire, personnel ─ HTTPS ─┐
  ├─ notifications et navigation                                      │
  └─ messagerie secrète ─ HTTPS + jeton renforcé ──────────────────────┘
                                                                        ▼
                         FastAPI : auth → services → repositories → SQL
                                      │                 │
                                      ├─ PostgreSQL (cible bêta)
                                      └─ provider LLM/STT privé
                                         (jamais appelé par Expo)
```

L'API est la frontière de confiance. Le mobile peut afficher une proposition
et demander sa confirmation, mais il ne décide ni de l'owner, ni du scope, ni
de l'autorisation d'une mutation. Le provider LLM ne reçoit ni credential, ni
accès direct à la base, au shell ou à la messagerie secrète.

## 2. Chemin commun d'une requête protégée

1. Le mobile envoie un access token de session et, si nécessaire, une clé
   d'idempotence.
2. `auth/dependencies.py` vérifie la session, l'appareil et l'expiration.
3. Le routeur valide le schéma HTTP et obtient `current_user`.
4. Le service métier applique owner, membership, scope, consentement et
   idempotence avant pagination, ranking ou écriture.
5. Le repository exécute la requête SQL avec les contraintes d'accès dans le
   filtre initial.
6. La réponse est sérialisée sans secret, prompt privé ou donnée d'un autre
   compte ; un request ID corrèle les logs sans enregistrer le corps.

## 3. Flux fonctionnels

### Assistant conversationnel

`apps/mobile/app/assistant.tsx` → `assistant/router.py` →
`assistant/service.py`/`assistant/kernel.py` → `LLMProvider` et outils de lecture
bornés → message assistant et propositions éventuelles.

Les outils personnels de `assistant/tools.py` sont en lecture seule : tâches,
agenda autorisé et mémoires accessibles. Une écriture est une proposition
versionnée ; elle est confirmée par une route API séparée et exécutée par le
service commun B02.

### Capture universelle

`apps/mobile/app/home.tsx` → `POST /api/captures/queue` (ou compatibilité) →
capture brute et `Run` persistés → `run_capture_worker` → événements durables
(`capture_persisted`, `claimed`, `understand_started`, `completed` ou `failed`)
→ proposition éventuelle → confirmation B02.

Le mobile consomme les événements avec SSE et `Last-Event-ID`, conserve un
brouillon si le réseau tombe et peut demander l'annulation d'un run. Une
annulation ne supprime pas la capture brute et le worker la revalide avant la
persistance du résultat.

### Mémoire personnelle

Le service mémoire reçoit uniquement des données du compte courant. Il sépare
capture brute et `MemoryItem`, filtre owner/scope avant retrieval et conserve la
provenance. Correction, remplacement et oubli passent par ses règles métier.

### Propositions et exécution

Assistant et capture créent des propositions, puis appellent le même service
d'autorisation/exécution : verrouillage, expiration, owner, version de payload,
idempotence, création de ressource et journalisation. Les ressources métier
(`task`, `grocery_item`, `training`, `note`, événement et rappels) ne sont
créées qu'après confirmation explicite.

### Voix

Le mobile obtient une transcription corrigible via l'API privée, puis réutilise
le pipeline texte. L'audio temporaire est nettoyé côté serveur/mobile ; aucun
audio permanent n'est créé sans consentement. Le fournisseur STT réel et les
tests appareil restent à qualifier.

### Rappels et notifications

Les rappels confirmés produisent des occurrences déterministes et une outbox.
Le worker prend une occurrence avec lease, applique retries et quotas, puis
livre hors transaction. Permission et livraison réelles sur appareil restent à
qualifier.

### Messagerie secrète — périmètre conservé

Les routes `secret` et les écrans de messagerie secrète constituent une
frontière indépendante avec réauthentification renforcée. Elles ne sont pas
injectées dans le contexte assistant, ne sont pas incluses dans les outils et
ne sont pas modifiées par les travaux MVP.

## 4. Matrice KEEP / REFACTOR / REMOVE / REBUILD

| Module | Responsabilité | Décision |
| --- | --- | --- |
| `auth` | comptes, sessions, appareils, tokens | KEEP |
| `assistant` | chat, provider, outils bornés, propositions | KEEP / REFACTOR progressif |
| `neural` | captures, runs, événements, mémoire historique | KEEP / REFACTOR vers services communs |
| `personal` | tâches, courses, entraînements | KEEP |
| `family_spaces` et `conversations` | famille et messagerie standard | KEEP, hors assistant par défaut |
| `secret` | accès et messagerie secrète | KEEP ISOLATED, ne pas modifier |
| `commands` | workers capture/rappel | KEEP / durcir PostgreSQL |
| `mobile/src/services` | clients HTTP et contrats Expo | KEEP / versionner les contrats |
| `hermes-agent` et plans historiques Hermes | référence documentaire | REMOVE FROM RUNTIME / ne pas intégrer |

Les duplications restantes entre routeurs sont limitées aux façades HTTP et aux
adaptateurs de payload ; validation, owner, expiration, idempotence et création
des ressources doivent rester dans les services communs, pas être recopiés
dans chaque routeur.

## 5. Garde-fous et écarts connus

- PostgreSQL concurrent, Ollama/STT/push réels et appareils ne sont pas
  remplacés par les fixtures SQLite ou les mocks.
- Le provider ne peut pas confirmer une proposition ni exécuter une mutation
  directe.
- Les futures compétences et connecteurs devront réutiliser le catalogue
  d'outils et le service de propositions ; aucun shell ou sous-agent générique
  ne doit être ajouté.
- Les lots B01 à B08 restent partiellement qualifiés tant que leurs preuves
  externes indiquées dans `TASKS.md` ne sont pas exécutées.

## 6. Commandes de référence

Depuis la racine du dépôt, l'audit non destructif est :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\audit-reproducibility.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\validate-mvp.ps1
```

Pour l'API, depuis `apps/api`, l'environnement verrouillé et les contrôles
locaux sont :

```powershell
uv sync --locked --extra dev
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check app migrations tests
```

Pour le mobile, depuis `apps/mobile` :

```powershell
npm ci
npm run typecheck
```

Le démarrage Compose, les migrations et les workers sont décrits dans
`README.md` et `docs/deployment.md`. Les commandes d'intégration PostgreSQL,
Ollama, STT, push et appareils nécessitent un environnement dédié et ne sont
pas simulées par ces contrôles locaux.
