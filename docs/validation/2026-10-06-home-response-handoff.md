# Attente de la première réponse sur l’accueil — 6 octobre 2026

## Comportement

L’envoi depuis l’accueil active immédiatement l’orbe, ferme le clavier et affiche « Votre assistant prépare sa réponse… ». Le flux SSE existant s’exécute sur cet écran. La navigation attend l’événement de réponse complète, puis transmet l’échange terminé en mémoire, avec ses suggestions et propositions de souvenir. L’écran assistant affiche cet échange sans le renvoyer ; son historique canonique reste chargé depuis l’API et évite les doublons par clé d’envoi et identifiant de réponse.

La transmission est limitée au compte et retirée du cache à l’ouverture de la conversation (expiration de secours après une minute). L’URL contient uniquement une clé opaque. Le catalogue et le modèle par défaut reprennent le contrat existant ; aucune nouvelle route API, dépendance ou publication.

L’action d’envoi devient un arrêt. Une erreur ou une annulation conserve le brouillon ; la tentative suivante du même texte conserve la clé d’idempotence. Le départ de l’accueil annule le flux ; une réponse tardive ne déclenche pas de navigation. Le changement de compte ou la révocation de l’accès invalide également la génération locale. Un verrou synchrone empêche deux envois simultanés.

## Vérification

- TypeScript, ESLint ciblé et formatage : succès.
- Suite mobile : 30 tests réussis, dont cinq nouveaux tests pour l’attente de la réponse complète, l’annulation pendant le chargement des modèles, une réponse tardive après annulation, la conservation de la clé lors d’une reprise, et l’isolation du cache par compte avec absence de modèle disponible.
- Export web de production : succès.
- Navigateur réel avec API locale simulée : accueil visible pendant la génération, statut d’attente et bouton d’arrêt, ouverture automatique après réponse avec un seul exemplaire du message, absence de texte privé dans l’URL, arrêt et erreur conservant le brouillon.
- Capture de l’état d’attente : `C:/Users/dolle/.codex/visualizations/2026/10/06/01a11032-0f0d-7491-902b-5ba4254424d9/home-waiting-reply.png`.

La réponse de test et les jetons sont fictifs. Aucun fournisseur LLM réel ni appareil iOS/Android n’a été exercé pour ce changement.
