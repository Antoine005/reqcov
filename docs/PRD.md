# reqcov — Product Requirements Document (v0.1)

## 1. Problème

Les équipes de 3 à 30 développeurs qui livrent du logiciel réglementé (IEC 62304 médical,
ISO 26262 automobile, EN 50128 ferroviaire, DO-178C aéronautique, IEC 61508 industriel, ECSS
spatial) doivent démontrer que chaque exigence est implémentée et vérifiée par un test. Elles
ont déjà tout dans Git et en CI, mais la matrice de traçabilité est refaite à la main dans
Excel avant chaque audit, les outils du marché sont soit trop chers (Jama, DOORS, Polarion :
« six chiffres par an »), soit des outils bureau par utilisateur (ReqView 440–600 $/utilisateur/an),
soit open source sans intégration CI ni rapport (Doorstop, StrictDoc, rmtoo).

## 2. Proposition

« Codecov pour les exigences » : un CLI + une GitHub Action qui, à chaque pull request,
calculent la couverture exigences → tests → résultats, commentent la PR, bloquent la fusion
sous un seuil, et produisent la matrice de traçabilité prête pour l'audit.

Principes : pas d'éditeur d'exigences (on lit ce que l'équipe a déjà), pas de serveur pour
commencer, tout est reproductible et versionné avec le commit — ce qu'un auditeur veut.

## 3. Utilisateurs

- **Tech lead / responsable qualité logiciel** d'une PME réglementée (acheteur).
- **Développeur** qui veut savoir dans la PR ce qu'il lui reste à couvrir (utilisateur).
- **Auditeur / évaluateur** qui reçoit `matrix.csv` et `index.html` (lecteur).

## 4. Périmètre v0.1 (livré)

- Entrées : Markdown (titres, gras, listes), YAML (liste, dict par id), items Doorstop.
- Marqueurs : `@req`, `@verifies`, `@implements`… dans tout langage ; symboles détectés pour
  Python, C/Unity, GoogleTest, Rust, JS/TS, Java/C#, Go.
- Résultats : JUnit XML ; statuts uncovered / covered / verified / failing / skipped / n/a.
- Règles : couverture minimale, ids inconnus, tests orphelins, parents obligatoires par niveau,
  `@implements` obligatoire par niveau, tests en échec.
- Sorties : HTML interactif, CSV, JSON, Markdown ; annotations et job summary GitHub ;
  commentaire de PR persistant ; artefact de workflow.

## 5. Hors périmètre v0.1

Édition d'exigences, gestion des risques (ISO 14971), signatures électroniques, hébergement.

## 6. Modèle économique

Open core. Le CLI et l'Action restent MIT (adoption, SEO, crédibilité). La valeur payante est
« reqcov Cloud » : historique et delta de couverture par PR, badges, tableau multi-dépôts,
export PDF signé et horodaté pour le dossier d'audit, intégration Jira/GitLab.

- Gratuit : dépôts publics.
- Team 29 €/mois : jusqu'à 5 dépôts privés, historique 12 mois, PDF.
- Compliance 99 €/mois : dépôts illimités, ReqIF/Jira, baselines, rapport signé.

Objectif 12 mois : 20–40 équipes payantes (800–2 000 €/mois). Facturation via GitHub
Marketplace (pas de Stripe à gérer au départ).

## 7. Distribution

GitHub Marketplace ; articles « matrice IEC 62304 depuis GitHub Actions en 15 minutes » ;
proposition de couche CI aux mainteneurs de StrictDoc et Doorstop ; Show HN ; r/embedded,
r/medicaldevices, r/QualityAssurance.

## 8. Roadmap

- 0.2 : delta de couverture vs branche de base ; StrictDoc `.sdoc` ; template GitLab CI.
- 0.3 : ReqIF import/export ; liens Jira ; export PDF.
- 0.4 : reqcov Cloud (historique, badges, multi-dépôts) — première offre payante.

## 9. Critères de succès

- 30 inscrits sur la liste d'attente ou 5 « je paierais » avant 0.2.
- 100 étoiles GitHub et 3 dépôts externes utilisant l'Action avant 0.4.
- Arrêt si < 5 équipes payantes 6 mois après 0.4.
