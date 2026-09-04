"""Command line interface.

    reqcov check   [--config reqcov.yml] [--root .] [--junit reports/*.xml] [--out dir] [--no-report]
    reqcov report  ... same options, never fails the build
    reqcov init    write an example reqcov.yml
    reqcov list    print requirements found
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .config import EXAMPLE_CONFIG, Config
from .coverage import analyze
from .report import render_markdown, write_reports


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", "-c", help="path to reqcov.yml (default: auto-detect in root)")
    p.add_argument("--root", "-r", default=".", help="repository root (default: .)")
    p.add_argument("--junit", action="append", help="JUnit XML glob (repeatable, overrides config)")
    p.add_argument("--out", "-o", help="report output directory (overrides config)")
    p.add_argument("--format", "-f", action="append", choices=["html", "csv", "json", "md"], help="report formats (repeatable)")
    p.add_argument("--no-report", action="store_true", help="do not write report files")
    p.add_argument("--quiet", "-q", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reqcov", description="Requirements coverage for pull requests.")
    p.add_argument("--version", action="version", version=f"reqcov {__version__}")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="analyze and fail (exit 1) when rules are violated")
    _common(c)
    r = sub.add_parser("report", help="analyze and write reports, never fails")
    _common(r)
    i = sub.add_parser("init", help="write an example reqcov.yml")
    i.add_argument("--root", "-r", default=".")
    i.add_argument("--force", action="store_true")
    l = sub.add_parser("list", help="list requirements found")
    _common(l)
    return p


def _load(args) -> Config:
    cfg = Config.load(args.config, root=args.root)
    if getattr(args, "junit", None):
        cfg.junit = args.junit
    if getattr(args, "out", None):
        cfg.report.out_dir = args.out
    if getattr(args, "format", None):
        cfg.report.formats = args.format
    return cfg


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd is None:
        build_parser().print_help()
        return 2

    if args.cmd == "init":
        path = os.path.join(args.root, "reqcov.yml")
        if os.path.exists(path) and not args.force:
            print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
            return 1
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(EXAMPLE_CONFIG)
        print(f"wrote {path}")
        return 0

    cfg = _load(args)
    report = analyze(cfg)

    if args.cmd == "list":
        for level, rows in report.by_level().items():
            print(f"[{level}]")
            for rc in rows:
                r = rc.requirement
                print(f"  {r.id:<12} {rc.verification_status:<10} {r.title[:70]}")
        return 0

    if not args.no_report:
        written = write_reports(report, cfg)
    else:
        written = {}

    if not args.quiet:
        print(render_markdown(report))
        for fmt, p in written.items():
            print(f"[reqcov] wrote {fmt}: {p}")

    # GitHub Actions integration: job summary + annotations
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(render_markdown(report))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for f in report.findings:
            if f.severity == "info":
                continue
            level = "error" if f.severity == "error" else "warning"
            loc = f" file={f.file}" + (f",line={f.line}" if f.line else "") if f.file else ""
            print(f"::{level}{loc}::[{f.code}] {f.message}")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(f"coverage={report.test_coverage_pct():.1f}\n")
                fh.write(f"errors={len(report.errors)}\n")
                fh.write(f"report_dir={os.path.join(cfg.root, cfg.report.out_dir)}\n")

    if args.cmd == "check" and report.errors:
        if not args.quiet:
            print(f"[reqcov] FAILED with {len(report.errors)} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
