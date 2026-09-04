"""File discovery helpers."""
from __future__ import annotations

import fnmatch
import glob
import os
from typing import Iterable, List


def _excluded(rel: str, exclude: Iterable[str]) -> bool:
    rel_posix = rel.replace(os.sep, "/")
    for pat in exclude:
        if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch("/" + rel_posix, pat):
            return True
        # also match directory components ("**/build/**" should exclude "build/x")
        parts = rel_posix.split("/")
        core = pat.replace("**/", "").replace("/**", "")
        if core and core in parts:
            return True
    return False


def find_files(root: str, patterns: Iterable[str], exclude: Iterable[str] = ()) -> List[str]:
    """Return sorted, de-duplicated file paths relative to root matching any pattern."""
    found = set()
    for pat in patterns:
        abs_pat = os.path.join(root, pat)
        for p in glob.glob(abs_pat, recursive=True):
            if os.path.isfile(p):
                rel = os.path.relpath(p, root)
                if not _excluded(rel, exclude):
                    found.add(rel)
    return sorted(found)


def read_text(root: str, rel: str) -> str:
    with open(os.path.join(root, rel), "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()
