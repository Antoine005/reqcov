"""0.3: ReqIF import/export, PDF export, Jira links."""
import csv
import json
import os
import re
import shutil
import textwrap
import zipfile
import zlib

import pytest

from reqcov.cli import main
from reqcov.config import Config, ReqifConfig
from reqcov.coverage import analyze
from reqcov.pdf import render_pdf, wrap
from reqcov.reqif import load_reqif, parse_reqif, render_reqif
from reqcov.report import render_html, render_markdown, to_json
from reqcov.requirements import parse_markdown, parse_yaml

ID = re.compile(r"[A-Z][A-Z0-9_]*-\d+")
HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "fixtures")
EXAMPLES = os.path.join(HERE, "..", "examples")


def _cfg(root, **data):
    cfg = Config.from_dict(data, root=root) if data else Config.load(root=root)
    cfg.report.formats = []
    return cfg


# --------------------------------------------------------------------------- ReqIF import

def test_reqif_import_doors_style_export():
    findings = []
    reqs = {r.id: r for r in load_reqif(FIXTURES, "doors_export.reqif", ID, findings, ReqifConfig(id_prefix="SRS-"))}
    assert not findings
    assert set(reqs) == {"SRS-2", "SRS-3", "SRS-4"}  # object 1 is a chapter heading
    r2 = reqs["SRS-2"]
    assert r2.text == "The controller shall apply the brakes within 50 ms.\nMeasured at the wheel."
    assert r2.title == "The controller shall apply the brakes within 50 ms."
    assert r2.verification == "test" and r2.status == "approved" and r2.jira == ["BRK-101", "BRK-102"]
    assert r2.level == "SRS" and r2.file == "doors_export.reqif" and r2.line > 1
    assert r2.parents == []  # its link goes to the heading, which is not a requirement
    r3 = reqs["SRS-3"]
    assert r3.text == "The brake command shall be retried\nat most twice."
    assert r3.verification == "analysis" and r3.status == "draft" and r3.parents == ["SRS-2"]
    assert reqs["SRS-4"].parents == ["SRS-2"]  # every relation type counts by default


def test_reqif_relation_filter_and_direction():
    cfg = ReqifConfig(id_prefix="SRS-", relation_types=["Satisfies"])
    reqs = {r.id: r for r in load_reqif(FIXTURES, "doors_export.reqif", ID, [], cfg)}
    assert reqs["SRS-3"].parents == ["SRS-2"] and reqs["SRS-4"].parents == []
    cfg = ReqifConfig(id_prefix="SRS-", parent_end="source")
    reqs = {r.id: r for r in load_reqif(FIXTURES, "doors_export.reqif", ID, [], cfg)}
    assert reqs["SRS-2"].parents == ["SRS-3", "SRS-4"] and reqs["SRS-3"].parents == []


def test_reqif_without_prefix_needs_ids_matching_the_pattern():
    # numeric DOORS ids do not match id_pattern: nothing is imported without id_prefix
    assert load_reqif(FIXTURES, "doors_export.reqif", ID, [], None) == []


def test_reqif_parse_errors_are_findings(tmp_path):
    (tmp_path / "bad.reqif").write_text("<REQ-IF><unclosed></REQ-IF>")
    (tmp_path / "bad.reqifz").write_bytes(b"not a zip")
    findings = []
    assert load_reqif(str(tmp_path), "bad.reqif", ID, findings) == []
    assert load_reqif(str(tmp_path), "bad.reqifz", ID, findings) == []
    assert [f.code for f in findings] == ["REQIF_PARSE", "REQIF_PARSE"]


def test_config_rejects_bad_parent_end():
    with pytest.raises(ValueError):
        Config.from_dict({"reqif": {"parent_end": "up"}})


# --------------------------------------------------------------------------- ReqIF export

