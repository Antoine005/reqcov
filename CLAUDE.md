# reqcov — notes for Claude Code

- Python ≥ 3.9, deps: PyYAML, Jinja2 only. Keep it that way (installs fast inside the Action).
- Pipeline: `config.py` → `coverage.analyze()` (uses `requirements.py`, `links.py`, `junit.py`) → `report.py`.
- Statuses live in `models.RequirementCoverage.verification_status`; rules in `coverage.evaluate_rules`.
- Run `python -m pytest -q`; the three `examples/` projects are the integration fixtures — keep their
  intentional gap (pytest: SRS-13 uncovered, one orphan test) and failure (ceedling: LLR-12 failing).
- Code in English, business docs in French (docs/PRD.md).
