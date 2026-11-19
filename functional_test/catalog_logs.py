"""Conservative matching of FAIG Traffic Log detail records to one test run.

A fresh unique marker is embedded in the user's test prompt. FAIG 8.0.2 was
observed to store it in detail.prompt.original. A missing marker is never
inferred from key/timestamp alone; callers must count requests independently.
"""
from __future__ import annotations
import re
from typing import Any, Callable

MARKER = re.compile(r'\[faig-test-[0-9a-f]{32}\]')
VERDICTS = {'log', 'alert', 'redact', 'block'}


def match_rows(rows: list[dict[str, Any]], *, key_name: str, since_ms: int,
               marker: str, fetch_detail: Callable[[str], dict[str, Any]]) -> list[dict[str, str]]:
    """Return positively identified rows; missing/unreadable rows are omitted.

    The evaluator separately marks a run incomplete when the number of returned
    rows is smaller than the number of requests. No prompt content is returned.
    """
    if not isinstance(marker, str) or not MARKER.fullmatch(marker):
        raise ValueError('invalid run marker')
    if not isinstance(rows, list) or not isinstance(key_name, str) or not key_name:
        raise ValueError('invalid traffic rows or key')
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get('keyAlias') != key_name:
            continue
        timestamp = row.get('timeStamp')
        if not isinstance(timestamp, (int, float)) or timestamp < since_ms:
            continue
        uid = row.get('uuid')
        if not isinstance(uid, str) or not uid or uid in seen:
            continue
        seen.add(uid)
        try:
            detail = fetch_detail(uid)
        except Exception:  # A failed detail lookup cannot be treated as matching evidence.
            continue
        if not isinstance(detail, dict) or detail.get('uuid') != uid or detail.get('keyAlias') != key_name:
            continue
        prompt = detail.get('prompt')
        original = prompt.get('original') if isinstance(prompt, dict) else None
        if not isinstance(original, str) or marker not in original:
            continue
        verdict = detail.get('verdictLabel')
        if not isinstance(verdict, str) or verdict.lower() not in VERDICTS:
            continue
        result.append({'uuid': uid, 'verdict': verdict.lower()})
    return result