def test_reqif_export_round_trips_through_import(tmp_path):
    root = os.path.join(EXAMPLES, "pytest-project")
    cfg = _cfg(root)
    rep = analyze(cfg)
    xml = render_reqif(rep, cfg)
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"')

    back = {r.id: r for r in parse_reqif("x.reqif", xml.encode("utf-8"), ID, [])}
    assert set(back) == set(rep.requirements)
    for rid, rc in rep.requirements.items():
        r, b = rc.requirement, back[rid]
        assert (b.title, b.text, b.parents, b.verification, b.status, b.tags) == (r.title, r.text, r.parents, r.verification, r.status, r.tags)
    # coverage travels as reqcov.* attributes, one SPECIFICATION per level
    assert 'LONG-NAME="reqcov.Coverage"' in xml and 'THE-VALUE="uncovered"' in xml
    assert xml.count("<SPECIFICATION ") == 2 and xml.count("<SPEC-RELATION ") == 4

    # the same file, zipped, analysed end to end as the requirement source
    (tmp_path / "tests").mkdir()
    shutil.copy(os.path.join(root, "tests", "test_controller.py"), tmp_path / "tests")
    with zipfile.ZipFile(tmp_path / "reqs.reqifz", "w") as z:
        z.writestr("export/reqs.reqif", xml)
    rep2 = analyze(_cfg(str(tmp_path), requirements=["*.reqifz"], tests=["tests/*.py"], sources=[]))
    assert {rid: rc.verification_status for rid, rc in rep2.requirements.items()} == {
        rid: ("covered" if s == "verified" else s) for rid, s in ((rid, rc.verification_status) for rid, rc in rep.requirements.items())
    }
    assert rep2.requirements["SRS-10"].requirement.line == 0  # no line numbers inside an archive


# --------------------------------------------------------------------------- PDF

def _pdf_pages(data: bytes):
    streams = re.findall(rb"stream\n(.*?)\nendstream", data, re.S)
    return [zlib.decompress(s).decode("latin-1") for s in streams]


def _pdf_text(data: bytes) -> str:
    return "\n".join(_pdf_pages(data))


def test_pdf_export_is_well_formed():
    root = os.path.join(EXAMPLES, "pytest-project")
    cfg = _cfg(root)
    rep = analyze(cfg)
    data = render_pdf(rep, cfg)
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")

    # every xref offset points at the start of its object
    xref_at = int(re.search(rb"startxref\n(\d+)", data).group(1))
    assert data[xref_at:].startswith(b"xref")
    count = int(re.search(rb"xref\n0 (\d+)", data).group(1))
    offsets = [int(o) for o in re.findall(rb"(\d{10}) 00000 n", data)]
    assert len(offsets) == count - 1
    for num, off in enumerate(offsets, start=1):
        assert data[off:].startswith(b"%d 0 obj" % num)

    pages = int(re.search(rb"/Type /Pages /Kids \[[^\]]*\] /Count (\d+)", data).group(1))
    text = _pdf_text(data)
    assert text.count("Page 1 / %d" % pages) == 1 and "Page %d / %d" % (pages, pages) in text
    for needle in ("(Traceability matrix)", "(SRS-13)", "(uncovered)", "(test_overtemp_cutoff  tests/test_controller.py:19)", "(Sign-off)"):
        assert needle in text
    assert "(The controller shall" not in text  # the matrix shows titles, not full texts
    # U+2212 in a title is transliterated, the em dash kept (WinAnsi 0x97)
    assert "\\227" in text


def test_pdf_wrap_breaks_long_tokens_after_separators():
    lines = wrap("PASS examples.pytest-project.tests.test_controller::test_hysteresis_turns_on_below_band", 150, 7.5)
    assert lines[0].startswith("PASS examples.") and all(len(l) > 3 for l in lines)
    assert "".join(lines).replace("PASS ", "PASS ", 1) == "PASS examples.pytest-project.tests.test_controller::test_hysteresis_turns_on_below_band"
    assert wrap("", 100, 8) == [""]


def test_pdf_paginates_large_matrices(tmp_path):
    reqs = "\n".join(f"## R-{i} — requirement {i} with a reasonably long title to wrap" for i in range(1, 301))
    (tmp_path / "reqs.md").write_text(reqs)
    rep = analyze(_cfg(str(tmp_path), requirements=["reqs.md"], tests=[], sources=[], rules={"min_test_coverage": 0}))
    pages = _pdf_pages(render_pdf(rep))
    assert len(pages) > 5
    assert r"(300 requirement\(s\) without a linked test are marked uncovered in the matrix.)" in pages[0]
    first = next(i for i, p in enumerate(pages) if "(Traceability matrix)" in p)
    assert first == 1 and all("(REQUIREMENT)" in p for p in pages[first:])  # header repeated on every page
    assert "(R-300)" in pages[-1]


# --------------------------------------------------------------------------- Jira

def test_jira_keys_in_markdown_and_yaml():
    md = textwrap.dedent(
        """
        ## SRS-1 — Braking
        Parent: SYS-1
        Jira: BRK-12, BRK-13
        - SRS-2: one-liner. Verification: test. Jira: BRK-14
        ## SRS-3 — No key
        Issue: see the review notes.
        """
    )
    reqs = {r.id: r for r in parse_markdown("f.md", md, ID, [])}
    assert reqs["SRS-1"].jira == ["BRK-12", "BRK-13"] and reqs["SRS-1"].text == ""
    assert reqs["SRS-2"].jira == ["BRK-14"] and reqs["SRS-2"].title == "one-liner"
    assert reqs["SRS-3"].jira == [] and reqs["SRS-3"].text == "Issue: see the review notes."
    y = parse_yaml("r.yml", "- id: HLR-1\n  title: A\n  jira: [BRK-1, BRK-2]\n- id: HLR-2\n  tickets: BRK-3\n", ID, [])
    assert [r.jira for r in y] == [["BRK-1", "BRK-2"], ["BRK-3"]]


