"""JUnit XML parsing (pytest, Ceedling, GoogleTest, CTest, Jest, Maven... all emit it)."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import List

from .models import TestResult


def parse_junit(path: str) -> List[TestResult]:
    results: List[TestResult] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return results
    root = tree.getroot()
    for case in root.iter("testcase"):
        name = case.get("name", "")
        classname = case.get("classname", "") or ""
        file_attr = case.get("file", "") or ""
        status = "passed"
        message = ""
        for child in case:
            tag = child.tag.lower()
            if tag == "failure":
                status, message = "failed", (child.get("message") or (child.text or "")).strip()[:500]
            elif tag == "error":
                status, message = "error", (child.get("message") or (child.text or "")).strip()[:500]
            elif tag == "skipped":
                status, message = "skipped", (child.get("message") or "").strip()[:500]
        # GoogleTest puts "Suite.Name" in classname/name; Ceedling uses "file.c" classnames.
        results.append(TestResult(name=name, classname=classname, status=status, file=file_attr, message=message))
    return results


def load_results(root: str, files: List[str]) -> List[TestResult]:
    out: List[TestResult] = []
    for rel in files:
        out.extend(parse_junit(os.path.join(root, rel)))
    return out


def match_results(symbol: str, file: str, results: List[TestResult]) -> List[TestResult]:
    """Find results for a test symbol detected next to a marker.

    Matching is name based: exact test name, ``Suite.Name`` for GoogleTest, or a
    parametrised pytest id (``test_x[case]``). Ceedling reports ``classname`` as the
    test file, so we also accept a file-stem match combined with the function name.
    """
    if not symbol:
        return []
    short = symbol.split(".")[-1]
    hits: List[TestResult] = []
    for r in results:
        rname = r.name
        base = rname.split("[")[0]
        if base == short or rname == symbol or f"{r.classname}.{rname}" == symbol:
            hits.append(r)
            continue
        if "." in symbol and r.classname.endswith(symbol.split(".")[0]) and base == short:
            hits.append(r)
    return hits
