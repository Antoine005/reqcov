# An IEC 62304 traceability matrix from GitHub Actions in 15 minutes

*Published 2026-09-04. Also on dev.to.*

If you ship software under IEC 62304, ISO 26262, DO-178C or EN 50128, you already know the
drill before an audit: someone opens Excel, lists every requirement, and hunts through the
test suite for the test that proves each one. It takes days, it is stale the moment it is
finished, and nobody trusts it, least of all the auditor.

The information was in Git the whole time. Requirements are in Markdown, tests reference
them in their names or comments, CI runs the tests and knows which ones passed. What is
missing is a tool that reads all three and writes the matrix. That is what reqcov does, on
every pull request.

## What you end up with

Every pull request gets one comment:

```text
## ❌ Requirements coverage: 83.3% (▼ -8.3% vs a1b2c3d)

| Requirements | With test | Verified | Uncovered | Failing | Unknown ids | Orphan tests |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 5 | 5 | 1 | 0 | 0 | 1 |

### ❌ 1 error(s)
- COVERAGE test coverage of requirements 83.3% is below the required 100.0%

### Changes vs base
- Regressed (1): SRS-13 covered → uncovered
```

and a workflow artifact with `index.html` (the interactive matrix), `matrix.csv` (what the
auditor asked for) and `coverage.json`. The merge is blocked while a requirement is uncovered
or a linked test fails.

## Step 1: give each requirement an id (5 minutes)

Put your requirements in `docs/requirements/SRS.md`. One heading per requirement, an id, and
optionally a parent and a verification method:

```markdown
## SRS-11 — Over-temperature cut-off
The controller shall force the heater off when temperature ≥ 35 °C.
Parent: SYS-2
Verification: test

## SRS-12 — Setpoint range
The setpoint shall be limited to 5–30 °C.
Parent: SYS-1

## SRS-14 — Firmware version string
The firmware shall expose its version over the service port.
Verification: inspection
```

The id prefix is the level. `SYS` requirements trace to `SRS` requirements through the
`Parent:` line, which is what a 62304 assessor means by "software requirements shall be
traceable to system requirements". `Verification: inspection` means no test is expected, so
SRS-14 appears in the matrix as n/a instead of dragging coverage down.

Already using YAML, or [Doorstop](https://github.com/doorstop-dev/doorstop)? Both are read
as-is.

## Step 2: mark the tests (5 minutes)

Any language, any test framework. A marker is a word like `@req` or `@verifies` followed by
ids, in a comment or a decorator:

```python
@pytest.mark.req("SRS-11", "SYS-2")
def test_overtemp_cutoff():
    ...
```

```c
/* @req LLR-12 */
void test_frame_bad_crc_is_rejected(void) { ... }
```

```cpp
// @verifies SWR-2
TEST(RingBuffer, PushOnFullFails) { ... }
```

Optional but useful for design-level traceability: `/* @implements LLR-12 */` above the
function that implements it.

## Step 3: the workflow (5 minutes)

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
      - uses: Antoine005/reqcov@v0
        with:
          junit: reports/junit.xml
```

Run `pip install reqcov && reqcov init` once to write `reqcov.yml`, adjust the globs, commit.
Open a pull request. Done.

## What the auditor gets

`matrix.csv` has one row per requirement: id, level, title, parents, verification method,
linked tests with file and line, test results, implementing source locations, and the
resulting status. It is generated from the commit under review, so it is reproducible: check
out the tag, run `reqcov report`, get the same file. That reproducibility is the argument
that ends most "how do we know this matrix is current" conversations.

## What it does not do

It does not edit requirements, manage risks (ISO 14971) or sign documents. It reads what you
already have. If you need requirement authoring, keep StrictDoc or Doorstop and add reqcov
as the CI layer.

## Try it

- Repository and examples: https://github.com/Antoine005/reqcov
- `pip install reqcov`
- Three worked examples: pytest, Ceedling/Unity (C), GoogleTest (C++)

If your team would use hosted history, coverage badges and a signed PDF for the audit
package, tell me: https://tally.so/r/Me4K28.
