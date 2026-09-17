#!/usr/bin/env python3
"""Build the landing page of the reqcov demo site from the generated reports.

Usage: python .github/scripts/build_demo_index.py <site-dir>

Each sub-directory of <site-dir> is one example report (index.html, matrix.csv,
coverage.json, summary.md). The numbers shown are read from coverage.json, so
the page can never drift from the reports it links to.
"""
from __future__ import annotations

import json
import pathlib
import sys

EXAMPLES = [
    (
        "pytest-project",
        "Python &middot; pytest",
        "A thermostat with SYS &rarr; SRS levels, one requirement deliberately left "
        "without a test and one orphan test.",
    ),
    (
        "ceedling-unity",
        "C &middot; Ceedling / Unity",
        "An embedded frame decoder with HLR &rarr; LLR levels, <code>@implements</code> "
        "markers in the sources and a failing Unity test propagating to its "
        "requirements.",
    ),
    (
        "googletest",
        "C++ &middot; GoogleTest",
        "A ring buffer with one-line requirements and GoogleTest "
        "<code>Suite.Name</code> results.",
    ),
]

CSS = """
:root { --bg:#f7f8fa; --card:#fff; --ink:#1b1f24; --muted:#5b6470; --line:#e3e6ea;
        --ok:#1a7f4b; --warn:#b26a00; --bad:#b3261e; }
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif }
header { padding:34px 28px 26px; border-bottom:1px solid var(--line); background:var(--card) }
header .wrap, main { max-width:900px; margin:0 auto }
header h1 { margin:0 0 6px; font-size:26px; letter-spacing:-.01em }
header p { margin:0; color:var(--muted); max-width:640px }
header .links { margin-top:16px; display:flex; gap:10px; flex-wrap:wrap }
header .links a { text-decoration:none; font-size:13px; font-weight:600; padding:7px 13px;
                  border:1px solid var(--line); border-radius:6px; color:var(--ink); background:var(--card) }
header .links a.primary { background:var(--ink); color:#fff; border-color:var(--ink) }
main { padding:26px 28px 40px }
.note { background:#fffbf0; border:1px solid #f0e2c0; border-radius:8px; padding:12px 14px;
        font-size:13.5px; color:#6b5620; margin-bottom:22px }
.card { display:block; text-decoration:none; color:inherit; background:var(--card);
        border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-bottom:6px }
.card:hover { border-color:#c7ccd3 }
.card h2 { margin:0 0 3px; font-size:16.5px }
.card .lang { color:var(--muted); font-size:12.5px; text-transform:uppercase; letter-spacing:.04em }
.card p { margin:8px 0 12px; color:var(--muted); font-size:13.5px }
.stats { display:flex; gap:20px; flex-wrap:wrap; border-top:1px solid var(--line); padding-top:11px }
.stat .k { color:var(--muted); font-size:11.5px; text-transform:uppercase; letter-spacing:.04em }
.stat .v { font-size:18px; font-weight:600 }
.stat .v.ok { color:var(--ok) } .stat .v.warn { color:var(--warn) } .stat .v.bad { color:var(--bad) }
.files { margin:0 0 20px; padding-left:18px; font-size:12.5px; color:var(--muted) }
.files a { color:var(--muted) }
code { font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
       background:#f0f2f5; padding:1px 4px; border-radius:3px }
footer { padding:22px 28px 40px; color:var(--muted); font-size:12.5px; text-align:center }
footer a { color:var(--muted) }
"""


def tone(pct: float) -> str:
    return "ok" if pct >= 100 else ("warn" if pct >= 80 else "bad")


def card(site: pathlib.Path, slug: str, lang: str, blurb: str) -> str:
    data = json.loads((site / slug / "coverage.json").read_text(encoding="utf-8"))
    s = data["summary"]
    pct = s["test_coverage_pct"]
    stats = [
        ("Requirements", str(s["total"]), ""),
        ("Test coverage", f"{pct:.1f}%", tone(pct)),
        ("Uncovered", str(s["uncovered"]), "bad" if s["uncovered"] else "ok"),
        ("Failing", str(s["failing"]), "bad" if s["failing"] else "ok"),
    ]
    cells = "".join(
        f'<div class="stat"><div class="k">{k}</div>'
        f'<div class="v {c}">{v}</div></div>'
        for k, v, c in stats
    )
    return f"""
  <a class="card" href="{slug}/index.html">
    <div class="lang">{lang}</div>
    <h2>examples/{slug}</h2>
    <p>{blurb}</p>
    <div class="stats">{cells}</div>
  </a>
  <p class="files">Same run, other formats:
    <a href="{slug}/matrix.csv">matrix.csv</a> &middot;
    <a href="{slug}/coverage.json">coverage.json</a> &middot;
    <a href="{slug}/summary.md">summary.md</a> (the pull-request comment)
  </p>"""


def main() -> int:
    site = pathlib.Path(sys.argv[1])
    cards = "\n".join(card(site, *ex) for ex in EXAMPLES)
    version = json.loads(
        (site / EXAMPLES[0][0] / "coverage.json").read_text(encoding="utf-8")
    )["reqcov"]
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>reqcov &mdash; live example reports</title>
<meta name="description" content="Requirements traceability matrices generated by reqcov for Python, C and C++ example projects - the real output, no install required.">
<style>{CSS}</style>
</head>
<body>
<header><div class="wrap">
  <h1>reqcov &mdash; live example reports</h1>
  <p>These are the actual reports reqcov {version} produced for the three example projects in
  the repository, regenerated on every push to <code>main</code>. Nothing to install: open one
  and use the filters, exactly as your team would after a pull request.</p>
  <div class="links">
    <a class="primary" href="https://github.com/Antoine005/reqcov">GitHub repository</a>
    <a href="https://github.com/marketplace/actions/reqcov-requirements-coverage">GitHub Action</a>
    <a href="https://pypi.org/project/reqcov/">PyPI</a>
  </div>
</div></header>
<main>
  <p class="note">Two of these examples fail on purpose &mdash; a requirement without a test, a
  test that fails &mdash; because that is what the tool is for. A green report proves nothing
  until you have seen it go red.</p>
{cards}
</main>
<footer>
  Generated by <a href="https://github.com/Antoine005/reqcov">reqcov</a> {version} &middot; MIT licence
</footer>
</body>
</html>
"""
    (site / "index.html").write_text(html, encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {site / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
