# reqcov — requirements coverage for pull requests

**Codecov, but for your requirements.** reqcov reads the requirements you already keep in your
repository (Markdown, YAML or Doorstop), finds the tests and code that reference them, merges
the JUnit results of your test run, and tells every pull request which requirements are
**uncovered**, **covered**, **verified** or **failing** — then writes the traceability matrix an
auditor asks for (IEC 62304, ISO 26262, EN 50128, DO-178C, IEC 61508, ECSS).

No server, no account, no new editor: a CLI + a GitHub Action.

```text
## ❌ Requirements coverage: 83.3%

| Requirements | With test | Verified | Uncovered | Failing | Unknown ids | Orphan tests |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 5 | 5 | 1 | 0 | 0 | 1 |

- SRS: 75% of 4 testable requirements have a test
- SYS: 100% of 2 testable requirements have a test

### ❌ 1 error(s)
- `COVERAGE` test coverage of requirements 83.3% is below the required 100.0%
```

## How it works

1. **Requirements** live in your repo, one id per requirement (`SYS-1`, `SRS-12`, `LLR-3`…):

   ```markdown
   ## SRS-11 — Over-temperature cut-off
   The controller shall force the heater off when temperature ≥ 35 °C.
   Parent: SYS-2
   Verification: test
   ```

   YAML lists and [Doorstop](https://github.com/doorstop-dev/doorstop) items are also read.

2. **Tests and code** reference ids with a marker — any language, in a comment, a decorator, a
   macro:

   ```python
   @pytest.mark.req("SRS-11", "SYS-2")
   def test_overtemp_cutoff(): ...
   ```

   ```c
   /* @req LLR-12 */
   void test_frame_bad_crc_is_rejected(void) { ... }

   /* @implements LLR-11, LLR-12 */
   frame_status_t frame_validate(const uint8_t *frame, size_t len) { ... }
   ```

   ```cpp
   // @verifies SWR-2
   TEST(RingBuffer, PushOnFullFails) { ... }
   ```

3. **JUnit XML** (pytest, Ceedling, GoogleTest, CTest, Jest, Maven…) turns *covered* into
   *verified* or *failing*.

4. **Rules** in `reqcov.yml` decide what fails the build: minimum coverage, unknown ids,
   orphan tests, mandatory parent links per level, mandatory `@implements` per level.

## Quick start

```bash
pip install reqcov
reqcov init                       # writes reqcov.yml — edit the globs
pytest --junitxml=reports/junit.xml
reqcov check                      # exit 1 on rule violations, writes reqcov-report/
open reqcov-report/index.html
```

`reqcov-report/` contains `index.html` (interactive matrix), `matrix.csv` (auditor-friendly),
`coverage.json` (machine readable) and `summary.md` (the PR comment).

## GitHub Action

```yaml
name: requirements
on: [pull_request, push]
jobs:
  reqcov:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e . pytest && pytest --junitxml=reports/junit.xml
      - uses: reqcov/reqcov@v0
        with:
          junit: reports/junit.xml
```

The action posts (and keeps updating) one sticky comment on the pull request, writes the
summary to the job page, emits annotations on the requirement lines that are uncovered or
failing, and uploads the report directory as an artifact.

## Configuration (`reqcov.yml`)

```yaml
id_pattern: "[A-Z][A-Z0-9_]*-\\d+"   # level = everything before the last dash
requirements: [docs/requirements/**/*.md]
sources:      [src/**/*]              # scanned for @implements markers
tests:        [tests/**/*]            # scanned for @req / @verifies markers
junit:        [reports/*.xml]
markers: [req, requirement, implements, verifies, satisfies, trace]
rules:
  min_test_coverage: 100        # % of testable requirements with ≥ 1 test
  min_verified: null            # % that must be verified (needs junit)
  fail_on_unknown_ids: true
  fail_on_orphan_tests: false
  fail_on_failing_tests: true
  require_parent_for: [SRS]     # levels that must trace up
  require_source_for: []        # levels that must have an @implements
  allow_derived: true           # missing parent = warning (false: error)
report:
  out_dir: reqcov-report
  formats: [html, csv, json, md]
  title: "Software Requirements Traceability"
```

### Requirement metadata

| Field | Markdown body line | YAML key | Values |
|---|---|---|---|
| parents | `Parent: SYS-1, SYS-2` | `parent` / `parents` / `links` | ids |
| verification | `Verification: test` | `verification` | `test` (default), `analysis`, `inspection`, `demonstration`, `none` |
| status | `Status: draft` | `status` (Doorstop: `active: false` → obsolete) | free text; `obsolete` is ignored by rules |
| tags | `Tags: safety, ui` | `tags` | list |

Only requirements with `verification: test` count toward test coverage; the others are shown
as `n/a` in the matrix so the auditor still sees them.

## Examples

- [`examples/pytest-project`](examples/pytest-project) — Python, SYS→SRS levels, one deliberate gap and one orphan test.
- [`examples/ceedling-unity`](examples/ceedling-unity) — C, HLR→LLR, `@implements` in sources, a failing Unity test propagating to two requirements.
- [`examples/googletest`](examples/googletest) — C++, one-line requirements, GoogleTest `Suite.Name` results.

## Status and roadmap

`0.1` — CLI, Markdown/YAML/Doorstop input, marker scanning, JUnit merge, HTML/CSV/JSON/MD
reports, GitHub Action with sticky PR comment. Planned: coverage delta against the base
branch, StrictDoc and ReqIF input, Jira issue links, GitLab CI template, signed PDF export for
audit packages, hosted history and badges.

## License

MIT.
