# Matrice d’accès MVP

Cette matrice décrit les frontières appliquées par l’API. Le mobile ne fournit jamais
un `user_id` pour choisir le propriétaire : l’identité vient du token de session.

| Ressource | Propriétaire | Portée | Règle MVP |
| --- | --- | --- | --- |
| `User` / session | compte courant | personnelle | token valide, session non révoquée |
| `PersonalTask`, courses, entraînements | `user_id` | personnelle | lecture et mutation limitées au compte courant |
| `Capture`, `CaptureRun`, événements | `user_id` | personnelle | owner vérifié sur chaque lecture, reprise et annulation |
| `NeuralProposal` | `user_id` | personnelle | confirmation uniquement par l’owner, expiration contrôlée |
| `AssistantProposal` | `user_id` | personnelle | confirmation/annulation uniquement par l’owner |
| `MemoryItem` | `user_id` | personnelle | owner + `owner_type=user` + `scope_type=personal` + état actif |
| `RecurringReminder`, outbox | `user_id` | personnelle | worker et routes filtrés par compte ; contenu push générique |
| `CalendarEvent` interne | `user_id` | personnelle | conflits et lecture limités au compte courant |
| `FamilySpace` et conversations | membership | partagée | hors contexte assistant ; règles de membership dédiées |
| conversations secrètes | membership + step-up | cachée | module séparé, aucun import depuis le contexte assistant |
| consentements | `user_id` | compte courant | version et révocation filtrées par le compte courant |

## Invariants

- Un UUID reçu du mobile est une cible, jamais une preuve de propriété.
- Les requêtes assistant construisent le contexte avec `user_id` côté serveur avant le tri,
  la limite ou l’appel provider.
- Une mutation proposée reste en attente jusqu’à confirmation explicite et revalidation des droits.
- Les fichiers, tokens provider, prompts complets et données secrètes ne sont pas écrits dans
  les journaux applicatifs.
- Toute extension familiale ou externe doit ajouter une portée et un consentement explicites ;
  elle ne peut pas réutiliser le contexte personnel par défaut.
- Les consentements sont versionnés et révocables via `/api/auth/consents`; leur état n’est jamais
  déduit d’un champ fourni par le modèle ou d’un autre compte.
- Les mutations personnelles résolvent désormais la ressource avec `id` et `user_id` dans la même
  requête SQL ; un UUID appartenant à un autre compte est donc traité comme introuvable avant
  tout chargement métier.
