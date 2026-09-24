"""PDF export of the traceability matrix, for audit packages.

Written against the PDF 1.4 specification with the standard library only (no reportlab), so
the Action keeps installing in seconds. Uses the two standard Type 1 fonts every reader ships
(Helvetica, Helvetica-Bold) with WinAnsiEncoding: text outside Windows-1252 is transliterated
(``≥`` → ``>=``) or replaced by ``?``.

Layout: A4 landscape. First the summary (numbers, coverage by level, findings, delta, a sign-off
table), then the matrix grouped by level with its header repeated on every page, then unknown
ids and orphan tests. Every page carries the title, commit and ``page n / N``.
"""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from . import __version__
from .models import CoverageReport

if TYPE_CHECKING:  # pragma: no cover
    from .config import Config

PAGE_W, PAGE_H = 842.0, 595.0  # A4 landscape, points
MARGIN = 36.0
CONTENT_W = PAGE_W - 2 * MARGIN
TOP = PAGE_H - MARGIN
BOTTOM = MARGIN + 18  # room for the footer

Color = Tuple[float, float, float]
INK: Color = (0.106, 0.122, 0.141)
MUTED: Color = (0.357, 0.392, 0.439)
LINE: Color = (0.89, 0.902, 0.918)
HEAD_BG: Color = (0.941, 0.949, 0.961)
WHITE: Color = (1.0, 1.0, 1.0)
STATUS_COLORS: Dict[str, Color] = {
    "verified": (0.102, 0.498, 0.294),
    "covered": (0.184, 0.373, 0.82),
    "uncovered": (0.702, 0.149, 0.118),
    "failing": (0.702, 0.149, 0.118),
    "skipped": (0.698, 0.416, 0.0),
    "n/a": (0.541, 0.58, 0.627),
    "error": (0.702, 0.149, 0.118),
    "warning": (0.698, 0.416, 0.0),
    "info": (0.184, 0.373, 0.82),
}

# Adobe AFM advance widths (1/1000 em) for ASCII 32..126.
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_HELVETICA_BOLD = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]
_WIDE = {0x97: 1000, 0x85: 1000, 0x89: 1000, 0x80: 556, 0x95: 350, 0x96: 556, 0xB0: 400}

_TRANSLIT = {
    "≥": ">=", "≤": "<=", "≠": "!=", "→": "->", "←": "<-", "↳": ">", "−": "-", "✓": "v", "✗": "x",
    "✅": "", "❌": "", "▲": "+", "▼": "-", "…": "...", " ": " ", "\t": "    ",
}


def _encode(s: str) -> bytes:
    for k, v in _TRANSLIT.items():
        if k in s:
            s = s.replace(k, v)
    return s.encode("cp1252", errors="replace")


def text_width(s: str, size: float, bold: bool = False) -> float:
    table = _HELVETICA_BOLD if bold else _HELVETICA
    total = 0
    for b in _encode(s):
        total += table[b - 32] if 32 <= b <= 126 else _WIDE.get(b, 556)
    return total * size / 1000.0


def _pdf_string(s: str) -> str:
    out = []
    for b in _encode(s):
        if b in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(b))
        elif 32 <= b <= 126:
            out.append(chr(b))
        else:
            out.append("\\%03o" % b)
    return "(" + "".join(out) + ")"


_BREAK_AFTER = "/\\:._-,"


def _cut(word: str, avail: float, size: float, bold: bool) -> int:
    """Longest prefix of ``word`` that fits ``avail``, backed off to a path/name separator."""
    cut = len(word)
    while cut > 0 and text_width(word[:cut], size, bold) > avail:
        cut -= 1
    if 0 < cut < len(word):
        brk = max(word.rfind(c, 0, cut) for c in _BREAK_AFTER)
        if brk >= cut // 2:
            cut = brk + 1
    return cut


