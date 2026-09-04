"""Data model shared by all reqcov modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Requirement:
    id: str
    title: str = ""
    text: str = ""
    parents: List[str] = field(default_factory=list)
    verification: str = "test"  # test | analysis | inspection | demonstration | none
    status: str = "approved"  # draft | approved | obsolete ...
    tags: List[str] = field(default_factory=list)
    file: str = ""
    line: int = 0
    level: str = ""  # derived from id prefix, e.g. "SYS", "SRS"

    def __post_init__(self) -> None:
        if not self.level and "-" in self.id:
            self.level = self.id.rsplit("-", 1)[0]


@dataclass
class Reference:
    """A marker found in a source or test file that references one requirement id."""

    req_id: str
    file: str
    line: int
    kind: str  # "test" | "source"
    marker: str  # verb used: req / implements / verifies ...
    symbol: str = ""  # enclosing/following test or function name if detectable


@dataclass
class TestResult:
    name: str  # test function name (short)
    classname: str
    status: str  # passed | failed | skipped | error
    file: str = ""
    message: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.classname}::{self.name}" if self.classname else self.name


@dataclass
class RequirementCoverage:
    requirement: Requirement
    tests: List[Reference] = field(default_factory=list)
    sources: List[Reference] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    results: List[TestResult] = field(default_factory=list)
    unknown_parents: List[str] = field(default_factory=list)

    @property
    def has_test(self) -> bool:
        return bool(self.tests)

    @property
    def has_source(self) -> bool:
        return bool(self.sources)

    @property
    def verification_status(self) -> str:
        """uncovered | covered | verified | failing | skipped | n/a"""
        if self.requirement.verification != "test" or self.requirement.status == "obsolete":
            return "n/a"
        if not self.tests:
            return "uncovered"
        if not self.results:
            return "covered"
        statuses = {r.status for r in self.results}
        if "failed" in statuses or "error" in statuses:
            return "failing"
        if statuses <= {"skipped"}:
            return "skipped"
        return "verified"


@dataclass
class Finding:
    severity: str  # error | warning | info
    code: str
    message: str
    file: str = ""
    line: int = 0


@dataclass
class CoverageReport:
    requirements: Dict[str, RequirementCoverage]
    references: List[Reference]
    results: List[TestResult]
    findings: List[Finding]
    unknown_ids: List[Reference]
    orphan_tests: List[TestResult]
    generated_at: str
    git_sha: str = ""
    title: str = "Requirements Traceability"

    # ---- summary helpers -------------------------------------------------
    def by_level(self) -> Dict[str, List[RequirementCoverage]]:
        out: Dict[str, List[RequirementCoverage]] = {}
        for rc in self.requirements.values():
            out.setdefault(rc.requirement.level or "?", []).append(rc)
        for lst in out.values():
            lst.sort(key=lambda r: natural_key(r.requirement.id))
        return dict(sorted(out.items()))

    def testable(self) -> List[RequirementCoverage]:
        return [
            rc
            for rc in self.requirements.values()
            if rc.requirement.verification == "test" and rc.requirement.status != "obsolete"
        ]

    def test_coverage_pct(self) -> float:
        t = self.testable()
        if not t:
            return 100.0
        return 100.0 * sum(1 for rc in t if rc.has_test) / len(t)

    def verified_pct(self) -> float:
        t = self.testable()
        if not t:
            return 100.0
        return 100.0 * sum(1 for rc in t if rc.verification_status == "verified") / len(t)

    def counts(self) -> Dict[str, int]:
        c = {"total": 0, "uncovered": 0, "covered": 0, "verified": 0, "failing": 0, "skipped": 0, "n/a": 0}
        for rc in self.requirements.values():
            c["total"] += 1
            c[rc.verification_status] += 1
        return c

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


def natural_key(s: str):
    import re

    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]
