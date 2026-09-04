"""Scan source and test files for requirement markers.

Recognised marker shapes (any language, inside comments, decorators, strings...)::

    // @req SRS-001
    # @req SRS-001, SRS-002
    /* @verifies SRS-003 */
    @pytest.mark.req("SRS-004")
    @pytest.mark.req("SRS-004", "SRS-005")
    // @implements SRS-006        (in source files -> code trace)
    TEST_REQ(SRS-007)             (any token followed by ids works if the verb is configured)

The verb list is configurable (``markers`` in reqcov.yml). Ids are matched with ``id_pattern``.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .files import read_text
from .models import Reference

_DEF_PATTERNS = [
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\("),  # python
    re.compile(r"^\s*TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"),  # googletest
    re.compile(r"^\s*(?:static\s+)?void\s+(test_?\w*)\s*\("),  # unity / ceedling
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]"),  # rust
    re.compile(r"^\s*(?:it|test|describe)\s*\(\s*['\"`](.+?)['\"`]"),  # js/ts
    re.compile(r"^\s*(?:public\s+|private\s+)?(?:static\s+)?void\s+(\w+)\s*\("),  # java / c#
    re.compile(r"^\s*func\s+(Test\w+)\s*\("),  # go
    re.compile(r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct)\s+(\w+)"),  # C++ class / struct
    # generic C/C++ definition: `static uint16_t crc16(`, `frame_status_t frame_validate(`, `Foo::bar(`
    re.compile(r"^\s*(?:(?:static|inline|extern|constexpr|virtual)\s+)*[A-Za-z_][\w:<>]*(?:\s*\*+\s*|\s+)\**([A-Za-z_]\w*(?:::\w+)?)\s*\("),
]
_KEYWORDS = {"return", "else", "if", "while", "for", "switch", "case", "sizeof", "new", "delete", "throw", "goto", "do"}


def _symbol_from_line(line: str) -> Optional[str]:
    for pat in _DEF_PATTERNS:
        m = pat.match(line)
        if m:
            groups = [g for g in m.groups() if g]
            if any(g in _KEYWORDS for g in groups) or line.lstrip().split(" ")[0] in _KEYWORDS:
                continue
            return ".".join(groups)
    return None


def _find_symbol(lines: List[str], idx: int) -> str:
    # forward first (marker as decorator / leading comment)
    for j in range(idx, min(len(lines), idx + 8)):
        s = _symbol_from_line(lines[j])
        if s:
            return s
    # then backwards (marker inside body)
    for j in range(idx - 1, max(-1, idx - 60), -1):
        s = _symbol_from_line(lines[j])
        if s:
            return s
    return ""


def build_marker_regex(markers: List[str], id_pattern: str) -> re.Pattern:
    verbs = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
    # verb, optional punctuation, then a span that must start with an id
    return re.compile(
        r"(?<![A-Za-z0-9_])@?(?P<verb>" + verbs + r")\b\s*[:=(\[]?\s*(?P<span>[\"'`]?" + id_pattern + r".*)$",
        re.IGNORECASE,
    )


def scan_files(root: str, files: List[str], kind: str, markers: List[str], id_pattern: str) -> List[Reference]:
    marker_re = build_marker_regex(markers, id_pattern)
    id_re = re.compile(id_pattern)
    refs: List[Reference] = []
    for rel in files:
        try:
            text = read_text(root, rel)
        except (OSError, UnicodeDecodeError):
            continue
        if "\x00" in text[:4096]:  # binary
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for m in marker_re.finditer(line):
                span = m.group("span")
                # cut the span at a closing bracket / comment end to avoid grabbing trailing prose ids
                span = re.split(r"\*/|-->|\)\s*$", span)[0]
                ids = id_re.findall(span)
                if not ids:
                    continue
                symbol = _find_symbol(lines, i)
                for rid in dict.fromkeys(ids):  # unique, ordered
                    refs.append(Reference(req_id=rid, file=rel, line=i + 1, kind=kind, marker=m.group("verb").lower(), symbol=symbol))
    return refs
