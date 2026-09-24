# `coverage.json` — format

`coverage.json` is reqcov's machine-readable output and the stable interface for anything built
on top of it: the coverage delta (`--baseline`), dashboards, scripts, a hosted history. It is
versioned by its top-level `schema` number.

**Compatibility promise.** Within one `schema` version, keys are only ever *added*. Renaming or
removing a key, or changing what a value means, bumps `schema`. Readers should ignore keys they
do not know. Files written before reqcov 0.3.1 have no `schema` key and are version 1.
`reqcov --baseline` refuses a file with a newer `schema` than it understands.

## Schema 1

| Key | Type | Meaning |
|---|---|---|
| `schema` | int | Format version, `1` |
| `reqcov` | string | reqcov version that wrote the file |
| `generated_at` | string | `YYYY-MM-DD HH:MM UTC` |
| `git_sha` | string | Short commit analysed (empty outside git) |
| `summary` | object | Counts below |
| `requirements` | list | One entry per requirement, below |
| `unknown_ids` | list | Markers citing an id that is not defined (same fields as `tests[]`) |
| `orphan_tests` | list | Test results linked to no requirement (same fields as `results[]`) |
| `findings` | list | `{severity, code, message, file, line}` — severity `error` / `warning` / `info` |
| `delta` | object \| null | Change against a baseline, `null` without `--baseline` / `--base-ref` |

`summary`: `total`, `uncovered`, `covered`, `verified`, `failing`, `skipped`, `n/a` (requirement
counts per status), `test_coverage_pct`, `verified_pct`, `unknown_ids`, `orphan_tests`, `errors`,
`warnings`.

`requirements[]`:

| Key | Type | Meaning |
|---|---|---|
| `id`, `level`, `title` | string | `level` is the id prefix (`SRS` for `SRS-12`) |
| `parents`, `children` | list of ids | Traceability links |
| `verification` | string | `test`, `analysis`, `inspection`, `demonstration`, `review`, `none` |
| `req_status` | string | The requirement's own status (`approved`, `draft`, `obsolete`…) |
| `status` | string | Coverage status: `uncovered`, `covered`, `verified`, `failing`, `skipped`, `n/a` |
| `tests[]` | list | `{req_id, file, line, kind, marker, symbol}` — markers in test files |
| `results[]` | list | `{name, classname, status, file, message}` — matched JUnit results |
| `sources[]` | list | Markers in source files, same fields as `tests[]` |
| `file`, `line` | string, int | Where the requirement is defined (`line` 0 when unknown) |
| `jira` | list of strings | Linked issue keys (since 0.3) |

`delta`: `base_sha`, `base_test_coverage_pct`, `test_coverage_change`, and the lists `added`,
`removed`, `improved`, `regressed`, `other` of `{req_id, title, before, after}`.
