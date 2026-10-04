# Cerveau Hermes multi-outils pour Cocoon

## Résumé

- Conserver Hermes comme runtime privé derrière FastAPI ; Expo ne contacte jamais Hermes, le LLM ni un outil directement.
- Réutiliser les profils Hermes opaques et isolés par compte, mais remplacer le mode « mémoire seule » par un catalogue d’outils Cocoon contrôlé.
- Toute action métier reste une proposition idempotente à confirmer ; Hermes ne crée jamais directement une tâche, un rappel ou une donnée personnelle.

## Changements clés

- Ajouter un pont MCP local `cocoon-personal`, lancé dans le profil Hermes courant. Il identifie le profil via son environnement Hermes, le fait correspondre au seul compte Cocoon autorisé, et communique avec FastAPI via une identité de service interne. Il échoue fermé si le profil, l’identité ou le consentement ne correspondent pas.
- Exposer uniquement les outils personnels suivants :
    - lecture : tâches/rappels, mémoires confirmées, courses, entraînement et agenda interne ;
    - proposition : tâche, rappel, note, article de courses, entraînement et événement d’agenda.
    - Aucun terminal, fichier, navigateur, réseau générique, messagerie, accès familial ou conversation cachée.
- Ajouter les autorisations par source de données dans les réglages Assistant. Tâches et rappels sont activés par défaut ; mémoires, courses, entraînement et agenda sont désactivés jusqu’à consentement. Désactiver une source bloque immédiatement sa consultation sans supprimer les données.
- Ajouter un flux SSE `POST /api/assistant/chat/stream` avec états sûrs, fragments de réponse, propositions et résultat final. L’écran Expo rend la réponse en direct, les activités d’outil sous forme lisible, puis les cartes de confirmation ; le champ est conservé en cas d’échec ou d’annulation.
- Conserver `/api/assistant/chat` pendant la transition, sans repli silencieux de Hermes vers le runtime local. Le runtime local reste activable explicitement par configuration.
- Étendre l’audit serveur : exécution, outil, portée consentie, résultat, proposition, version de compétence et latence, sans journaliser le contenu personnel brut.

## Compétences auto-apprenantes

- Stocker les compétences dans un registre Cocoon versionné et rattaché au compte, avec contenu déclaratif, sources autorisées et outils autorisés.
- Hermes peut créer et activer automatiquement une compétence seulement si la validation prouve qu’elle est strictement en lecture, limitée aux sources déjà consenties, sans URL, code, MCP additionnel, fichier, terminal ni instruction de contournement.
- Toute compétence demandant une mutation, une nouvelle permission ou un outil hors catalogue est mise en quarantaine pour revue superadmin ; elle ne devient jamais active automatiquement.
- Les instructions de compétence et les données lues sont traitées comme non fiables : elles ne peuvent modifier ni consentements, ni politiques, ni limites d’outil.

## Validation

- Tests d’isolation entre deux comptes, refus total des conversations familiales et cachées, et absence de fuite si un profil Hermes est invalide.
- Tests de consentement pour chaque source, y compris révocation immédiate.
- Tests MCP de lecture filtrée, de propositions validées, de confirmation transactionnelle/idempotente et de refus de tout outil non autorisé.
- Tests de quarantaine des compétences générées contenant une mutation, du code, une URL ou une élévation de privilèges.
- Tests SSE mobile/API : progression, streaming, annulation, indisponibilité Hermes et conservation de la saisie.
- Validation réelle : démarrer Hermes en privé avec le pont MCP, vérifier une session persistante, une lecture consentie et une action confirmée sur un development build Expo.

## Hypothèses

- Hermes reste un service privé, protégé par TLS hors boucle locale ; ses jetons et l’identité de service restent exclusivement côté serveur.
- Le pont MCP est un processus local par profil Hermes et ne devient pas une API publique.
- Ce lot exclut e-mail, maison connectée, navigateurs, messageries externes et toute capacité d’exécution système.
