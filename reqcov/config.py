"""Configuration loading (reqcov.yml)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

DEFAULT_CONFIG_NAMES = ("reqcov.yml", "reqcov.yaml", ".reqcov.yml")

DEFAULT_ID_PATTERN = r"[A-Z][A-Z0-9_]*-\d+"


@dataclass
class Rules:
    min_test_coverage: float = 100.0  # % of testable requirements with >= 1 linked test
    min_verified: Optional[float] = None  # % verified (needs JUnit); None = not enforced
    fail_on_unknown_ids: bool = True
    fail_on_orphan_tests: bool = False
    fail_on_failing_tests: bool = True
    require_parent_for: List[str] = field(default_factory=list)  # levels that must have a parent
    require_source_for: List[str] = field(default_factory=list)  # levels that must have an implements link
    allow_derived: bool = True  # if False, missing parent is an error instead of warning


@dataclass
class ReportConfig:
    out_dir: str = "reqcov-report"
    formats: List[str] = field(default_factory=lambda: ["html", "csv", "json", "md"])
    title: str = "Requirements Traceability"
    project: str = ""


@dataclass
class Config:
    root: str = "."
    id_pattern: str = DEFAULT_ID_PATTERN
    requirements: List[str] = field(default_factory=lambda: ["docs/requirements/**/*.md", "docs/requirements/**/*.yml"])
    sources: List[str] = field(default_factory=lambda: ["src/**/*"])
    tests: List[str] = field(default_factory=lambda: ["tests/**/*", "test/**/*"])
    junit: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=lambda: ["**/node_modules/**", "**/.git/**", "**/build/**", "**/.venv/**"])
    markers: List[str] = field(default_factory=lambda: ["req", "requirement", "requirements", "implements", "verifies", "satisfies", "trace", "traces"])
    rules: Rules = field(default_factory=Rules)
    report: ReportConfig = field(default_factory=ReportConfig)

    @staticmethod
    def load(path: Optional[str] = None, root: Optional[str] = None) -> "Config":
        root = root or "."
        data: Dict[str, Any] = {}
        cfg_path = path
        if cfg_path is None:
            for name in DEFAULT_CONFIG_NAMES:
                candidate = os.path.join(root, name)
                if os.path.exists(candidate):
                    cfg_path = candidate
                    break
        if cfg_path and os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        return Config.from_dict(data, root=root)

    @staticmethod
    def from_dict(data: Dict[str, Any], root: str = ".") -> "Config":
        cfg = Config(root=root)
        if "id_pattern" in data:
            cfg.id_pattern = str(data["id_pattern"])
        for key in ("requirements", "sources", "tests", "junit", "exclude", "markers"):
            if key in data and data[key] is not None:
                val = data[key]
                if isinstance(val, str):
                    val = [val]
                # accept list of {path: ...} too
                cfg.__dict__[key] = [v["path"] if isinstance(v, dict) else str(v) for v in val]
        rules = data.get("rules") or {}
        for k, v in rules.items():
            if hasattr(cfg.rules, k):
                setattr(cfg.rules, k, v)
        rep = data.get("report") or {}
        for k, v in rep.items():
            if hasattr(cfg.report, k):
                setattr(cfg.report, k, v)
        return cfg


EXAMPLE_CONFIG = """# reqcov configuration — see https://github.com/reqcov/reqcov
version: 1

# Regex for requirement identifiers. Level = everything before the last dash (SYS, SRS, HLR, LLR...).
id_pattern: "[A-Z][A-Z0-9_]*-\\\\d+"

# Where requirements live (Markdown headings, YAML lists, or Doorstop items).
requirements:
  - docs/requirements/**/*.md
  - docs/requirements/**/*.yml

# Files scanned for `@implements REQ-1` style markers (traces to code).
sources:
  - src/**/*

# Files scanned for `@req REQ-1` / `@verifies REQ-1` markers (traces to tests).
tests:
  - tests/**/*

# Optional JUnit XML results: turns "covered" into "verified" / "failing".
junit:
  - reports/**/*.xml

rules:
  min_test_coverage: 100      # % of testable requirements that must have at least one test
  fail_on_unknown_ids: true   # a marker references an id that does not exist
  fail_on_orphan_tests: false # a test has no requirement marker
  fail_on_failing_tests: true # a linked test failed (needs junit)
  require_parent_for: [SRS]   # these levels must trace up to a parent requirement

report:
  out_dir: reqcov-report
  formats: [html, csv, json, md]
  title: "Software Requirements Traceability"
"""
