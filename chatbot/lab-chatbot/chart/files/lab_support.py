"""Support code for the FortiAIGate 8.0.2 student lab chatbot.

Pure-Python, standard library only, so it can be unit tested without
Streamlit or a cluster:

- identity: verify the gateway's signed X-Lab-* headers and sign fresh ones
  for the gateway's internal Traffic Log API. The signing scheme must match
  chatbot/https-gateway/chart/files/lab_auth.py (tests cross-check it).
- key store: each student's scenario keys live in one Kubernetes Secret
  (`<prefix><student>`, data key `keys.json`) that Ansible seeds and the
  chatbot may update. Edits never write back to the instructor's files.
- key checks: GET <gateway>/models with a key proves FortiAIGate accepts it
  (and shows which models it reaches) without sending a chat request.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

IDENTITY_FIELDS = ("user", "student", "role", "workspace_id", "ts")
SIGNATURE_MAX_AGE = int(os.environ.get("LAB_SIGNATURE_MAX_AGE", "300"))
SECRET_DATA_KEY = "keys.json"


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


# ------------------------------------------------------------------ keys

def mask(secret: str) -> str:
    return ("..." + secret[-4:]) if secret and len(secret) > 8 else "(not set)"


def key_for(keys: list[dict[str, Any]], scenario: str, action: str) -> dict[str, Any] | None:
    return next((k for k in keys if k.get("scenario") == scenario and k.get("action") == action), None)


def available(keys: list[dict[str, Any]], pack: dict[str, Any]) -> dict[str, list[str]]:
    """Scenario -> actions the student has a key for and the pack describes."""
    out: dict[str, list[str]] = {}
    for scenario, entry in pack.get("scenarios", {}).items():
        actions = [a for a in entry.get("actions", {}) if key_for(keys, scenario, a)]
        if actions:
            out[scenario] = actions
    return out


def public_keys(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Display rows without secrets."""
    return [{"key": k.get("keyName", ""), "scenario": k.get("scenario", ""), "action": k.get("action", ""),
             "model": k.get("model", ""), "secret": mask(k.get("secretKey", "")),
             "updated": k.get("updatedAt", "seeded")} for k in keys]


def replace_secret(keys: list[dict[str, Any]], key_name: str, secret: str, by: str,
                   now: float | None = None) -> list[dict[str, Any]]:
    secret = secret.strip()
    if not secret or any(c.isspace() for c in secret):
        raise ValueError("The key is empty or contains spaces.")
    if not any(k.get("keyName") == key_name for k in keys):
        raise KeyError(key_name)
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now or time.time()))
    return [({**k, "secretKey": secret, "updatedAt": stamp, "updatedBy": by} if k.get("keyName") == key_name else k)
            for k in keys]


def check_key(base_url: str, secret: str, model: str = "", timeout: int = 20) -> tuple[bool, str]:
    """(ok, message) from GET <base_url>/models with the key."""
    request = urllib.request.Request(base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {secret}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            models = [m.get("id") for m in json.loads(response.read()).get("data", [])]
    except urllib.error.HTTPError as exc:
        return False, f"FortiAIGate rejected the key (HTTP {exc.code})."
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return False, f"Could not reach FortiAIGate: {exc}"
    if model and model not in models:
        return False, f"Key accepted, but it does not reach model {model} (reaches: {', '.join(models) or 'none'})."
    return True, f"Key accepted; reaches {', '.join(models) or 'no models'}."


class SecretStore:
    """Read and update per-student key Secrets with the pod's service account."""

    TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    def __init__(self, namespace: str, prefix: str, api: str = "https://kubernetes.default.svc"):
        self.namespace, self.prefix, self.api = namespace, prefix, api.rstrip("/")

    def name(self, student: str) -> str:
        return self.prefix + student

    def _call(self, method: str, path: str, body: Any = None, content_type: str = "application/json") -> Any:
        with open(self.TOKEN, encoding="utf-8") as handle:
            token = handle.read().strip()
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.api + path, data=data, method=method,
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": content_type})
        context = ssl.create_default_context(cafile=self.CA)
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            return json.loads(response.read())

    def _path(self, student: str) -> str:
        return f"/api/v1/namespaces/{urllib.parse.quote(self.namespace)}/secrets/{urllib.parse.quote(self.name(student))}"

    def load(self, student: str) -> list[dict[str, Any]]:
        try:
            secret = self._call("GET", self._path(student))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                return []
            raise
        raw = (secret.get("data") or {}).get(SECRET_DATA_KEY, "")
        return json.loads(base64.b64decode(raw)) if raw else []

    def save(self, student: str, keys: list[dict[str, Any]]) -> None:
        encoded = base64.b64encode(json.dumps(keys, indent=1).encode()).decode()
        self._call("PATCH", self._path(student), {"data": {SECRET_DATA_KEY: encoded}},
                   content_type="application/merge-patch+json")


def internal_logs(auth_url: str, identity: dict[str, str], key: bytes, *, student: str = "",
                  key_alias: str = "", since_ms: int = 0, uuid: str = "", limit: int = 50) -> tuple[int, Any]:
    """Call the gateway's internal Traffic Log API with freshly signed identity headers."""
    query = {"uuid": uuid} if uuid else {"key": key_alias, "since": str(since_ms), "limit": str(limit)}
    if student and identity.get("role") == "admin":
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
