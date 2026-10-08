# Rédiger `docs/MEMORY_PLAN.md` — Mémoire personnelle fiable et pertinente

## 1. Objectif du document et décisions retenues

Créer un document de référence suffisamment précis pour guider les futures implémentations, sans modifier le code dans ce travail documentaire.

Le document distinguera systématiquement :

- le fonctionnement actuellement constaté ;
- les comportements cibles ;
- les mécanismes à construire ;
- les critères de validation ;
- les évolutions facultatives.

**Décisions retenues :**

- Mémoire exclusivement personnelle pour cette première version.
- Confirmation obligatoire avant activation d’un souvenir extrait automatiquement.
- Recherche et embeddings locaux par défaut.
- Modèle conversationnel configurable indépendamment du modèle d’embedding.
- Réutilisation de FastAPI, PostgreSQL, des propositions, des workers et des routes existantes.
- Conversation directe conservée comme parcours principal.
- Partage familial, profilage comportemental et consolidation autonome exclus de la première livraison.

Le document signalera les divergences avec `VISION.md` et `TASKS.md`, notamment sur le calendrier des embeddings. Leur harmonisation sera identifiée comme une tâche documentaire ultérieure ; cette demande produira uniquement `MEMORY_PLAN.md`.

## 2. Objectifs, architecture et mécanismes à détailler

### Objectifs observables

L’assistant doit pouvoir :

- retrouver un souvenir ancien malgré une reformulation ;
- poursuivre une conversation longue sans perdre ses décisions importantes ;
- distinguer une préférence générale d’une contrainte de projet ;
- reconnaître un changement, une exception et une contradiction ;
- expliquer la provenance d’une information ;
- demander une précision lorsque les sources sont ambiguës ;
- répondre honnêtement lorsqu’aucune information fiable n’est disponible ;
- oublier une information sans la réintroduire par ses données dérivées.

La mémoire enrichit le contexte du modèle ; elle ne constitue ni un entraînement de ses poids ni une garantie de raisonnement correct.

### Séparer les responsabilités

| Élément                       | Responsabilité                                                                |
| ----------------------------- | ----------------------------------------------------------------------------- |
| Historique et captures        | Conserver les sources selon leur politique de rétention                       |
| Mémoire de travail            | Maintenir le sujet, les options, décisions provisoires et questions ouvertes  |
| Mémoire durable               | Conserver les informations utiles et confirmées                               |
| Épisodes                      | Décrire les événements et décisions significatifs avec leurs dates            |
| Préférences de fonctionnement | Adapter le style et la collaboration, dans les limites des règles applicables |
| Sources métier                | Fournir l’état actuel des tâches, événements et projets                       |

Les résumés seront des représentations dérivées et reconstructibles, jamais des sources plus fiables que les éléments dont ils proviennent.

### Boucle de lecture

Décrire le parcours suivant :

1. Authentifier l’utilisateur et vérifier les consentements.
2. Identifier le contexte courant à partir de la conversation et des références de projet disponibles.
3. Rechercher uniquement dans les données autorisées et applicables.
4. Combiner recherche exacte, plein texte et recherche sémantique.
5. Écarter les résultats insuffisamment pertinents et les doublons.
6. Construire un contexte limité contenant types, dates, portée et références.
7. Générer la réponse avec le provider existant.

La sélection sera bornée **après recherche dans le corpus autorisé**, sans présélection des seuls 100 souvenirs récents.

### Boucle d’apprentissage

Décrire le parcours suivant :

1. Extraire des candidats à partir des déclarations de l’utilisateur.
2. Valider leur structure, provenance et admissibilité.
3. Comparer avec les souvenirs existants.
4. Proposer création, complément ou remplacement.
5. Attendre la confirmation.
6. Persister transactionnellement et préparer l’indexation.
7. Indexer en arrière-plan avec reprise après erreur.

Une réponse générée par l’assistant ne pourra pas servir de preuve indépendante pour confirmer sa propre affirmation.

### Structure des souvenirs

Prévoir une extension progressive de `MemoryItem`, en conservant les données existantes :

