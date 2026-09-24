# Changelog

## 0.3.1 — 2026-09-24
- ReqIF: `reqif.id_prefix` also takes a mapping `{specification name: prefix}`, so a DOORS
  export holding several modules (each numbered from 1) gives `SYS-1`, `SRS-1`...
- ReqIF export keeps the SPEC-OBJECT identifiers of requirements that were read from ReqIF,
  so the requirements tool can match its own objects when importing the coverage back.
- `UNKNOWN_ID` on a Jira key (`@req THERM-42`) names the requirements linked to that issue.
- `coverage.json` carries `"schema": 1`; its format and compatibility rules are documented in
  `docs/coverage-json.md`. `--baseline` refuses a file written with a newer schema.
- README: "Adopting reqcov on an existing project" (DOORS + Jira + existing tests).
- Fix: the coverage delta no longer lists every tested requirement as "covered → verified"
  when the base was analysed without test results (the Action's pull-request comparison):
  unless both sides have results, only gaining or losing a test is a change.

## 0.3.0 — 2026-09-24
- ReqIF import: `.reqif` files and `.reqifz` archives from DOORS, Polarion, codebeamer, Jama,
  Enterprise Architect... are read like any other requirement file. Attributes are matched by
  name (`ReqIF.ForeignID`, `ReqIF.Name`, `ReqIF.Text`, `Verification Method`, `Status`...),
  SPEC-RELATIONs become parent links, chapter headings are skipped. New `reqif:` settings:
  `id_prefix` (DOORS exports the absolute number: `SRS-` + `12`), `id_attribute`,
  `parent_end`, `relation_types`.
- ReqIF export: report format `reqif` writes `requirements.reqif` (valid against the OMG
  schema) with one specification per level, parent relations and the coverage of the run as
  `reqcov.*` attributes, ready to import back into the requirements tool.
- PDF export: report format `pdf` writes `matrix.pdf`, an A4 audit document with the summary,
  coverage by level, findings, delta, a sign-off table and the full matrix. No new dependency.
- Jira links: a `Jira:` (or `Issue:`, `Ticket:`) field on a requirement lists issue keys;
  with `jira.url` set they become links in the HTML report and the PR comment. Keys are also
  in `matrix.csv` (new last column `jira`), `coverage.json`, the PDF and the ReqIF export.
- `reqcov init` and the default requirement globs include `docs/requirements/**/*.reqif`.

## 0.2.0 — 2026-09-04
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
