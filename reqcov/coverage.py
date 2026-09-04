"""Build the coverage model and evaluate rules."""
from __future__ import annotations

import datetime as _dt
import subprocess
from typing import Dict, List

from .config import Config
from .files import find_files
from .junit import load_results, match_results
from .links import scan_files
from .models import CoverageReport, Finding, Reference, RequirementCoverage, TestResult
from .requirements import load_requirements


def _git_sha(root: str) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:  # pragma: no cover
        return ""


def analyze(cfg: Config, evaluate: bool = True) -> CoverageReport:
    findings: List[Finding] = []
    root = cfg.root

    req_files = find_files(root, cfg.requirements, cfg.exclude)
    if not req_files:
        findings.append(Finding("error", "NO_REQUIREMENTS", f"no requirement files matched {cfg.requirements}"))
    requirements = load_requirements(root, req_files, cfg.id_pattern, findings)

    # don't scan requirement files themselves as sources/tests
    src_files = [f for f in find_files(root, cfg.sources, cfg.exclude) if f not in req_files]
    test_files = [f for f in find_files(root, cfg.tests, cfg.exclude) if f not in req_files]
    src_set = set(src_files)
    test_files = [f for f in test_files if f not in src_set]  # tests win over sources only if not both

    refs = scan_files(root, test_files, "test", cfg.markers, cfg.id_pattern)
    refs += scan_files(root, src_files, "source", cfg.markers, cfg.id_pattern)

    # junit results often live under build/ — never apply the exclude list to them
    results = load_results(root, find_files(root, cfg.junit, ())) if cfg.junit else []

    cov: Dict[str, RequirementCoverage] = {rid: RequirementCoverage(requirement=r) for rid, r in requirements.items()}
    unknown: List[Reference] = []
    for ref in refs:
        rc = cov.get(ref.req_id)
        if rc is None:
            unknown.append(ref)
            continue
        if ref.kind == "test":
            rc.tests.append(ref)
        else:
            rc.sources.append(ref)

    # parent / child relationships
    for rc in cov.values():
        for p in rc.requirement.parents:
            if p in cov:
                cov[p].children.append(rc.requirement.id)
            else:
                rc.unknown_parents.append(p)

    # test results
    matched_result_ids = set()
    for rc in cov.values():
        seen = set()
        for t in rc.tests:
            for res in match_results(t.symbol, t.file, results):
                key = id(res)
                if key not in seen:
                    seen.add(key)
                    rc.results.append(res)
                    matched_result_ids.add(key)
    referenced_symbols = {r.symbol.split(".")[-1] for r in refs if r.kind == "test" and r.symbol}
    orphan_tests = [
        r for r in results if id(r) not in matched_result_ids and r.name.split("[")[0] not in referenced_symbols
    ]

    report = CoverageReport(
        requirements=cov,
        references=refs,
        results=results,
        findings=findings,
        unknown_ids=unknown,
        orphan_tests=orphan_tests,
        generated_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        git_sha=_git_sha(root),
        title=cfg.report.title,
    )
    if evaluate:
        evaluate_rules(report, cfg)
    return report


def evaluate_rules(report: CoverageReport, cfg: Config) -> None:
    rules = cfg.rules
    f = report.findings

    for ref in report.unknown_ids:
        f.append(
            Finding(
                "error" if rules.fail_on_unknown_ids else "warning",
                "UNKNOWN_ID",
                f"{ref.req_id} referenced by {ref.symbol or 'marker'} but not defined",
                ref.file,
                ref.line,
            )
        )

    for rc in report.requirements.values():
        r = rc.requirement
        for p in rc.unknown_parents:
            f.append(Finding("error", "UNKNOWN_PARENT", f"{r.id} traces to undefined parent {p}", r.file, r.line))
        if r.level in rules.require_parent_for and not r.parents and r.status != "obsolete":
            sev = "warning" if rules.allow_derived else "error"
            f.append(Finding(sev, "DERIVED", f"{r.id} has no parent requirement (derived?)", r.file, r.line))
        if r.level in rules.require_source_for and not rc.sources and r.status != "obsolete":
            f.append(Finding("error", "NO_SOURCE", f"{r.id} is not implemented by any source marker", r.file, r.line))
        if r.verification == "test" and r.status != "obsolete" and not rc.tests:
            f.append(Finding("warning", "UNCOVERED", f"{r.id} has no linked test", r.file, r.line))
        if rc.verification_status == "failing":
            failed = [t for t in rc.results if t.status in ("failed", "error")]
            f.append(
                Finding(
                    "error" if rules.fail_on_failing_tests else "warning",
                    "TEST_FAILED",
                    f"{r.id}: {len(failed)} linked test(s) failed ({', '.join(t.name for t in failed[:3])})",
                    r.file,
                    r.line,
                )
            )

    pct = report.test_coverage_pct()
    if pct + 1e-9 < rules.min_test_coverage:
        f.append(Finding("error", "COVERAGE", f"test coverage of requirements {pct:.1f}% is below the required {rules.min_test_coverage:.1f}%"))
    if rules.min_verified is not None and report.results:
        v = report.verified_pct()
        if v + 1e-9 < rules.min_verified:
            f.append(Finding("error", "VERIFIED", f"verified requirements {v:.1f}% is below the required {rules.min_verified:.1f}%"))

    if report.delta is not None:
        d = report.delta
        sev = "error" if rules.fail_on_coverage_drop else "warning"
        for ch in d.regressed:
            f.append(Finding(sev, "REGRESSION", f"{ch.req_id} lost its test ({ch.before} → {ch.after})",
                             report.requirements[ch.req_id].requirement.file, report.requirements[ch.req_id].requirement.line))
        if d.pct_change < -1e-9:
            f.append(Finding(sev, "COVERAGE_DROP", f"test coverage dropped from {d.base_pct:.1f}% to {d.pct:.1f}%"))

    for t in report.orphan_tests:
        f.append(
            Finding(
                "error" if rules.fail_on_orphan_tests else "info",
                "ORPHAN_TEST",
                f"test {t.full_name} is not linked to any requirement",
                t.file,
            )
        )