def test_jira_links_in_reports(tmp_path):
    (tmp_path / "reqs.md").write_text("## R-1 — covered\nJira: ABC-7\n## R-2 — uncovered\nJira: ABC-8\n")
    (tmp_path / "test_x.py").write_text("# @req R-1\ndef test_x():\n    pass\n")
    (tmp_path / "reqcov.yml").write_text(
        "requirements: [reqs.md]\ntests: ['test_*.py']\nsources: []\n"
        "jira:\n  url: https://acme.atlassian.net/\n"
        "report:\n  formats: [html, csv, json, md, pdf, reqif]\n"
    )
    assert main(["report", "--root", str(tmp_path), "-q"]) == 0
    out = tmp_path / "reqcov-report"
    assert {p.name for p in out.iterdir()} == {"index.html", "matrix.csv", "coverage.json", "summary.md", "matrix.pdf", "requirements.reqif"}
    assert "- **R-2** uncovered ([ABC-8](https://acme.atlassian.net/browse/ABC-8))" in (out / "summary.md").read_text()
    assert '<a class="jira" href="https://acme.atlassian.net/browse/ABC-7">ABC-7</a>' in (out / "index.html").read_text()
    rows = list(csv.DictReader((out / "matrix.csv").open(encoding="utf-8")))
    assert [r["jira"] for r in rows] == ["ABC-7", "ABC-8"]
    assert [r["jira"] for r in json.loads((out / "coverage.json").read_text())["requirements"]] == [["ABC-7"], ["ABC-8"]]
    assert 'THE-VALUE="ABC-8"' in (out / "requirements.reqif").read_text()

    # without a url the keys are still shown, as plain text
    cfg = Config.load(root=str(tmp_path))
    cfg.jira.url = ""
    rep = analyze(cfg)
    assert "(`ABC-8`)" in render_markdown(rep)
    assert "<code>ABC-7</code>" in render_html(rep, cfg)
    assert to_json(rep)["requirements"][0]["jira"] == ["ABC-7"]
    assert Config.from_dict({"jira": "https://x.example"}).jira.issue_url("A-1") == "https://x.example/browse/A-1"


# --------------------------------------------------------------------------- 0.3.1: brownfield adoption

def _two_module_export() -> bytes:
    """Two DOORS modules in one exchange file, numbered from 1 each, one link SRS 1 -> SYS 1."""
    def obj(ident, fid, text):
        return (
            f'<SPEC-OBJECT IDENTIFIER="{ident}" LAST-CHANGE="2026-01-01T00:00:00Z"><TYPE><SPEC-OBJECT-TYPE-REF>t</SPEC-OBJECT-TYPE-REF></TYPE><VALUES>'
            f'<ATTRIBUTE-VALUE-STRING THE-VALUE="{fid}"><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>a_id</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>'
            f'<ATTRIBUTE-VALUE-STRING THE-VALUE="{text}"><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>a_text</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>'
            "</VALUES></SPEC-OBJECT>"
        )

    def spec(name, *refs):
        children = "".join(
            f'<SPEC-HIERARCHY IDENTIFIER="h_{r}" LAST-CHANGE="2026-01-01T00:00:00Z"><OBJECT><SPEC-OBJECT-REF>{r}</SPEC-OBJECT-REF></OBJECT></SPEC-HIERARCHY>'
            for r in refs
        )
        return f'<SPECIFICATION IDENTIFIER="s_{name}" LONG-NAME="{name}" LAST-CHANGE="2026-01-01T00:00:00Z"><CHILDREN>{children}</CHILDREN></SPECIFICATION>'

    return (
        '<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"><CORE-CONTENT><REQ-IF-CONTENT>'
        '<SPEC-TYPES><SPEC-OBJECT-TYPE IDENTIFIER="t" LAST-CHANGE="2026-01-01T00:00:00Z"><SPEC-ATTRIBUTES>'
        '<ATTRIBUTE-DEFINITION-STRING IDENTIFIER="a_id" LONG-NAME="ReqIF.ForeignID" LAST-CHANGE="2026-01-01T00:00:00Z"/>'
        '<ATTRIBUTE-DEFINITION-STRING IDENTIFIER="a_text" LONG-NAME="ReqIF.Text" LAST-CHANGE="2026-01-01T00:00:00Z"/>'
        "</SPEC-ATTRIBUTES></SPEC-OBJECT-TYPE></SPEC-TYPES>"
        "<SPEC-OBJECTS>"
        + obj("sys1", "1", "System does X")
        + obj("srs1", "1", "Software does X")
        + obj("srs2", "2", "Software logs X")
        + obj("loose", "7", "Outside any module")
        + "</SPEC-OBJECTS><SPEC-RELATIONS>"
        '<SPEC-RELATION IDENTIFIER="r1" LAST-CHANGE="2026-01-01T00:00:00Z"><SOURCE><SPEC-OBJECT-REF>srs1</SPEC-OBJECT-REF></SOURCE>'
        "<TARGET><SPEC-OBJECT-REF>sys1</SPEC-OBJECT-REF></TARGET></SPEC-RELATION>"
        "</SPEC-RELATIONS><SPECIFICATIONS>"
        + spec("System Requirements", "sys1")
        + spec("Software Requirements", "srs1", "srs2")
        + "</SPECIFICATIONS></REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>"
    ).encode()