- sujet ou entité concernée ;
- propriété et valeur lorsque l’information se prête à une représentation structurée ;
- type d’information et forme de mémoire ;
- portée personnelle, projet ou conversation ;
- origine explicite, observée ou inférée ;
- références aux sources et aux dérivations ;
- dates d’observation et de validité ;
- état et liens de remplacement.

Les souvenirs anciens resteront consultables sans classification inventée ni activation supplémentaire. Les champs manquants seront renseignés progressivement.

Le score de confiance sera décrit comme un indicateur interne, distinct de la confirmation utilisateur et de la vérité objective.

### Contradictions et temporalité

Comparer propriétaire, sujet, propriété, portée et période avant tout remplacement.

Distinguer répétition, complément, changement explicite, contradiction et exception temporaire. Une similarité de texte ou une catégorie commune ne suffira pas.

Conserver les versions historiques pour répondre aux questions sur les décisions passées. Une contradiction ambiguë produira une proposition de clarification, sans remplacement automatique.

### Oubli et consentement

Distinguer :

- désactivation de la consultation mémoire ;
- oubli d’un souvenir pour l’assistant ;
- effacement des sources conservées.

L’oubli devra invalider le souvenir, ses embeddings, ses résumés dérivés et les contextes mis en cache. Les sources concernées ne devront pas le réactiver automatiquement lors d’une reconstruction.

Une nouvelle demande explicite de mémorisation pourra produire une nouvelle proposition à confirmer. La politique de sauvegarde et de restauration devra préserver les demandes d’oubli.

## 3. Technologies, interfaces et exploitation

### Technologies retenues

