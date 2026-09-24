"""ReqIF (OMG Requirements Interchange Format 1.x) import and export.

ReqIF is what DOORS, Polarion, Jama, codebeamer, Enterprise Architect... exchange. Import reads
``.reqif`` files and ``.reqifz`` archives:

* every SPEC-OBJECT whose id attribute matches ``id_pattern`` becomes a requirement; objects
  without one (information objects) and chapter headings are skipped. DOORS exports the
  absolute number as ``ReqIF.ForeignID``: set ``reqif.id_prefix: "SRS-"`` to get ``SRS-12``, or
  one prefix per module (SPECIFICATION) when an export holds several: ``{"SRS": "SRS-", ...}``;
* attributes are matched by LONG-NAME, case-insensitively and without the ``ReqIF.`` prefix:
  ``ReqIF.ForeignID`` / ``ID`` → id, ``ReqIF.Name`` / ``ReqIF.ChapterName`` / ``Title`` → title,
  ``ReqIF.Text`` / ``Description`` → text, and the same ``Verification`` / ``Status`` /
  ``Tags`` / ``Jira`` / ``Parent`` names as Markdown and YAML;
* SPEC-RELATIONs become parent links (by default the TARGET is the parent, ``reqif.parent_end``
  flips it, ``reqif.relation_types`` keeps only some relation types).

Export writes ``requirements.reqif``: one SPECIFICATION per level, parent links as
SPEC-RELATIONs, requirements read from ReqIF under their original SPEC-OBJECT IDENTIFIER, and
the coverage computed by reqcov as ``reqcov.*`` attributes, so the result of a CI run can be
imported back into the requirements tool.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from . import __version__
from .models import CoverageReport, Finding, Requirement
from .requirements import (
    JIRA_KEYS,
    PARENT_KEYS,
    STATUS_KEYS,
    TAG_KEYS,
    TEXT_KEYS,
    TITLE_KEYS,
    VERIFICATION_KEYS,
    _norm_verification,
    _split_ids,
    split_jira,
)

if TYPE_CHECKING:  # pragma: no cover
    from .config import Config, ReqifConfig

NS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
XHTML_NS = "http://www.w3.org/1999/xhtml"

ID_KEYS = ("foreignid", "id", "identifier", "req_id", "reqid", "requirement_id", "object_identifier", "key", "uid")
REQIF_TITLE_KEYS = ("name", "chaptername") + TITLE_KEYS + ("heading", "object_heading")
REQIF_TEXT_KEYS = TEXT_KEYS + ("object_text",)
_XHTML_BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _iter(el: ET.Element, name: str):
    return (e for e in el.iter() if _local(e.tag) == name)


def _child(el: ET.Element, name: str) -> Optional[ET.Element]:
    return next((c for c in el if _local(c.tag) == name), None)


def _ref(el: Optional[ET.Element], suffix: str = "-REF") -> str:
    """Text of the first ``*-REF`` element under ``el`` (``<TYPE><SPEC-OBJECT-TYPE-REF>x</...>``)."""
    if el is None:
        return ""
    for e in el.iter():
        if _local(e.tag).endswith(suffix) and e.text:
            return e.text.strip()
    return ""


def _xhtml_text(el: ET.Element) -> str:
    parts: List[str] = []

    def walk(e: ET.Element) -> None:
        block = _local(e.tag) in _XHTML_BLOCKS
        if block:
            parts.append("\n")
        if e.text:
            parts.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                parts.append(c.tail)
        if block:
            parts.append("\n")

    walk(el)
    lines = [re.sub(r"\s+", " ", l).strip() for l in "".join(parts).splitlines()]
    return "\n".join(l for l in lines if l)


def _norm_name(name: str) -> str:
    n = name.strip().lower()
    if n.startswith("reqif."):
        n = n[len("reqif."):]
    return re.sub(r"[\s\-]+", "_", n)


def _read(root: str, rel: str) -> Tuple[bytes, bool]:
    """Return (xml bytes, has_meaningful_lines). A .reqifz is a zip holding one or more .reqif."""
    path = os.path.join(root, rel)
    if rel.lower().endswith(".reqifz"):
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.lower().endswith(".reqif")), None)
            if name is None:
                raise ValueError("archive contains no .reqif file")
            return z.read(name), False
    with open(path, "rb") as fh:
        return fh.read(), True


def _object_values(obj: ET.Element, attr_names: Dict[str, str], enum_names: Dict[str, str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    container = _child(obj, "VALUES")
    if container is None:
        return values
    for v in container:
        kind = _local(v.tag)
        if not kind.startswith("ATTRIBUTE-VALUE-"):
            continue
        ref = _ref(_child(v, "DEFINITION"))
        name = attr_names.get(ref, ref)
        if kind == "ATTRIBUTE-VALUE-XHTML":
            the = _child(v, "THE-VALUE")
            val = _xhtml_text(the) if the is not None else ""
        elif kind == "ATTRIBUTE-VALUE-ENUMERATION":
            refs = [e.text.strip() for e in _iter(v, "ENUM-VALUE-REF") if e.text]
            val = ", ".join(enum_names.get(r, r) for r in refs)
        else:
            val = v.get("THE-VALUE", "")
        values[name] = val
    return values


def _requirement(values: Dict[str, str], obj: ET.Element, id_re: re.Pattern, cfg: Optional["ReqifConfig"],
                 prefix: str = "") -> Optional[Requirement]:
    by_norm: Dict[str, str] = {}
    for k, v in values.items():
        by_norm.setdefault(_norm_name(k), v)

    if by_norm.get("chaptername", "").strip() and not any(by_norm.get(k, "").strip() for k in REQIF_TEXT_KEYS):
        return None  # a chapter heading, not a requirement

    rid = ""
    id_attribute = _norm_name(cfg.id_attribute) if cfg is not None and cfg.id_attribute else ""
    if id_attribute or prefix:  # explicit mapping: trust it, the id pattern may not apply to the raw value
        raw = by_norm.get(id_attribute, "") if id_attribute else next((by_norm[k] for k in ID_KEYS if by_norm.get(k, "").strip()), "")
        rid = prefix + raw.strip() if raw.strip() else ""
    else:
        for k in ID_KEYS:
            v = by_norm.get(k, "").strip()
            if v and id_re.fullmatch(v):
                rid = v
                break
        if not rid:  # any attribute that is exactly an id
            rid = next((v.strip() for v in values.values() if id_re.fullmatch(v.strip())), "")
    if not rid:
        return None

    req = Requirement(id=rid)
    req.title = next((by_norm[k].strip() for k in REQIF_TITLE_KEYS if by_norm.get(k, "").strip()), "")
    req.text = next((by_norm[k].strip() for k in REQIF_TEXT_KEYS if by_norm.get(k, "").strip()), "")
    if not req.title:
        req.title = (obj.get("LONG-NAME") or "").strip() or (req.text.splitlines()[0][:120] if req.text else "")
    for k, v in by_norm.items():
        if not v.strip():
            continue
        if k in PARENT_KEYS:
            req.parents.extend(p for p in _split_ids(v, id_re) if p not in req.parents)
        elif k in VERIFICATION_KEYS:
            req.verification = _norm_verification(v)
        elif k in STATUS_KEYS:
            req.status = v.strip().lower()
        elif k in TAG_KEYS:
            req.tags.extend(t.strip() for t in v.split(",") if t.strip())
        elif k in JIRA_KEYS:
            req.jira.extend(split_jira(v))
    return req


def _prefixes(root: ET.Element, cfg: Optional["ReqifConfig"]) -> Dict[str, str]:
    """SPEC-OBJECT IDENTIFIER → id prefix.

    ``id_prefix`` is one string for every object, or a mapping from SPECIFICATION LONG-NAME (a
    DOORS module) to its prefix, for exports holding several modules. Objects outside the listed
    specifications get no prefix and must carry a full id.
    """
    if cfg is None or not cfg.id_prefix:
        return {}
    if isinstance(cfg.id_prefix, str):
        return {obj.get("IDENTIFIER", ""): cfg.id_prefix for obj in _iter(root, "SPEC-OBJECT")}
    by_name = {str(k).strip().lower(): str(v) for k, v in cfg.id_prefix.items()}
    out: Dict[str, str] = {}
    for spec in _iter(root, "SPECIFICATION"):
        prefix = by_name.get((spec.get("LONG-NAME") or "").strip().lower())
        if prefix is None:
            continue
        for ref in _iter(spec, "SPEC-OBJECT-REF"):
            if ref.text:
                out.setdefault(ref.text.strip(), prefix)
    return out


def parse_reqif(rel: str, data: bytes, id_re: re.Pattern, findings: List[Finding],
                cfg: Optional["ReqifConfig"] = None, with_lines: bool = True) -> List[Requirement]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        findings.append(Finding("error", "REQIF_PARSE", f"{exc}", rel))
        return []

    enum_names = {e.get("IDENTIFIER", ""): e.get("LONG-NAME", "") or e.get("IDENTIFIER", "") for e in _iter(root, "ENUM-VALUE")}
    attr_names = {
        e.get("IDENTIFIER", ""): e.get("LONG-NAME", "") or e.get("IDENTIFIER", "")
        for e in root.iter()
        if _local(e.tag).startswith("ATTRIBUTE-DEFINITION-") and not _local(e.tag).endswith("-REF") and e.get("IDENTIFIER")
    }
    rel_types = {e.get("IDENTIFIER", ""): e.get("LONG-NAME", "") for e in _iter(root, "SPEC-RELATION-TYPE")}
    text = data.decode("utf-8", errors="replace") if with_lines else ""

    by_ident: Dict[str, Requirement] = {}
    reqs: List[Requirement] = []
    prefixes = _prefixes(root, cfg)
    for obj in _iter(root, "SPEC-OBJECT"):
        ident = obj.get("IDENTIFIER", "")
        req = _requirement(_object_values(obj, attr_names, enum_names), obj, id_re, cfg, prefixes.get(ident, ""))
        if req is None:
            continue
        req.file = rel
        req.reqif_id = ident
        if text:
            pos = text.find(f'IDENTIFIER="{ident}"')
            req.line = text.count("\n", 0, pos) + 1 if pos >= 0 else 0
        by_ident[ident] = req
        reqs.append(req)

    parent_end = cfg.parent_end if cfg is not None else "target"
    wanted = {t.lower() for t in cfg.relation_types} if cfg is not None and cfg.relation_types else None
    for relation in _iter(root, "SPEC-RELATION"):
        if wanted is not None and rel_types.get(_ref(_child(relation, "TYPE")), "").lower() not in wanted:
            continue
        src = by_ident.get(_ref(_child(relation, "SOURCE")))
        dst = by_ident.get(_ref(_child(relation, "TARGET")))
        if src is None or dst is None:
            continue
        child, parent = (src, dst) if parent_end == "target" else (dst, src)
        if parent.id not in child.parents:
            child.parents.append(parent.id)
    return reqs


def load_reqif(root: str, rel: str, id_re: re.Pattern, findings: List[Finding], cfg: Optional["ReqifConfig"] = None) -> List[Requirement]:
    try:
        data, with_lines = _read(root, rel)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        findings.append(Finding("error", "REQIF_PARSE", f"{exc}", rel))
        return []
    return parse_reqif(rel, data, id_re, findings, cfg, with_lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

# (identifier suffix, LONG-NAME, xhtml?) — the reqcov.* attributes are the coverage of this run
_EXPORT_ATTRIBUTES = [
    ("id", "ReqIF.ForeignID", False),
    ("name", "ReqIF.Name", False),
    ("text", "ReqIF.Text", True),
    ("level", "Level", False),
    ("verification", "Verification", False),
    ("status", "Status", False),
    ("tags", "Tags", False),
    ("jira", "Jira", False),
    ("coverage", "reqcov.Coverage", False),
    ("tests", "reqcov.Tests", False),
    ("results", "reqcov.Results", False),
    ("sources", "reqcov.Sources", False),
    ("location", "reqcov.Location", False),
    ("commit", "reqcov.Commit", False),
]


def _xml_id(prefix: str, value: str) -> str:
    return prefix + re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _timestamp(report: CoverageReport) -> str:
    try:
        t = _dt.datetime.strptime(report.generated_at, "%Y-%m-%d %H:%M UTC")
    except ValueError:
        t = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def render_reqif(report: CoverageReport, cfg: "Config") -> str:
    ET.register_namespace("", NS)
    ET.register_namespace("xhtml", XHTML_NS)
    q = lambda t: f"{{{NS}}}{t}"  # noqa: E731
    now = _timestamp(report)

    def sub(parent: ET.Element, tag: str, text: Optional[str] = None, **attrs: str) -> ET.Element:
        e = ET.SubElement(parent, q(tag), {k.replace("_", "-"): v for k, v in attrs.items()})
        if text is not None:
            e.text = text
        return e

    def ident(parent: ET.Element, tag: str, identifier: str, long_name: str = "") -> ET.Element:
        attrs = {"IDENTIFIER": identifier, "LAST_CHANGE": now}
        if long_name:
            attrs["LONG_NAME"] = long_name
        return sub(parent, tag, **attrs)

    doc = ET.Element(q("REQ-IF"))
    header = sub(sub(doc, "THE-HEADER"), "REQ-IF-HEADER", IDENTIFIER="_reqcov_header")
    sub(header, "COMMENT", f"Requirements coverage exported by reqcov{' at commit ' + report.git_sha if report.git_sha else ''}")
    sub(header, "CREATION-TIME", now)
    sub(header, "REQ-IF-TOOL-ID", "reqcov")
    sub(header, "REQ-IF-VERSION", "1.0")
    sub(header, "SOURCE-TOOL-ID", f"reqcov {__version__}")
    sub(header, "TITLE", report.title)

    content = sub(sub(doc, "CORE-CONTENT"), "REQ-IF-CONTENT")
    datatypes = sub(content, "DATATYPES")
    s_dt = ident(datatypes, "DATATYPE-DEFINITION-STRING", "_dt_string", "String")
    s_dt.set("MAX-LENGTH", "65535")
    ident(datatypes, "DATATYPE-DEFINITION-XHTML", "_dt_xhtml", "XHTML")

    types = sub(content, "SPEC-TYPES")
    obj_type = ident(types, "SPEC-OBJECT-TYPE", "_type_requirement", "Requirement")
    attrs_el = sub(obj_type, "SPEC-ATTRIBUTES")
    for key, name, xhtml in _EXPORT_ATTRIBUTES:
        kind = "XHTML" if xhtml else "STRING"
        a = ident(attrs_el, f"ATTRIBUTE-DEFINITION-{kind}", f"_attr_{key}", name)
        sub(sub(a, "TYPE"), f"DATATYPE-DEFINITION-{kind}-REF", "_dt_xhtml" if xhtml else "_dt_string")
    ident(types, "SPEC-RELATION-TYPE", "_type_parent", "Parent")
    ident(types, "SPECIFICATION-TYPE", "_type_specification", "Specification")

    objects = sub(content, "SPEC-OBJECTS")
    object_ids: Dict[str, str] = {}
    used = {e.get("IDENTIFIER") for e in doc.iter() if e.get("IDENTIFIER")}
    # a requirement read from ReqIF keeps its SPEC-OBJECT IDENTIFIER, so the requirements tool can
    # match it with its own object on import; generated identifiers take the names left over
    for rc in report.requirements.values():
        if rc.requirement.reqif_id and rc.requirement.reqif_id not in used:
            object_ids[rc.requirement.id] = rc.requirement.reqif_id
            used.add(rc.requirement.reqif_id)

    def fresh(candidate: str) -> str:
        while candidate in used:  # two ids sanitised to the same NCName, or taken by an original
            candidate += "_"
        used.add(candidate)
        return candidate

    for rc in report.requirements.values():
        r = rc.requirement
        oid = object_ids.get(r.id) or fresh(_xml_id("_req_", r.id))
        object_ids[r.id] = oid
        obj = ident(objects, "SPEC-OBJECT", oid)
        sub(sub(obj, "TYPE"), "SPEC-OBJECT-TYPE-REF", "_type_requirement")
        values = sub(obj, "VALUES")
        fields = {
            "id": r.id,
            "name": r.title,
            "text": r.text,
            "level": r.level,
            "verification": r.verification,
            "status": r.status,
            "tags": ", ".join(r.tags),
            "jira": ", ".join(r.jira),
            "coverage": rc.verification_status,
            "tests": "\n".join(f"{t.symbol or t.marker} ({t.file}:{t.line})" for t in rc.tests),
            "results": "\n".join(f"{res.full_name}: {res.status}" for res in rc.results),
            "sources": "\n".join(f"{s.file}:{s.line}" + (f" {s.symbol}" if s.symbol else "") for s in rc.sources),
            "location": f"{r.file}:{r.line}" if r.line else r.file,
            "commit": report.git_sha,
        }
        for key, _name, xhtml in _EXPORT_ATTRIBUTES:
            val = fields[key]
            if not val:
                continue
            if xhtml:
                v = sub(values, "ATTRIBUTE-VALUE-XHTML")
                sub(sub(v, "DEFINITION"), "ATTRIBUTE-DEFINITION-XHTML-REF", f"_attr_{key}")
                div = ET.SubElement(sub(v, "THE-VALUE"), f"{{{XHTML_NS}}}div")
                lines = val.splitlines()
                div.text = lines[0]
                for line in lines[1:]:
                    ET.SubElement(div, f"{{{XHTML_NS}}}br").tail = line
            else:
                v = sub(values, "ATTRIBUTE-VALUE-STRING", THE_VALUE=val)
                sub(sub(v, "DEFINITION"), "ATTRIBUTE-DEFINITION-STRING-REF", f"_attr_{key}")

    relations = sub(content, "SPEC-RELATIONS")
    for rc in report.requirements.values():
        for p in rc.requirement.parents:
            if p not in object_ids:
                continue
            rel = ident(relations, "SPEC-RELATION", fresh(_xml_id("_rel_", f"{rc.requirement.id}__{p}")))
            sub(sub(rel, "TYPE"), "SPEC-RELATION-TYPE-REF", "_type_parent")
            sub(sub(rel, "SOURCE"), "SPEC-OBJECT-REF", object_ids[rc.requirement.id])
            sub(sub(rel, "TARGET"), "SPEC-OBJECT-REF", object_ids[p])

    specs = sub(content, "SPECIFICATIONS")
    for level, rows in report.by_level().items():
        spec = ident(specs, "SPECIFICATION", fresh(_xml_id("_spec_", level)), level)
        sub(sub(spec, "TYPE"), "SPECIFICATION-TYPE-REF", "_type_specification")
        children = sub(spec, "CHILDREN")
        for rc in rows:
            h = ident(children, "SPEC-HIERARCHY", fresh("_h" + object_ids[rc.requirement.id]))
            sub(sub(h, "OBJECT"), "SPEC-OBJECT-REF", object_ids[rc.requirement.id])

    if hasattr(ET, "indent"):
        ET.indent(doc)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(doc, encoding="unicode") + "\n"
