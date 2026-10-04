# Correctifs du composeur et de la vérification biométrique

Date : 22 septembre 2026.

## Comportement livré

- Un seul bouton partagé par l’accueil et l’assistant, de 48 px : appui court pour envoyer le texte, maintien de 350 ms pour afficher « Transcription audio indisponible. » sans envoyer le brouillon.
- Décision explicite de l’utilisateur : ne pas brancher de fournisseur STT pour le moment. Le composant n’importe plus de recorder et ne demande aucune permission microphone ; aucun fichier, consentement vocal ni appel réseau vocal n’est créé par le maintien.
- Le même bouton conserve l’arrêt de la génération dans l’assistant. Les contrôles supplémentaires de dictée ont été supprimés.
- L’en-tête de l’accueil revient à la ligne à petite largeur et garde les accès profil/rappels visibles.
- L’adaptateur audio conservé pour une activation future lit les fichiers natifs avec `File.arrayBuffer()` plutôt qu’avec `fetch(file://…)`. Le multipart serveur annonce une extension cohérente avec le MIME. Ce code n’est pas activé par le composeur actuel.
- La vérification distingue Face ID indisponible dans Expo Go, absence de biométrie forte Android, annulation et verrouillage temporaire. Les messages précis remontent à l’écran, avec recours au mot de passe du compte et formulaire défilable au-dessus du clavier.
- La preuve de développement est désormais isolée par compte dans SecureStore. Les exigences serveur, le niveau biométrique `strong`, l’interdiction en production et les jetons secrets temporaires restent inchangés.

## Vérifications exécutées

Depuis `apps/mobile` :

- `node --test tests/voice-biometric.test.cjs` : **8 tests réussis**. Les frontières natives sont simulées ; le test du bouton vérifie appui court et maintien sans import du microphone.
- `node node_modules/typescript/bin/tsc --noEmit` : réussi.
- ESLint sur les sept fichiers TypeScript/TSX modifiés et le test : réussi.
- Prettier sur les fichiers modifiés : réussi après formatage.
- `node node_modules/expo/bin/cli export --platform web --output-dir .expo/voice-biometric-export` : export web réussi (989 modules).
- ESLint global : deux erreurs préexistantes `react-hooks/refs` et `react-hooks/purity` dans `src/hooks/use-secret-gesture.ts`, plus avertissements existants. Ce hook n’a pas été modifié.

Depuis `apps/api` :

- `.venv/Scripts/python.exe -m pytest tests/test_secret_access.py tests/test_assistant.py -q` : **41 tests réussis**, deux avertissements de dépréciation FastAPI/Starlette.
- Ruff sur `app/modules/assistant/voice.py` et `tests/test_assistant.py` : réussi.

Interface :

- Navigateur réel sur Metro existant, vues accueil et assistant à **390 × 844**, accueil également à **1280 × 720** : contrôle unique sans chevauchement ; formulaire de mot de passe inspecté à 390 × 844.
- La session navigateur n’était pas authentifiée : envoi et accès secret réels non exercés, boutons d’envoi désactivés. Les captures du navigateur ne prouvent pas le clavier ni les gestes natifs.
- Détecteur Impeccable sur les quatre composants/écrans modifiés : aucun résultat.
- Audit Premium strict des sources UI du monorepo : aucun résultat, rapport `voice-biometric-audit.json`. Le premier parcours sans racines explicites a été interrompu car il parcourait aussi les caches/dépendances ; `voice-biometric-audit.config.json` désigne toutes les sources mobiles de l’application.

## Limites et diagnostic restant

- Configuration locale vérifiée sans exposer les secrets : environnement development, adaptateur biométrique de développement activé, STT non configuré.
- Aucun téléphone n’a été piloté. L’erreur biométrique exacte et le type d’appareil/Expo Go restent attendus pour confirmer la cause de l’incident utilisateur. Les corrections de disponibilité et de messages ne constituent pas une preuve de déverrouillage réel.
- Le fournisseur STT reste volontairement absent conformément à la décision utilisateur.
