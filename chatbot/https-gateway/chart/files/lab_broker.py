"""Lab broker helpers for lab_auth: caller tokens, session handles and FAIG allowlists.

Authority model (Milestone 2 interfaces, section 10):
- Each in-cluster caller (e.g. lab-management) has its own bearer token, read
  from LAB_CALLER_TOKEN_DIR/<caller>. A token grants one scope.
- The user being served is identified by an opaque per-sign-in session handle
  (X-Lab-Session) that lab_auth issues and nginx forwards. lab_auth resolves it
  to the live in-memory session; signed X-Lab-* headers are display data only.
- Calls to FAIG are limited to exact (METHOD, anchored path regex) entries.

Standard library only.
"""
from __future__ import annotations

import hmac
import os
import re
import urllib.parse
from pathlib import Path

CALLER_TOKEN_DIR = os.environ.get("LAB_CALLER_TOKEN_DIR", "/etc/lab-auth/callers")
# Caller name -> scope. Only listed callers are accepted, whatever files exist.
CALLER_SCOPES = {"lab-management": "admin"}
MAX_PROXY_BODY = 256 * 1024

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_PROVIDER = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"

# (method, path regex without query, allowed query parameter names)
ADMIN_ALLOW = (
    ("GET", rf"/api/v1/admin/ai-providers", set()),
    ("GET", rf"/api/v1/admin/ai-providers/{_PROVIDER}", set()),
    ("PUT", rf"/api/v1/admin/ai-providers/{_PROVIDER}", set()),
    ("GET", r"/api/v1/admin/users", {"offset", "limit"}),
    ("GET", r"/api/v1/admin/review-queue", set()),
    ("GET", r"/api/v1/admin/dlp-labels", set()),
)


def load_caller_tokens(directory: str = None) -> dict:
    """{token: caller} for known callers whose token file exists and is non-empty."""
    tokens = {}
    base = Path(directory or CALLER_TOKEN_DIR)
    for caller in CALLER_SCOPES:
        try:
            value = (base / caller).read_text().strip()
        except OSError:
            continue
        if len(value) >= 32:
            tokens[value] = caller
    return tokens


def caller_for(authorization: str, tokens: dict) -> str | None:
    """Return the caller name for 'Bearer <token>' using constant-time comparison."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    presented = authorization[len("Bearer "):].strip()
    found = None
    for token, caller in tokens.items():
        if hmac.compare_digest(token.encode(), presented.encode()):
            found = caller
    return found


def normalize(path: str) -> tuple[str, dict] | None:
    """Split and check a FAIG API path; None when it is unsafe or malformed."""
    if not isinstance(path, str) or not path.startswith("/api/v1/") or len(path) > 512:
        return None
    lowered = path.lower()
    if "#" in path or "\\" in path or "//" in path or "%2f" in lowered or "%2e" in lowered or "%5c" in lowered:
        return None
    url = urllib.parse.urlsplit(path)
    if url.scheme or url.netloc:
        return None
    segments = url.path.split("/")
    if any(s in (".", "..") for s in segments):
        return None
    query = urllib.parse.parse_qs(url.query, keep_blank_values=True, strict_parsing=False)
    if any(len(v) != 1 for v in query.values()):
        return None
    return url.path, {k: v[0] for k, v in query.items()}


def allowed(method: str, path: str, allowlist=ADMIN_ALLOW) -> bool:
    checked = normalize(path)
    if not checked or method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return False
    bare, query = checked
    for allowed_method, pattern, params in allowlist:
        if method == allowed_method and re.fullmatch(pattern, bare):
            return set(query) <= params and all(re.fullmatch(r"[0-9]{1,6}", v) for v in query.values())
    return False
