"""Synthetic sensitive-data detection used as test evidence (stdlib only).

Change 2026-11-20: moved here from functional_test/result_contract.py so the
8.0.2 lab chatbot depends only on catalog802. The patterns are unchanged;
tests/test_catalog_sensitive.py keeps both copies identical until the old
functional_test copy is retired.
"""
from __future__ import annotations

import json
import re
from typing import Any

PATTERNS = (
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",          # email
    r"\b\d{3}-\d{2}-\d{4}\b",                                        # SSN
    r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b",         # US phone
    r"\b(?:\d{4}[- ]?){3}\d{4}\b|\b\d{13,19}\b",                     # card number
    r"\bcredit_card_number\b",
)


def contains_sensitive(value: Any) -> bool:
    """True when the value (string, or any JSON-serializable object) contains synthetic sensitive data."""
    text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in PATTERNS)