- **FastAPI, Pydantic, SQLAlchemy et Alembic** : conserver la pile existante.
- **PostgreSQL** : stockage canonique, transactions, versions et recherche plein texte.
- **Recherche plein texte française**, avec traitement complémentaire des noms et termes techniques. [Documentation PostgreSQL](https://www.postgresql.org/docs/current/textsearch-controls.html).
- **pgvector** : recherche sémantique locale, avec recherche exacte au départ ; index approximatifs uniquement après mesure.
- **Ollama `/api/embed`** : adaptateur d’embedding séparé du provider conversationnel.
- **`qwen3-embedding:0.6b`** : modèle initial proposé pour qualification locale, sans téléchargement ni installation dans ce travail. La famille propose des capacités multilingues. [Catalogue officiel](https://ollama.com/library/qwen3-embedding).

Versionner modèle, dimension, empreinte du contenu et configuration d’embedding. Ne jamais comparer des vecteurs issus de configurations incompatibles.

La fusion des classements utilisera une méthode déterministe de type **Reciprocal Rank Fusion**, puis des règles de portée, validité et diversité. Les seuils de pertinence seront calibrés sur le corpus, sans constante universelle présentée comme fiable.

### Interfaces et compatibilité

- Conserver les routes existantes de consultation, correction, oubli et confirmation.
- Prévoir pagination et filtres pour consulter l’ensemble des souvenirs.
- Ajouter progressivement provenance, validité et portée aux réponses API.
- Remplacer en interne les simples chaînes de contexte par des références structurées.
- Préserver le contrat de conversation et le streaming ; rendre les nouveaux champs optionnels pour les anciens clients.
- Ne jamais accepter l’identité ou les permissions proposées par le modèle.

### Traitements et supervision

Prévoir des traitements durables et idempotents pour indexation, réindexation et invalidation, en réutilisant les conventions de workers existantes.

Si les embeddings sont indisponibles, utiliser le plein texte et signaler le mode dégradé dans les diagnostics internes. La génération conversationnelle doit rester disponible.

Mesurer latence, files d’attente, échecs, volume de contexte et résultats de recherche. Les journaux courants ne contiendront pas le texte privé des souvenirs ; toute inspection détaillée devra être protégée.

## 4. Lots, validation et limites

### Ordre de réalisation

| Lot                                | Livrable et condition de sortie                                                                                                  |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **M0 — Référence**                 | Corpus fictif, mesures initiales et cartographie des chemins de mémoire                                                          |
| **M1 — Fiabilité**                 | Suppression du plafond de présélection, pertinence minimale, déduplication globale, faux conflits corrigés, provenance transmise |
| **M2 — Continuité**                | Mémoire de travail, portée projet et versions temporelles validées                                                               |
| **M3 — Recherche hybride**         | Embeddings locaux, indexation durable et gain mesuré face au plein texte                                                         |
| **M4 — Contrôle et qualification** | Oubli propagé, consentements, concurrence PostgreSQL et parcours utilisateur vérifiés                                            |

Chaque lot précisera ses dépendances, changements de données, compatibilité, retour arrière et preuves attendues. Les migrations ne supprimeront pas les sources existantes ; les index dérivés pourront être reconstruits.

### Scénarios de validation

Utiliser des corpus de 10, 100, 500 et 1 000 souvenirs, avec tests sur PostgreSQL pour les fonctions spécifiques à cette base.

Couvrir :

- souvenir ancien et reformulation ;
- informations absentes ou hors sujet ;
- préférences compatibles ;
- changement et exception temporaire ;
- contraintes différentes entre projets ;
- continuité entre sessions ;
- provenance correcte ;
- oubli, reconstruction et restauration ;
- révocation de consentement ;
- séparation entre comptes ;
- confirmations concurrentes et reprise de worker ;
- panne du service d’embedding.

Mesurer séparément extraction, recherche et utilisation par le modèle : précision, rappel à cinq résultats, bruit injecté, faux remplacements, abstention, latence et utilité perçue.

Aucune livraison ne sera déclarée qualifiée sur la seule base de tests SQLite ou de réponses simulées. La recherche hybride ne deviendra le mode par défaut qu’après démonstration de son bénéfice et validation des garanties d’isolation et d’oubli.

### Limites et évolutions proposées

Documenter les erreurs d’extraction, pertes dues aux résumés, ambiguïtés temporelles, limites du modèle, coût matériel, injection d’instructions dans les sources et risque de renforcement d’hypothèses.

Prévoir comme évolutions distinctes : consolidation d’épisodes, révision proposée des souvenirs vieillissants, relations simples entre entités et partage familial explicitement autorisé.

Ne pas introduire de base graphe, Redis, agents spécialisés ou entraînement personnalisé dans les premiers lots.

## 5. Mise en œuvre au 6 octobre 2026

À la suite de la demande de mise en œuvre, ce plan sert maintenant de référence à l'implémentation backend. Le périmètre et les décisions ci-dessus sont conservés.

| Lot | État et preuve disponible |
| --- | --- |
| M0 | Corpus synthétiques de 10, 100, 500 et 1 000 souvenirs et comparaison lexicale avec l'ancienne présélection ; pas encore d'évaluation de l'utilité par des utilisateurs. |
| M1 | Recherche dans le corpus autorisé, déduplication globale, contexte structuré, remplacement conservateur et provenance implémentés et testés localement. |
| M2 | Continuité extractive, options provisoires, portée projet et accès aux versions historiques implémentés. La synthèse sémantique de conversation et le suivi automatique de résolution des questions restent des évolutions. |
| M3 | Adaptateur Ollama, indexeur durable et recherche hybride pgvector implémentés, désactivés par défaut. Gain sémantique réel et performances à qualifier avant activation. |
| M4 | Consentements, propagation de l'oubli et dépendances des réponses implémentés et testés localement. Qualification PostgreSQL/pgvector, fournisseur réel, sauvegarde/restauration et parcours utilisateur encore requise. |

Installation, configuration, migrations et retour arrière : [MEMORY_SETUP.md](MEMORY_SETUP.md). Résultats et limites de validation : [MEMORY_IMPLEMENTATION.md](validation/MEMORY_IMPLEMENTATION.md).

Les tests locaux ne constituent pas une qualification de production. La migration et les installations optionnelles n'ont pas été appliquées à l'environnement Supabase personnel. L'interface existante reste compatible ; les nouvelles métadonnées et la pagination sont disponibles dans l'API sans nouveau parcours mobile dédié.
