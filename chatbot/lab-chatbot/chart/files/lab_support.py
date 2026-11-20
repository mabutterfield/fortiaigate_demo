"""Support code for the FortiAIGate 8.0.2 student lab chatbot.

Pure-Python, standard library only, so it can be unit tested without
Streamlit or a cluster:

- identity: verify the gateway's signed X-Lab-* headers and sign fresh ones
  for the gateway's internal APIs. The signing scheme must match
  chatbot/https-gateway/chart/files/lab_auth.py (tests cross-check it).
- Traffic Log: read the signed-in student's (or, for an admin acting as a
  student, that student's) Traffic Log entries through the gateway.
- admin: call the gateway's admin-only internal API and generate passwords.

Change 2026-11-20: the v1 helpers (per-student lab-keys-* SecretStore, key
checks, seed drift/restore, pack-based judge/run_test and the old "deny"
verdict mapping) were removed with chatbot/lab-chatbot/legacy/lab_chatbot_v1.py.
Keys now live behind the gateway broker and tests use catalog802; the 8.0.1
versions are in the archive/8.0.1 branch.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

IDENTITY_FIELDS = ("user", "student", "role", "workspace_id", "ts")
SIGNATURE_MAX_AGE = int(os.environ.get("LAB_SIGNATURE_MAX_AGE", "300"))


# ------------------------------------------------------------------ identity

def load_signing_key(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read().strip()


def sign_identity(identity: dict[str, Any], key: bytes) -> str:
    message = "|".join(str(identity.get(f, "")) for f in IDENTITY_FIELDS).encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_identity(headers: dict[str, str], key: bytes, now: float | None = None) -> dict[str, str] | None:
    """Identity from lower-cased X-Lab-* headers when the signature is valid and fresh."""
    identity = {f: headers.get("x-lab-" + f.replace("_", "-"), "") for f in IDENTITY_FIELDS}
    signature = headers.get("x-lab-signature", "")
    if not signature or not identity["user"] or not hmac.compare_digest(signature, sign_identity(identity, key)):
        return None
    try:
        age = (now or time.time()) - float(identity["ts"])
    except ValueError:
        return None
    if not 0 <= age <= SIGNATURE_MAX_AGE or identity["role"] not in ("student", "admin"):
        return None
    return identity


def identity_headers(identity: dict[str, str], key: bytes, now: float | None = None) -> dict[str, str]:
    """Freshly signed headers (the chatbot holds the key, so it can re-sign for internal calls)."""
    fresh = {**{f: identity.get(f, "") for f in IDENTITY_FIELDS}, "ts": str(int(now or time.time()))}
    headers = {"X-Lab-" + "-".join(p.capitalize() for p in f.split("_")): fresh[f] for f in IDENTITY_FIELDS}
    headers["X-Lab-Signature"] = sign_identity(fresh, key)
    return headers



def mask(secret: str) -> str:
    return ("..." + secret[-4:]) if secret and len(secret) > 8 else "(not set)"


# ------------------------------------------------------------------ traffic log

def internal_logs(auth_url: str, identity: dict[str, str], key: bytes, *,
                  key_alias: str = "", since_ms: int = 0, uuid: str = "", limit: int = 50,
                  student: str = "") -> tuple[int, Any]:
    """Call the gateway's internal Traffic Log API with freshly signed identity headers.

    Students read their own workspace; an admin passes student= (Act as student, Change 2026-11-20)."""
    query = {"uuid": uuid} if uuid else {"key": key_alias, "since": str(since_ms), "limit": str(limit)}
    if student:
        query["student"] = student
    request = urllib.request.Request(auth_url.rstrip("/") + "/_lab/internal/traffic-logs?" + urllib.parse.urlencode(query),
                                     headers=identity_headers(identity, key))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, {"error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": str(exc)}


# ------------------------------------------------------------------ admin

PASSWORD_SPECIALS = "_"  # FAIG accepts underscore; common word selection includes it.


def generate_password(length: int = 16) -> str:
    """Random password with upper, lower, digit and special characters (FAIG's strength rules)."""
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, PASSWORD_SPECIALS]
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice("".join(pools)) for _ in range(max(length, 12) - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def admin_call(auth_url: str, identity: dict[str, str], key: bytes, method: str, path: str,
               body: dict[str, Any] | None = None) -> tuple[int, Any]:
    """Call an admin-only internal endpoint of the sign-in service with freshly signed headers."""
    headers = identity_headers(identity, key)
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(auth_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, {"error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": str(exc)}
