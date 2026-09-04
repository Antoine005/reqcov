"""Requirement parsers: Markdown, YAML lists, Doorstop items."""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

import yaml

from .files import read_text
from .models import Finding, Requirement

VERIFICATION_METHODS = {"test", "analysis", "inspection", "demonstration", "review", "none", "n/a"}

# Metadata keys accepted in Markdown bodies and YAML items (lowercase).
PARENT_KEYS = ("parent", "parents", "refines", "derived_from", "derived-from", "traces", "trace", "links", "satisfies")
VERIFICATION_KEYS = ("verification", "verify", "verified_by", "method")
STATUS_KEYS = ("status",)
TAG_KEYS = ("tags", "tag", "labels")
TITLE_KEYS = ("title", "header", "name", "summary")
TEXT_KEYS = ("text", "description", "statement", "body")


def _split_ids(value, id_re: re.Pattern) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for v in value:
            out.extend(_split_ids(v, id_re))
        return out
    if isinstance(value, dict):
        # Doorstop link form: {SRS001: hash}
        return [str(k) for k in value.keys()]
    s = str(value)
    ids = id_re.findall(s)
    if ids:
        return ids
    # fallback: comma separated tokens (for custom id schemes)
    return [t.strip() for t in re.split(r"[,\s]+", s) if t.strip() and t.strip() != "-"]


def _norm_verification(v) -> str:
    if v is None:
        return "test"
    s = str(v).strip().lower()
    if s in ("t", "ut", "unit", "unit test", "unit-test", "testing"):
        return "test"
    if s in ("a", "analyse"):
        return "analysis"
    if s in ("i",):
        return "inspection"
    if s in ("d", "demo"):
        return "demonstration"
    if s in ("none", "n/a", "na", "-", ""):
        return "none"
    return s


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_MD_META_RE = re.compile(r"^\s*(?:[-*]\s*)?\**\s*([A-Za-z_ -]+?)\s*\**\s*:\s*\**\s*(.+?)\s*\**\s*$")


def parse_markdown(rel: str, text: str, id_re: re.Pattern, findings: List[Finding]) -> List[Requirement]:
    """A requirement starts at a heading (or bold line) that contains an id.

    Supported heading shapes::

        ## SRS-001 — Title
        ### [SRS-001] Title
        **SRS-001**: Title
        - SRS-001: Title            (list form, body = following indented lines)

    Body lines of the form ``Parent: SYS-1, SYS-2``, ``Verification: test``,
    ``Status: draft``, ``Tags: a, b`` are metadata; everything else is the text.
    """
    reqs: List[Requirement] = []
    lines = text.splitlines()
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    bold_re = re.compile(r"^\*\*\s*(" + id_re.pattern + r")\s*\*\*\s*[:\-—–]?\s*(.*)$")
    list_re = re.compile(r"^\s*[-*]\s+\**(" + id_re.pattern + r")\**\s*[:\-—–]\s*(.*)$")

    current: Optional[Requirement] = None
    current_level = 0
    body: List[str] = []

    def flush():
        nonlocal current, body
        if current is not None:
            _apply_body(current, body, id_re)
            reqs.append(current)
        current, body = None, []

    for i, line in enumerate(lines, start=1):
        m = heading_re.match(line)
        start: Optional[Tuple[str, str, int]] = None
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            idm = id_re.search(title)
            if idm and title.find(idm.group(0)) <= 2:  # id at (or right after '[') start of heading
                rest = title[idm.end():].strip(" :—–-]\t")
                start = (idm.group(0), rest, level)
            else:
                # a heading without id closes the current requirement if it is not deeper
                if current is not None and level <= current_level:
                    flush()
                continue
        else:
            bm = bold_re.match(line)
            lm = list_re.match(line)
            if bm:
                start = (bm.group(1), bm.group(2).strip(), 99)
            elif lm:
                start = (lm.group(1), lm.group(2).strip(), 99)

        if start:
            flush()
            rid, title, level = start
            current = Requirement(id=rid, title=title, file=rel, line=i)
            current_level = level
            continue

        if current is not None:
            body.append(line)
    flush()
    return reqs


_INLINE_META_RE = re.compile(
    r"(?:^|(?<=[.;,)])\s*|\s+)\**(Verification|Verify|Method|Parents?|Refines|Status|Tags?)\**\s*:\s*\**([^.;|]+?)\**\s*(?=$|[.;|])",
    re.IGNORECASE,
)


def _extract_inline_meta(req: Requirement, id_re: re.Pattern) -> None:
    """Handle one-line requirements: ``- SWR-1: text. Verification: test. Parent: SYS-1``."""
    if not req.title:
        return

    def repl(m: re.Match) -> str:
        key, val = m.group(1).lower(), m.group(2).strip()
        if key in PARENT_KEYS:
            req.parents.extend(_split_ids(val, id_re))
        elif key in VERIFICATION_KEYS:
            req.verification = _norm_verification(val)
        elif key in STATUS_KEYS:
            req.status = val.lower()
        elif key in TAG_KEYS:
            req.tags.extend(t.strip() for t in val.split(",") if t.strip())
        return ""

    cleaned = _INLINE_META_RE.sub(repl, req.title)
    req.title = re.sub(r"\s{2,}", " ", cleaned).strip(" .;")
    if not req.text:
        req.text = req.title


