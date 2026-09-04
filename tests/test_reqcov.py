import os
import re
import textwrap

import pytest

from reqcov.cli import main
from reqcov.config import Config
from reqcov.coverage import analyze
from reqcov.junit import parse_junit
from reqcov.links import scan_files
from reqcov.report import render_markdown, to_json
from reqcov.requirements import parse_markdown, parse_yaml

ID = r"[A-Z][A-Z0-9_]*-\d+"
EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


# --------------------------------------------------------------------------- parsers

def test_markdown_headings_and_metadata():
    text = textwrap.dedent(
        """
        # Doc
        ## SRS-1 — Title one
        Body line.
        Parent: SYS-1, SYS-2
        Verification: analysis
        Status: draft
        Tags: safety, ui
        ### [SRS-2] Title two
        **Parent:** SYS-1
        ## Not a requirement
        text
        **SRS-3**: bold form
        - SRS-4: list form. Verification: inspection. Parent: SRS-1
        """
    )
    reqs = {r.id: r for r in parse_markdown("f.md", text, re.compile(ID), [])}
    assert set(reqs) == {"SRS-1", "SRS-2", "SRS-3", "SRS-4"}
    r1 = reqs["SRS-1"]
    assert r1.title == "Title one" and r1.text == "Body line."
    assert r1.parents == ["SYS-1", "SYS-2"] and r1.verification == "analysis"
    assert r1.status == "draft" and r1.tags == ["safety", "ui"] and r1.level == "SRS"
    assert reqs["SRS-2"].parents == ["SYS-1"] and reqs["SRS-2"].title == "Title two"
    assert reqs["SRS-3"].title == "bold form"
    assert reqs["SRS-4"].verification == "inspection" and reqs["SRS-4"].parents == ["SRS-1"]
    assert reqs["SRS-4"].title == "list form"


def test_yaml_list_and_doorstop_forms():
    lst = "requirements:\n  - id: HLR-1\n    title: A\n    parent: SYS-9\n  - id: HLR-2\n    text: B text\n    verification: none\n"
    reqs = parse_yaml("r.yml", lst, re.compile(ID), [])
    assert [r.id for r in reqs] == ["HLR-1", "HLR-2"]
    assert reqs[0].parents == ["SYS-9"] and reqs[1].verification == "none" and reqs[1].title == "B text"

    doorstop = "active: true\nderived: false\nlevel: 1.2\nlinks:\n- SYS001: abc123\nnormative: true\ntext: |\n  The thing shall work.\n"
    reqs = parse_yaml("REQ001.yml", doorstop, re.compile(r"[A-Z]+\d+"), [])
    assert len(reqs) == 1 and reqs[0].id == "REQ001" and reqs[0].parents == ["SYS001"]
    assert reqs[0].title == "The thing shall work."


def test_marker_scanning(tmp_path):
    (tmp_path / "t.py").write_text(
        textwrap.dedent(
            """
            @pytest.mark.req("SRS-1", "SRS-2")
            def test_a():
                pass

            # @verifies SRS-3
            def test_b():
                pass

            def test_c():
                # @req SRS-4
                assert True
            """
        )
    )
    (tmp_path / "s.c").write_text("/* @implements SRS-1 */\nvoid f(void) {}\n")
    refs = scan_files(str(tmp_path), ["t.py"], "test", ["req", "verifies", "implements"], ID)
    got = {(r.req_id, r.symbol) for r in refs}
    assert got == {("SRS-1", "test_a"), ("SRS-2", "test_a"), ("SRS-3", "test_b"), ("SRS-4", "test_c")}
    src = scan_files(str(tmp_path), ["s.c"], "source", ["req", "verifies", "implements"], ID)
    assert [(r.req_id, r.symbol, r.kind) for r in src] == [("SRS-1", "f", "source")]


