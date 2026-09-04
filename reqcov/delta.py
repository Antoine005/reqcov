"""Coverage delta against a baseline (typically the pull request's base branch).

A baseline is a ``coverage.json`` produced by an earlier ``reqcov`` run. It can be
given explicitly (``--baseline path``) or produced on the fly from a git ref
(``--base-ref origin/main``): the ref is checked out in a temporary worktree and
analysed with the same configuration, without JUnit results. The delta is
therefore about *static* coverage (which requirements have a linked test), which
is what a reviewer can act on inside the pull request.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import Config
from .models import CoverageReport, natural_key


@dataclass
class StatusChange:
    req_id: str
    title: str
    before: str  # status in the baseline, or "" when the requirement is new
    after: str  # status now, or "" when the requirement was removed


@dataclass
class Delta:
    base_sha: str = ""
    base_pct: float = 0.0
    pct: float = 0.0
    added: List[StatusChange] = field(default_factory=list)  # new requirements
    removed: List[StatusChange] = field(default_factory=list)  # requirements that disappeared
    improved: List[StatusChange] = field(default_factory=list)  # gained a test
    regressed: List[StatusChange] = field(default_factory=list)  # lost its test
    other: List[StatusChange] = field(default_factory=list)  # any other status change

    @property
    def pct_change(self) -> float:
        return self.pct - self.base_pct

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.improved or self.regressed or self.other)


def load_baseline(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "requirements" not in data or "summary" not in data:
        raise ValueError(f"{path} is not a reqcov coverage.json")
    return data


def _has_test(status: str) -> bool:
    return status in ("covered", "verified", "failing", "skipped")


def compute_delta(report: CoverageReport, baseline: Dict) -> Delta:
    """Compare ``report`` with a baseline ``coverage.json`` dict."""
    base_status: Dict[str, str] = {r["id"]: r["status"] for r in baseline["requirements"]}
    base_title: Dict[str, str] = {r["id"]: r.get("title", "") for r in baseline["requirements"]}
    d = Delta(
        base_sha=baseline.get("git_sha", ""),
        base_pct=float(baseline["summary"].get("test_coverage_pct", 0.0)),
        pct=round(report.test_coverage_pct(), 2),
    )
    for rid, rc in sorted(report.requirements.items(), key=lambda kv: natural_key(kv[0])):
        now = rc.verification_status
        if rid not in base_status:
            d.added.append(StatusChange(rid, rc.requirement.title, "", now))
            continue
        before = base_status[rid]
        if before == now:
            continue
        ch = StatusChange(rid, rc.requirement.title, before, now)
        if not _has_test(before) and _has_test(now):
            d.improved.append(ch)
        elif _has_test(before) and now == "uncovered":
            d.regressed.append(ch)
        else:
            d.other.append(ch)
    for rid in sorted(set(base_status) - set(report.requirements), key=natural_key):
        d.removed.append(StatusChange(rid, base_title.get(rid, ""), base_status[rid], ""))
    return d


def baseline_from_git(cfg: Config, ref: str, config_path: Optional[str] = None) -> Dict:
    """Analyse ``ref`` in a temporary worktree and return its coverage as a dict.

    JUnit results are not available for the base commit, so the baseline only
    knows whether each requirement has a linked test.
    """
    from .coverage import analyze  # local import: coverage imports nothing from here
    from .report import to_json

    root = os.path.abspath(cfg.root)
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    sub = os.path.relpath(root, top)
    tmp = tempfile.mkdtemp(prefix="reqcov-base-")
    wt = os.path.join(tmp, "wt")
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", wt, ref],
            cwd=top,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        base_root = os.path.normpath(os.path.join(wt, sub)) if sub != "." else wt
        base_cfg_path = None
        if config_path:
            rel = os.path.relpath(os.path.abspath(config_path), root)
            cand = os.path.join(base_root, rel)
            base_cfg_path = cand if os.path.exists(cand) else None
        base_cfg = Config.load(base_cfg_path, root=base_root)
        base_cfg.junit = []
        base_cfg.report.formats = []
        return to_json(analyze(base_cfg))
    except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on git state
        msg = (exc.stderr or "").strip()
        raise RuntimeError(f"cannot check out base ref {ref!r}: {msg or exc}") from None
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=top, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(tmp, ignore_errors=True)