def test_reqif_prefix_per_module():
    cfg = ReqifConfig(id_prefix={"system requirements": "SYS-", "Software Requirements": "SRS-"})
    findings = []
    reqs = {r.id: r for r in parse_reqif("x.reqif", _two_module_export(), ID, findings, cfg)}
    assert not findings
    # the same absolute number 1 in two modules gives two requirements; an object outside the
    # mapped modules has only a numeric id, which does not match id_pattern: skipped
    assert set(reqs) == {"SYS-1", "SRS-1", "SRS-2"}
    assert reqs["SRS-1"].parents == ["SYS-1"] and reqs["SRS-1"].level == "SRS"
    assert reqs["SRS-2"].reqif_id == "srs2"
    with pytest.raises(ValueError):
        Config.from_dict({"reqif": {"id_prefix": ["SRS-"]}})
    assert Config.from_dict({"reqif": {"id_prefix": {"SRS": "SRS-"}}}).reqif.id_prefix == {"SRS": "SRS-"}


def test_reqif_export_keeps_original_identifiers(tmp_path):
    shutil.copy(os.path.join(FIXTURES, "doors_export.reqif"), tmp_path)
    cfg = _cfg(str(tmp_path), requirements=["*.reqif"], tests=[], sources=[], reqif={"id_prefix": "SRS-"}, rules={"min_test_coverage": 0})
    rep = analyze(cfg)
    xml = render_reqif(rep, cfg)
    # DOORS can match its own objects: SPEC-OBJECT identifiers are the ones it exported
    assert re.findall(r'<SPEC-OBJECT IDENTIFIER="([^"]+)"', xml) == ["_o2", "_o3", "_o4"]
    assert '<SPEC-OBJECT-REF>_o3</SPEC-OBJECT-REF>' in xml
    idents = re.findall(r'IDENTIFIER="([^"]+)"', xml)
    assert len(idents) == len(set(idents))  # xsd:ID: unique across the document
    back = {r.id: r for r in parse_reqif("x.reqif", xml.encode(), ID, [])}
    assert set(back) == {"SRS-2", "SRS-3", "SRS-4"} and back["SRS-3"].parents == ["SRS-2"]


def test_unknown_id_that_is_a_jira_issue_names_its_requirements(tmp_path):
    (tmp_path / "reqs.md").write_text("## R-1 — a\nJira: ABC-7\n## R-2 — b\nJira: ABC-7\n")
    (tmp_path / "test_x.py").write_text("# @req ABC-7\ndef test_x():\n    pass\n")
    rep = analyze(_cfg(str(tmp_path), requirements=["reqs.md"], tests=["test_*.py"], sources=[]))
    [f] = [f for f in rep.errors if f.code == "UNKNOWN_ID"]
    assert "it is a Jira issue: reference its requirement(s) R-1, R-2 instead" in f.message


def test_coverage_json_schema_and_newer_baseline_refused(tmp_path):
    from reqcov.delta import load_baseline

    root = os.path.join(EXAMPLES, "googletest")
    data = to_json(analyze(_cfg(root)))
    assert data["schema"] == 1
    old = dict(data)
    del old["schema"]  # written by reqcov < 0.3.1
    (tmp_path / "old.json").write_text(json.dumps(old))
    assert load_baseline(str(tmp_path / "old.json"))["summary"] == data["summary"]
    data["schema"] = 2
    (tmp_path / "new.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="newer reqcov"):
        load_baseline(str(tmp_path / "new.json"))
