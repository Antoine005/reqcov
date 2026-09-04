"""Report writers: HTML, CSV, JSON, Markdown (PR comment / job summary)."""
from __future__ import annotations

import csv
import dataclasses
import json
import os
from typing import Dict, List

from jinja2 import Environment, PackageLoader, select_autoescape

from . import __version__
from .config import Config
from .models import CoverageReport

_env = Environment(loader=PackageLoader("reqcov", "templates"), autoescape=select_autoescape(["html"]))


def write_reports(report: CoverageReport, cfg: Config) -> Dict[str, str]:
    out_dir = os.path.join(cfg.root, cfg.report.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    written: Dict[str, str] = {}
    for fmt in cfg.report.formats:
        if fmt == "html":
            p = os.path.join(out_dir, "index.html")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(render_html(report, cfg))
        elif fmt == "csv":
            p = os.path.join(out_dir, "matrix.csv")
            write_csv(report, p)
        elif fmt == "json":
            p = os.path.join(out_dir, "coverage.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(to_json(report), fh, indent=2)
        elif fmt == "md":
            p = os.path.join(out_dir, "summary.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(render_markdown(report))
        else:
            continue
        written[fmt] = p
    return written


def render_html(report: CoverageReport, cfg: Config) -> str:
    tpl = _env.get_template("report.html")
    return tpl.render(
        title=report.title,
        project=cfg.report.project,
        version=__version__,
        generated_at=report.generated_at,
        git_sha=report.git_sha,
        counts=report.counts(),
        test_pct=report.test_coverage_pct(),
        verified_pct=report.verified_pct(),
        has_results=bool(report.results),
        by_level=report.by_level(),
        findings=sorted(report.findings, key=lambda f: {"error": 0, "warning": 1, "info": 2}[f.severity]),
        unknown_ids=report.unknown_ids,
        orphan_tests=report.orphan_tests,
    )


def write_csv(report: CoverageReport, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "level", "title", "parents", "verification", "req_status", "tests", "test_results", "sources", "coverage_status", "file"])
        for level, rows in report.by_level().items():
            for rc in rows:
                r = rc.requirement
                w.writerow(
                    [
                        r.id,
                        level,
                        r.title,
                        "; ".join(r.parents),
                        r.verification,
                        r.status,
                        "; ".join(f"{t.symbol or t.marker} ({t.file}:{t.line})" for t in rc.tests),
                        "; ".join(f"{res.full_name}={res.status}" for res in rc.results),
                        "; ".join(f"{s.file}:{s.line}" for s in rc.sources),
                        rc.verification_status,
                        f"{r.file}:{r.line}" if r.line else r.file,
                    ]
                )


def to_json(report: CoverageReport) -> Dict:
    return {
        "reqcov": __version__,
        "generated_at": report.generated_at,
        "git_sha": report.git_sha,
        "summary": {
            **report.counts(),
            "test_coverage_pct": round(report.test_coverage_pct(), 2),
            "verified_pct": round(report.verified_pct(), 2),
            "unknown_ids": len(report.unknown_ids),
            "orphan_tests": len(report.orphan_tests),
            "errors": len(report.errors),
            "warnings": len(report.warnings),
        },
        "requirements": [
            {
                "id": rc.requirement.id,
                "level": rc.requirement.level,
                "title": rc.requirement.title,
                "parents": rc.requirement.parents,
                "children": rc.children,
                "verification": rc.requirement.verification,
                "req_status": rc.requirement.status,
                "status": rc.verification_status,
                "tests": [dataclasses.asdict(t) for t in rc.tests],
                "results": [dataclasses.asdict(r) for r in rc.results],
                "sources": [dataclasses.asdict(s) for s in rc.sources],
                "file": rc.requirement.file,
                "line": rc.requirement.line,
            }
            for rc in report.requirements.values()
        ],
        "unknown_ids": [dataclasses.asdict(u) for u in report.unknown_ids],
        "orphan_tests": [dataclasses.asdict(t) for t in report.orphan_tests],
        "findings": [dataclasses.asdict(f) for f in report.findings],
    }


def render_markdown(report: CoverageReport, max_rows: int = 30) -> str:
    c = report.counts()
    pct = report.test_coverage_pct()
    icon = "✅" if not report.errors else "❌"
    lines: List[str] = []
    lines.append("<!-- reqcov -->")
    lines.append(f"## {icon} Requirements coverage: {pct:.1f}%")
    lines.append("")
    lines.append("| Requirements | With test | Verified | Uncovered | Failing | Unknown ids | Orphan tests |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    with_test = sum(1 for rc in report.requirements.values() if rc.has_test)
    lines.append(
        f"| {c['total']} | {with_test} | {c['verified']} | {c['uncovered']} | {c['failing']} | {len(report.unknown_ids)} | {len(report.orphan_tests)} |"
    )
    lines.append("")
    for level, rows in report.by_level().items():
        t = [rc for rc in rows if rc.requirement.verification == "test" and rc.requirement.status != "obsolete"]
        if not t:
            continue
        cov = 100.0 * sum(1 for rc in t if rc.has_test) / len(t)
        lines.append(f"- **{level}**: {cov:.0f}% of {len(t)} testable requirements have a test")
    lines.append("")
    if report.errors:
        lines.append(f"### ❌ {len(report.errors)} error(s)")
        for f in report.errors[:max_rows]:
            loc = f" — `{f.file}:{f.line}`" if f.file and f.line else (f" — `{f.file}`" if f.file else "")
            lines.append(f"- `{f.code}` {f.message}{loc}")
        if len(report.errors) > max_rows:
            lines.append(f"- … {len(report.errors) - max_rows} more")
        lines.append("")
    uncovered = [rc for rc in report.requirements.values() if rc.verification_status == "uncovered"]
    if uncovered:
        lines.append("<details><summary>Uncovered requirements (" + str(len(uncovered)) + ")</summary>")
        lines.append("")
        for rc in uncovered[:max_rows]:
            lines.append(f"- **{rc.requirement.id}** {rc.requirement.title}")
        if len(uncovered) > max_rows:
            lines.append(f"- … {len(uncovered) - max_rows} more")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    if report.warnings:
        others = [w for w in report.warnings if w.code != "UNCOVERED"]
        if others:
            lines.append("<details><summary>Warnings (" + str(len(others)) + ")</summary>")
            lines.append("")
            for f in others[:max_rows]:
                lines.append(f"- `{f.code}` {f.message}")
            lines.append("")
            lines.append("</details>")
            lines.append("")
    lines.append(f"<sub>reqcov {__version__} · {report.generated_at}" + (f" · `{report.git_sha}`" if report.git_sha else "") + "</sub>")
    return "\n".join(lines) + "\n"