def _apply_body(req: Requirement, body: List[str], id_re: re.Pattern) -> None:
    _extract_inline_meta(req, id_re)
    text_lines: List[str] = []
    for line in body:
        m = _MD_META_RE.match(line)
        if m:
            key = m.group(1).strip().lower().replace(" ", "_")
            val = m.group(2).strip()
            if key in PARENT_KEYS:
                req.parents.extend(_split_ids(val, id_re))
                continue
            if key in VERIFICATION_KEYS:
                req.verification = _norm_verification(val)
                continue
            if key in STATUS_KEYS:
                req.status = val.lower()
                continue
            if key in TAG_KEYS:
                req.tags.extend(t.strip() for t in val.split(",") if t.strip())
                continue
            if key in TITLE_KEYS and not req.title:
                req.title = val
                continue
        text_lines.append(line)
    req.text = "\n".join(text_lines).strip()
    if not req.title:
        first = next((l.strip() for l in text_lines if l.strip()), "")
        req.title = first[:120]


# ---------------------------------------------------------------------------
# YAML
# ---------------------------------------------------------------------------


def _req_from_mapping(d: Dict, rel: str, id_re: re.Pattern, default_id: Optional[str] = None) -> Optional[Requirement]:
    low = {str(k).lower(): v for k, v in d.items()}
    rid = low.get("id") or low.get("uid") or low.get("key") or default_id
    if not rid:
        return None
    req = Requirement(id=str(rid), file=rel, line=0)
    for k in TITLE_KEYS:
        if k in low and low[k]:
            req.title = str(low[k]).strip()
            break
    for k in TEXT_KEYS:
        if k in low and low[k]:
            req.text = str(low[k]).strip()
            break
    for k in PARENT_KEYS:
        if k in low:
            req.parents.extend(_split_ids(low[k], id_re))
    for k in VERIFICATION_KEYS:
        if k in low:
            req.verification = _norm_verification(low[k])
            break
    for k in STATUS_KEYS:
        if k in low and low[k] is not None:
            req.status = str(low[k]).lower()
    if "active" in low and low["active"] is False:
        req.status = "obsolete"
    if "normative" in low and low["normative"] is False and req.verification == "test":
        req.verification = "none"
    for k in TAG_KEYS:
        if k in low and low[k]:
            v = low[k]
            req.tags.extend([str(x) for x in v] if isinstance(v, list) else [t.strip() for t in str(v).split(",")])
    if not req.title:
        req.title = req.text.splitlines()[0][:120] if req.text else ""
    return req


def parse_yaml(rel: str, text: str, id_re: re.Pattern, findings: List[Finding]) -> List[Requirement]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        findings.append(Finding("error", "YAML_PARSE", f"{exc}", rel))
        return []
    if data is None:
        return []
    reqs: List[Requirement] = []
    stem = os.path.splitext(os.path.basename(rel))[0]

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        low = {str(k).lower(): v for k, v in data.items()}
        if "requirements" in low and isinstance(low["requirements"], list):
            items = low["requirements"]
        elif "text" in low and ("links" in low or "active" in low or "normative" in low or "level" in low):
            # Doorstop item: one requirement per file, id = file stem
            r = _req_from_mapping(data, rel, id_re, default_id=stem)
            return [r] if r else []
        elif "id" in low:
            r = _req_from_mapping(data, rel, id_re)
            return [r] if r else []
        else:
            # mapping keyed by id
            items = []
            for k, v in data.items():
                if isinstance(v, dict):
                    v = dict(v)
                    v.setdefault("id", k)
                    items.append(v)
                elif isinstance(v, str):
                    items.append({"id": k, "text": v})
    else:
        return []

    for item in items:
        if isinstance(item, dict):
            r = _req_from_mapping(item, rel, id_re)
            if r:
                reqs.append(r)
        elif isinstance(item, str):
            m = id_re.search(item)
            if m:
                reqs.append(Requirement(id=m.group(0), title=item[m.end():].strip(" :-—"), file=rel))
    return reqs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def load_requirements(root: str, files: List[str], id_pattern: str, findings: List[Finding]) -> Dict[str, Requirement]:
    id_re = re.compile(id_pattern)
    out: Dict[str, Requirement] = {}
    for rel in files:
        text = read_text(root, rel)
        ext = os.path.splitext(rel)[1].lower()
        if ext in (".yml", ".yaml"):
            reqs = parse_yaml(rel, text, id_re, findings)
        else:
            reqs = parse_markdown(rel, text, id_re, findings)
        for r in reqs:
            if r.id in out:
                findings.append(
                    Finding("error", "DUPLICATE_ID", f"{r.id} defined twice (also in {out[r.id].file}:{out[r.id].line})", r.file, r.line)
                )
                continue
            if r.verification not in VERIFICATION_METHODS:
                findings.append(
                    Finding("warning", "UNKNOWN_VERIFICATION", f"{r.id}: unknown verification method '{r.verification}' (treated as test)", r.file, r.line)
                )
                r.verification = "test"
            out[r.id] = r
    return out
