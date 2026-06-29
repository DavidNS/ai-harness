"""Knowledge-source patch rendering helpers."""

from __future__ import annotations

import json
import re
from typing import Iterable, Mapping

from .contracts import CLAIMS_FILE, MANIFEST_FILE, PENDING_PATCH_ROOT, RELATIONS_FILE
from .validation import _fail


def render_jsonl(items: Iterable[Mapping[str, object]]) -> str:
    return "".join(json.dumps(dict(item), ensure_ascii=False, sort_keys=True) + "\n" for item in items)


def pending_patch_path(run_id: str, filename: str = "") -> str:
    if not run_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", run_id):
        _fail("run_id is invalid for pending knowledge patch path")
    if filename:
        if filename not in {MANIFEST_FILE, CLAIMS_FILE, RELATIONS_FILE, "reconciliation_jobs.json", "reducer_patch.json"}:
            _fail("pending patch filename is unsupported")
        return f"{PENDING_PATCH_ROOT}/{run_id}/{filename}"
    return f"{PENDING_PATCH_ROOT}/{run_id}"
