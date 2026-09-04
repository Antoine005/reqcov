# Changelog

## 0.2.0 — unreleased
- Coverage delta against a baseline: `--base-ref <git ref>` analyses the ref in a temporary
  worktree, `--baseline coverage.json` reuses a previous run. The PR comment headline shows the
  change, a "Changes vs base" section lists regressed / improved / new / removed requirements,
  and `coverage.json` carries a `delta` object.
- New rule `fail_on_coverage_drop` (default false): `REGRESSION` and `COVERAGE_DROP` become
  errors instead of warnings.
- Action: `compare-base` (default true) compares pull requests against their base commit;
  `base-ref` overrides the ref.
- GitLab CI template in `examples/gitlab-ci.yml`.

## 0.1.0 — 2026-09-04
- First release: CLI (`check`, `report`, `list`, `init`), Markdown/YAML/Doorstop requirements,
  marker scanning in any language, JUnit merge, HTML/CSV/JSON/Markdown reports, composite
  GitHub Action with sticky PR comment, annotations and artifact upload.