def wrap(s: str, width: float, size: float, bold: bool = False) -> List[str]:
    """Greedy word wrap; words longer than a line (paths, test ids) break after a separator."""
    lines: List[str] = []
    for para in (s or "").splitlines() or [""]:
        cur = ""
        for word in para.split(" "):
            cand = f"{cur} {word}" if cur else word
            if text_width(cand, size, bold) <= width:
                cur = cand
                continue
            if text_width(word, size, bold) <= width and len(cur) > 6:  # keep "PASS name" together
                lines.append(cur)
                cur = word
                continue
            while word:  # start the word on this line, continue it below
                prefix = f"{cur} " if cur else ""
                cut = _cut(word, width - text_width(prefix, size, bold), size, bold)
                if cut >= len(word):
                    cur = prefix + word
                    break
                if cut < 3 and cur:
                    lines.append(cur)
                    cur = ""
                    continue
                cut = max(cut, 1)
                lines.append(prefix + word[:cut])
                cur, word = "", word[cut:]
        lines.append(cur)
    return lines


def _info_string(s: str) -> str:
    """Document-info strings are PDFDocEncoding, not WinAnsi: write them as UTF-16BE."""
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def _num(v: float) -> str:
    return ("%.2f" % v).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Low-level document
# ---------------------------------------------------------------------------


class _Document:
    def __init__(self) -> None:
        self.pages: List[List[str]] = []
        self.y = TOP
        self.new_page()

    def new_page(self) -> None:
        self.pages.append([])
        self.y = TOP

    @property
    def ops(self) -> List[str]:
        return self.pages[-1]

    def text(self, x: float, y: float, s: str, size: float = 9, bold: bool = False, color: Color = INK) -> None:
        self.ops.append(
            f"BT /{'F2' if bold else 'F1'} {_num(size)} Tf {_num(color[0])} {_num(color[1])} {_num(color[2])} rg "
            f"{_num(x)} {_num(y)} Td {_pdf_string(s)} Tj ET"
        )

    def rect(self, x: float, y: float, w: float, h: float, fill: Color) -> None:
        self.ops.append(f"{_num(fill[0])} {_num(fill[1])} {_num(fill[2])} rg {_num(x)} {_num(y)} {_num(w)} {_num(h)} re f")

    def hline(self, x0: float, x1: float, y: float, color: Color = LINE) -> None:
        self.ops.append(f"{_num(color[0])} {_num(color[1])} {_num(color[2])} RG 0.6 w {_num(x0)} {_num(y)} m {_num(x1)} {_num(y)} l S")

    def ensure(self, h: float) -> bool:
        """Start a new page if ``h`` points do not fit. Returns True when a page was added."""
        if self.y - h < BOTTOM:
            self.new_page()
            return True
        return False

    def heading(self, s: str, size: float = 13) -> None:
        self.ensure(size + 16 + 3 * (LEAD + 2 * PAD))  # keep a heading with the table header and a first row
        self.y -= size + 8
        self.text(MARGIN, self.y, s, size, bold=True)
        self.y -= 8

    def paragraph(self, s: str, size: float = 9, color: Color = INK, bold: bool = False) -> None:
        for line in wrap(s, CONTENT_W, size, bold):
            self.ensure(size + 3)
            self.y -= size + 3
            self.text(MARGIN, self.y, line, size, bold, color)

    def serialize(self, title: str, footer_left: str, created: str) -> bytes:
        n = len(self.pages)
        objects: List[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        add(b"<< /Type /Catalog /Pages 2 0 R >>")
        add(b"")  # pages tree, filled once page ids are known
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        info = add(
            f"<< /Title {_info_string(title)} /Producer {_info_string('reqcov ' + __version__)} "
            f"/Creator {_info_string('reqcov')} /CreationDate ({created}) >>".encode("latin-1")
        )
        kids = []
        for i, ops in enumerate(self.pages, start=1):
            footer = [
                f"{_num(0.6)} w",
                _footer_line(footer_left, f"Page {i} / {n}"),
            ]
            stream = zlib.compress("\n".join(ops + footer).encode("latin-1"))
            content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
            page = add(
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_num(PAGE_W)} {_num(PAGE_H)}] "
                    f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {content} 0 R >>"
                ).encode("latin-1")
            )
            kids.append(page)
        objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {n} >>".encode("latin-1")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, info, xref)
        return bytes(out)