def test_junit_parsing(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(
        '<testsuites><testsuite name="s"><testcase classname="m" name="test_a"/>'
        '<testcase classname="m" name="test_b"><failure message="boom"/></testcase>'
        '<testcase classname="m" name="test_c"><skipped/></testcase></testsuite></testsuites>'
    )
    res = {r.name: r.status for r in parse_junit(str(p))}
    assert res == {"test_a": "passed", "test_b": "failed", "test_c": "skipped"}


# --------------------------------------------------------------------------- end to end

def _cfg(root, **rules):
    cfg = Config.load(root=root)
    for k, v in rules.items():
        setattr(cfg.rules, k, v)
    cfg.report.formats = []
    return cfg


def test_pytest_example_has_intentional_gap():
    root = os.path.join(EXAMPLES, "pytest-project")
    rep = analyze(_cfg(root))
    s = to_json(rep)["summary"]
    assert s["total"] == 8 and s["uncovered"] == 1 and s["n/a"] == 2
    assert rep.requirements["SRS-13"].verification_status == "uncovered"
    assert rep.requirements["SRS-12"].verification_status == "verified"  # parametrised test matched
    assert len(rep.requirements["SRS-12"].results) == 4
    assert [t.name for t in rep.orphan_tests] == ["test_default_setpoint"]
    assert {f.code for f in rep.errors} == {"COVERAGE"}
    assert rep.requirements["SRS-10"].sources[0].symbol == "update"
    assert "SRS-10" in rep.requirements["SYS-1"].children


def test_ceedling_example_propagates_failure():
    root = os.path.join(EXAMPLES, "ceedling-unity")
    rep = analyze(_cfg(root))
    assert rep.test_coverage_pct() == 100.0
    assert rep.requirements["LLR-12"].verification_status == "failing"
    assert rep.requirements["HLR-2"].verification_status == "failing"
    assert {f.code for f in rep.errors} == {"TEST_FAILED"}
    md = render_markdown(rep)
    assert md.startswith("<!-- reqcov -->") and "TEST_FAILED" in md


def test_googletest_example_passes():
    root = os.path.join(EXAMPLES, "googletest")
    rep = analyze(_cfg(root))
    assert not rep.errors
    assert rep.requirements["SWR-2"].results[0].full_name == "RingBuffer::PushOnFullFails"
    assert rep.requirements["SWR-4"].verification_status == "n/a"


def test_rules_unknown_id_and_orphans(tmp_path):
    (tmp_path / "reqs.md").write_text("## R-1 — a\n## R-2 — b\n")
    (tmp_path / "test_x.py").write_text("# @req R-1, R-9\ndef test_x():\n    pass\n")
    cfg = Config.from_dict({"requirements": ["reqs.md"], "tests": ["test_*.py"], "sources": [], "rules": {"min_test_coverage": 50}}, root=str(tmp_path))
    cfg.report.formats = []
    rep = analyze(cfg)
    assert [u.req_id for u in rep.unknown_ids] == ["R-9"]
    assert {f.code for f in rep.errors} == {"UNKNOWN_ID"}
    assert rep.test_coverage_pct() == 50.0


def test_cli_writes_reports_and_exit_codes(tmp_path, capsys):
    root = os.path.join(EXAMPLES, "googletest")
    out = tmp_path / "rep"
    assert main(["check", "--root", root, "--out", str(out), "-q"]) == 0
    assert {p.name for p in out.iterdir()} == {"index.html", "matrix.csv", "coverage.json", "summary.md"}
    html = (out / "index.html").read_text()
    assert "Traceability matrix" in html and "SWR-1" in html
    root2 = os.path.join(EXAMPLES, "pytest-project")
    assert main(["check", "--root", root2, "--out", str(tmp_path / "rep2"), "-q"]) == 1
    assert main(["report", "--root", root2, "--out", str(tmp_path / "rep3"), "-q"]) == 0


def test_cli_init(tmp_path):
    assert main(["init", "--root", str(tmp_path)]) == 0
    assert (tmp_path / "reqcov.yml").exists()
    cfg = Config.load(root=str(tmp_path))
    assert cfg.rules.require_parent_for == ["SRS"]
