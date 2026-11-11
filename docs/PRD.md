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

Aucun. reqcov est un outil libre (MIT), sans offre payante : le CLI et l'Action sont le produit
entier. La piste « reqcov Cloud » (open core avec historique hébergé, badges, PDF signé, offres
Team/Compliance) a été abandonnée en septembre 2026. Les fonctions qui étaient réservées à cette
offre (historique, baselines) sont, si elles se font, faites dans l'outil libre.

## 7. Distribution

GitHub Marketplace ; articles « matrice IEC 62304 depuis GitHub Actions en 15 minutes » ;
proposition de couche CI aux mainteneurs de StrictDoc et Doorstop ; Show HN ; r/embedded,
r/medicaldevices, r/QualityAssurance.

## 8. Roadmap

- 0.2 (livrée) : delta de couverture vs branche de base ; template GitLab CI. StrictDoc `.sdoc`
  reporté sans date.
- 0.3 (livrée) : ReqIF import/export ; liens Jira ; export PDF (non signé).
- 0.3.1 : adoption sur un projet existant (DOORS + Jira + tests existants) : export ReqIF
  multi-modules, identifiants ReqIF conservés à l'export, aide sur les clés Jira citées comme
  exigences, format `coverage.json` versionné, guide d'adoption progressive (cliquet).
- En discussion (issue #4) : exigences par périmètre (une spec par feature, façon GitHub Spec
  Kit, avec des identifiants `FR-001` qui se répètent) et détection de dérive (une exigence dont
  le texte change alors que ses tests restent verts), dans l'outil libre.

Écarté volontairement, pour garder l'outil ouvert et facile à adopter :
- appels à l'API Jira depuis la CI (jeton, réseau, différences Cloud / Data Center, résultat non
  reproductible depuis le commit) ;
- marqueurs posés automatiquement ou clés Jira acceptées comme marqueurs (un lien deviné ou
  indirect gonfle la couverture, ce qu'un auditeur ne doit jamais trouver) ;
- toute dépendance envers un service hébergé : les outils tiers consomment `coverage.json`, dont
  le format est versionné et documenté.

## 9. Critères de succès

- 100 étoiles GitHub et 3 dépôts externes utilisant l'Action.
- Des contributions externes (issues, pull requests) traitées dans la semaine.