def _footer_line(left: str, right: str) -> str:
    size = 7.5
    y = MARGIN
    parts = [
        f"{_num(LINE[0])} {_num(LINE[1])} {_num(LINE[2])} RG {_num(MARGIN)} {_num(y + 10)} m {_num(PAGE_W - MARGIN)} {_num(y + 10)} l S",
        f"BT /F1 {size} Tf {_num(MUTED[0])} {_num(MUTED[1])} {_num(MUTED[2])} rg {_num(MARGIN)} {_num(y)} Td {_pdf_string(left)} Tj ET",
        f"BT /F1 {size} Tf {_num(PAGE_W - MARGIN - text_width(right, size))} {_num(y)} Td {_pdf_string(right)} Tj ET",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

# A cell is a list of paragraphs; a paragraph is (text, style) with style in
# "normal" | "bold" | "muted" | "badge:<status>".
Cell = List[Tuple[str, str]]
FONT = 7.5
LEAD = FONT + 2.2
PAD = 4.0
MAX_CELL_LINES = 45  # a single row never spans more than one page


def _layout_cell(cell: Cell, width: float) -> List[Tuple[str, str]]:
    lines: List[Tuple[str, str]] = []
    for text, style in cell:
        if style.startswith("badge:"):
            lines.append((text, style))
            continue
        for line in wrap(text, width - 2 * PAD, FONT, style == "bold"):
            lines.append((line, style))
    if len(lines) > MAX_CELL_LINES:
        lines = lines[: MAX_CELL_LINES - 1] + [("… truncated, see matrix.csv", "muted")]
    return lines


def _draw_row(doc: _Document, widths: Sequence[float], laid: List[List[Tuple[str, str]]], header: bool = False) -> None:
    h = max(len(c) for c in laid) * LEAD + 2 * PAD
    top = doc.y
    if header:
        doc.rect(MARGIN, top - h, sum(widths), h, HEAD_BG)
    x = MARGIN
    for w, lines in zip(widths, laid):
        y = top - PAD - FONT
        for text, style in lines:
            if style.startswith("badge:"):
                status = style.split(":", 1)[1]
                bw = text_width(text, FONT, True) + 8
                doc.rect(x + PAD, y - 2.2, bw, FONT + 3.4, STATUS_COLORS.get(status, MUTED))
                doc.text(x + PAD + 4, y, text, FONT, True, WHITE)
            else:
                color = MUTED if (style == "muted" or header) else INK
                doc.text(x + PAD, y, text, FONT, style == "bold" or header, color)
            y -= LEAD
        x += w
    doc.y = top - h
    doc.hline(MARGIN, MARGIN + sum(widths), doc.y)


def table(doc: _Document, headers: Sequence[str], widths: Sequence[float], rows: Sequence[Sequence[Cell]],
          keep_together: bool = False) -> None:
    head = [_layout_cell([(h.upper(), "bold")], w) for h, w in zip(headers, widths)]
    head_h = max(len(c) for c in head) * LEAD + 2 * PAD
    laid_rows = [[_layout_cell(c, w) for c, w in zip(row, widths)] for row in rows]
    heights = [max(len(c) for c in laid) * LEAD + 2 * PAD for laid in laid_rows]
    doc.ensure(head_h + (sum(heights) if keep_together else (heights[0] if heights else 0)))
    _draw_row(doc, widths, head, header=True)
    for laid, h in zip(laid_rows, heights):
        if doc.ensure(h):
            _draw_row(doc, widths, head, header=True)
        _draw_row(doc, widths, laid)
    doc.y -= 6


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _loc(file: str, line: int) -> str:
    return f"{file}:{line}" if line else file


def _result_mark(status: str) -> str:
    return {"passed": "PASS", "failed": "FAIL", "error": "ERROR", "skipped": "SKIP"}.get(status, status.upper())


def render_pdf(report: CoverageReport, cfg: Optional["Config"] = None) -> bytes:
    doc = _Document()
    project = cfg.report.project if cfg is not None else ""
    counts = report.counts()
    pct = report.test_coverage_pct()

    # --- title & summary -----------------------------------------------------
    doc.y -= 18
    doc.text(MARGIN, doc.y, report.title, 18, bold=True)
    doc.y -= 6
    meta = [f"Generated {report.generated_at}"]
    if report.git_sha:
        meta.append(f"commit {report.git_sha}")
    meta.append(f"reqcov {__version__}")
    if project:
        meta.append(project)
    doc.paragraph(" · ".join(meta), 9, MUTED)
    verdict = "PASSED — no rule violation" if not report.errors else f"FAILED — {len(report.errors)} rule violation(s)"
    doc.y -= 4
    doc.paragraph(verdict, 11, STATUS_COLORS["verified"] if not report.errors else STATUS_COLORS["failing"], bold=True)

    doc.heading("Summary")
    with_test = sum(1 for rc in report.requirements.values() if rc.has_test)
    cov_txt = f"{pct:.1f}%"
    if report.delta is not None:
        base = f" {report.delta.base_sha}" if report.delta.base_sha else ""
        cov_txt += f" ({report.delta.pct_change:+.1f}% vs base{base})"
    summary = [
        ("Requirements", str(counts["total"])),
        ("Test coverage (testable requirements with a linked test)", cov_txt),
        ("Verified (all linked tests passed)", f"{report.verified_pct():.1f}%" if report.results else "no test results"),
        ("With a linked test / verified / uncovered / failing / not testable",
         f"{with_test} / {counts['verified']} / {counts['uncovered']} / {counts['failing']} / {counts['n/a']}"),
        ("Unknown ids referenced / tests without requirement", f"{len(report.unknown_ids)} / {len(report.orphan_tests)}"),
    ]
    table(doc, ["Measure", "Value"], [CONTENT_W * 0.55, CONTENT_W * 0.45], [[[(k, "normal")], [(v, "bold")]] for k, v in summary])

    doc.heading("Coverage by level")
    level_rows = []
    for level, rows in report.by_level().items():
        testable = [rc for rc in rows if rc.requirement.verification == "test" and rc.requirement.status != "obsolete"]
        cov = f"{100.0 * sum(1 for rc in testable if rc.has_test) / len(testable):.0f}%" if testable else "—"
        level_rows.append([
            [(level, "bold")],
            [(str(len(rows)), "normal")],
            [(str(sum(1 for rc in rows if rc.has_test)), "normal")],
            [(str(sum(1 for rc in rows if rc.verification_status == "verified")), "normal")],
            [(str(sum(1 for rc in rows if rc.verification_status == "uncovered")), "normal")],
            [(str(sum(1 for rc in rows if rc.has_source)), "normal")],
            [(str(sum(1 for rc in rows if rc.requirement.parents)), "normal")],
            [(cov, "bold")],
        ])
    table(doc, ["Level", "Requirements", "With test", "Verified", "Uncovered", "With source trace", "With parent", "Test coverage"],
          [CONTENT_W / 8] * 8, level_rows)

    # UNCOVERED warnings repeat the matrix, one per requirement: summarised instead of listed
    findings = sorted((f for f in report.findings if f.code != "UNCOVERED"), key=lambda f: {"error": 0, "warning": 1, "info": 2}[f.severity])
    if findings or counts["uncovered"]:
        doc.heading(f"Findings ({len(findings)})")
        if counts["uncovered"]:
            doc.paragraph(f"{counts['uncovered']} requirement(s) without a linked test are marked uncovered in the matrix.", 8.5, MUTED)
            doc.y -= 4
        if findings:
            table(doc, ["Severity", "Code", "Message", "Location"], [70, 100, 400, CONTENT_W - 570], [
                [[(f.severity, f"badge:{f.severity}")], [(f.code, "bold")], [(f.message, "normal")], [(_loc(f.file, f.line), "muted")]]
                for f in findings
            ])

    d = report.delta
    if d is not None and d.has_changes:
        doc.heading("Changes vs base" + (f" {d.base_sha}" if d.base_sha else ""))
        rows = []
        for label, changes in (("Regressed", d.regressed), ("Improved", d.improved), ("New", d.added), ("Removed", d.removed), ("Other", d.other)):
            for c in changes:
                rows.append([[(label, "bold")], [(c.req_id, "bold")], [(c.title, "normal")], [(f"{c.before or '—'} -> {c.after or '—'}", "normal")]])
        table(doc, ["Change", "Requirement", "Title", "Status"], [90, 100, 400, CONTENT_W - 590], rows)

    doc.ensure(150)  # heading + the whole sign-off table stay on one page
    doc.heading("Sign-off")
    table(doc, ["Role", "Name", "Date", "Signature"], [150, 250, 120, CONTENT_W - 520], [
        [[(role, "normal")], [("", "normal"), ("", "normal")], [("", "normal")], [("", "normal")]]
        for role in ("Prepared by", "Reviewed by", "Approved by")
    ], keep_together=True)

    # --- matrix --------------------------------------------------------------
    doc.new_page()
    doc.heading("Traceability matrix", 15)
    doc.paragraph(
        "uncovered: no linked test · covered: linked test, no result · verified: all linked tests passed · "
        "failing: a linked test failed · n/a: not verified by test",
        7.5, MUTED,
    )
    widths = [82, 200, 66, 62, 186, 110, CONTENT_W - 706]
    headers = ["Requirement", "Title", "Traces up", "Verif.", "Tests and results", "Implemented in", "Status"]
    for level, rows in report.by_level().items():
        doc.heading(f"{level} — {len(rows)} requirement(s)", 11)
        matrix_rows = []
        for rc in rows:
            r = rc.requirement
            title: Cell = [(r.title, "normal")]
            if r.status != "approved":
                title.append((f"[{r.status}]", "muted"))
            if r.jira:
                title.append(("Jira: " + ", ".join(r.jira), "muted"))
            if rc.children:
                title.append(("children: " + ", ".join(rc.children), "muted"))
            tests: Cell = [(f"{t.symbol or t.marker}  {_loc(t.file, t.line)}", "normal") for t in rc.tests] or [("—", "muted")]
            tests += [(f"{_result_mark(res.status)} {res.full_name}", "muted") for res in rc.results]
            sources: Cell = [(f"{_loc(s.file, s.line)}" + (f" {s.symbol}" if s.symbol else ""), "normal") for s in rc.sources] or [("—", "muted")]
            matrix_rows.append([
                [(r.id, "bold"), (_loc(r.file, r.line), "muted")],
                title,
                [(", ".join(r.parents) or "—", "normal" if r.parents else "muted")],
                [(r.verification, "normal")],
                tests,
                sources,
                [(rc.verification_status, f"badge:{rc.verification_status}")],
            ])
        table(doc, headers, widths, matrix_rows)

    if report.unknown_ids:
        doc.heading(f"Unknown identifiers ({len(report.unknown_ids)})")
        table(doc, ["Id", "Where", "Symbol"], [120, 400, CONTENT_W - 520], [
            [[(u.req_id, "bold")], [(_loc(u.file, u.line), "normal")], [(u.symbol or "—", "normal")]] for u in report.unknown_ids
        ])
    if report.orphan_tests:
        doc.heading(f"Tests not linked to any requirement ({len(report.orphan_tests)})")
        table(doc, ["Test", "Result"], [CONTENT_W - 120, 120], [
            [[(t.full_name, "normal")], [(t.status, "normal")]] for t in report.orphan_tests
        ])

    created = "D:" + "".join(ch for ch in report.generated_at if ch.isdigit()) + "00Z"
    footer = " · ".join(p for p in (report.title, f"commit {report.git_sha}" if report.git_sha else "", report.generated_at) if p)
    return doc.serialize(report.title, footer, created)
