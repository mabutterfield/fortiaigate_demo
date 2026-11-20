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
- admin: list students and reset passwords through the gateway's admin-only
  internal API, generate strong passwords, and compare or restore a student's
  keys against the instructor's seed (`<seed prefix><student>`, read-only).
- scenario tests: run one scenario action's validation case, judge it with the
  shared result contract (functional_test/result_contract.py, the same rules
  as `functional_test baseline`), and match the turn's Traffic Log entries.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import string
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

try:  # in the pod, Ansible copies result_contract.py next to this file
    import result_contract
except ImportError:  # repository checkout (unit tests)
    from functional_test import result_contract

IDENTITY_FIELDS = ("user", "student", "role", "workspace_id", "ts")
SIGNATURE_MAX_AGE = int(os.environ.get("LAB_SIGNATURE_MAX_AGE", "300"))
SECRET_DATA_KEY = "keys.json"
EXPECTED_LOG_VERDICT = {"alert": "Alert", "deny": "Block", "redact": "Redact", "passthrough": "Log"}
VERDICT_SEVERITY = {"Log": 0, "Alert": 1, "Redact": 2, "Block": 3}
LOG_SUMMARY_FIELDS = ("verdictLabel", "action", "guardType", "httpStatus", "model", "prompt", "response",
                      "toolCalls", "tokens", "cost", "latency", "uuid")


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

    def __init__(self, namespace: str, prefix: str, api: str = "https://kubernetes.default.svc",
                 seed_prefix: str = "lab-seed-"):
        self.namespace, self.prefix, self.api, self.seed_prefix = namespace, prefix, api.rstrip("/"), seed_prefix

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

    def _path(self, student: str, seed: bool = False) -> str:
        name = (self.seed_prefix if seed else self.prefix) + student
        return f"/api/v1/namespaces/{urllib.parse.quote(self.namespace)}/secrets/{urllib.parse.quote(name)}"

    def load_seed(self, student: str) -> list[dict[str, Any]]:
        """The instructor's seeded keys (rewritten by every deploy; the app can only read them)."""
        return self.load(student, seed=True)

    def load(self, student: str, seed: bool = False) -> list[dict[str, Any]]:
        try:
            secret = self._call("GET", self._path(student, seed))
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


# ------------------------------------------------------------------ scenario tests

def log_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """The Traffic Log fields worth showing next to the payloads (drops tool definitions etc.)."""
    return {f: entry.get(f) for f in LOG_SUMMARY_FIELDS if f in entry}


def judge(scenario: str, action: str, test: dict[str, Any], raw: dict[str, Any],
          verdicts: list[str] | None) -> tuple[bool, list[str], dict[str, Any]]:
    """Same pass/fail rules as functional_test baseline; verdicts=None skips the Traffic Log check."""
    normalized = result_contract.normalized_live_result(raw)
    item = {"scenario": scenario, "required_tools": test.get("required_tools", []),
            "forbidden_tools": test.get("forbidden_tools", [])}
    expected = test.get("expected_result", "completed")
    ok = result_contract.result_matches_expected(expected, item, normalized)
    details = [] if ok else result_contract.expectation_failure_details(expected, item, normalized)
    if raw.get("error"):
        details.insert(0, f"{raw['error']}: {str(raw.get('detail'))[:300]}")
    if verdicts is not None:
        wanted = test.get("expected_log_verdict") or EXPECTED_LOG_VERDICT.get(action, "")
        observed = max(verdicts, key=lambda v: VERDICT_SEVERITY.get(v, -1)) if verdicts else None
        if wanted and observed != wanted:
            ok = False
            details.append(f"Traffic Log verdict {observed or 'missing'} (entries: {', '.join(verdicts) or 'none'}); "
                           f"expected {wanted}")
    return ok, details, normalized


def run_test(agent: Callable[[dict[str, Any]], dict[str, Any]], fetch_logs: Callable[..., tuple[int, Any]], *,
             scenario: str, action: str, spec: dict[str, Any], key: dict[str, Any], faig_url: str, mcp_url: str,
             max_tokens: int = 2048, temperature: float = 0.0, with_details: bool = True,
             polls: int = 6, delay: float = 2.0, sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """Run one scenario action's validation case with the student's key and collect its Traffic Log entries.

    Entries are matched by key alias and start time, so another chat on the
    same key during the test can add rows. The key value is never returned.
    """
    test = spec["test"]
    since = int(clock() * 1000) - 2000
    raw = agent({"base_url": faig_url, "api_key": key.get("secretKey", ""), "model": spec["model"],
                 "prompt": test["prompt"], "system_prompt": spec.get("system_prompt", ""), "mcp_url": mcp_url,
                 "tools": spec.get("tools", []), "max_rounds": spec.get("max_rounds", 3), "max_tokens": max_tokens,
                 "temperature": temperature, "record_exchanges": True})
    wanted_rows = max(1, len(raw.get("exchanges") or []))
    rows: list[dict[str, Any]] = []
    log_error = None
    for _ in range(max(1, polls)):
        sleep(delay)
        status, data = fetch_logs(key_alias=key.get("keyName", ""), since_ms=since)
        if status != 200:
            log_error = (data or {}).get("error") or f"HTTP {status}"
            break
        rows = sorted(data.get("items", []), key=lambda r: r.get("timeStamp", 0))
        if len(rows) >= wanted_rows:
            break
    entries = []
    if with_details and log_error is None:
        for row in rows:
            status, detail = fetch_logs(uuid=row.get("uuid", ""))
            entries.append(log_summary(detail if status == 200 else row))
    verdicts = None if log_error else [r.get("verdictLabel") for r in rows]
    ok, details, normalized = judge(scenario, action, test, raw, verdicts)
    if log_error:
        details.append(f"Traffic Log not checked: {log_error}")
    return {"scenario": scenario, "action": action, "key_name": key.get("keyName", ""), "test": test, "passed": ok,
            "details": details, "normalized": normalized, "verdicts": verdicts, "log_error": log_error,
            "exchanges": raw.get("exchanges", []), "log_entries": entries, "reply": raw.get("reply", ""),
            "tool_events": raw.get("tool_events", [])}


# ------------------------------------------------------------------ admin

PASSWORD_SPECIALS = "_"  # FAIG accepts underscore; common word selection includes it.


def generate_password(length: int = 16) -> str:
    """Random password with upper, lower, digit and special characters (FAIG's strength rules)."""
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, PASSWORD_SPECIALS]
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice("".join(pools)) for _ in range(max(length, 12) - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def key_drift(current: list[dict[str, Any]], seed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per key: does the student's stored key still match the instructor's seed? (No secrets returned.)"""
    now = {k.get("keyName"): k for k in current}
    seeded = {k.get("keyName"): k for k in seed}
    rows = []
    for name in sorted(set(now) | set(seeded)):
        mine, original = now.get(name), seeded.get(name)
        if mine and original:
            status = "matches seed" if mine.get("secretKey") == original.get("secretKey") else "changed"
        else:
            status = "missing (seed only)" if original else "not in seed"
        source = mine or original
        rows.append({"key": name, "scenario": source.get("scenario", ""), "action": source.get("action", ""),
                     "status": status, "changed by": (mine or {}).get("updatedBy", ""),
                     "changed at": (mine or {}).get("updatedAt", "")})
    return rows


def restore_keys(current: list[dict[str, Any]], seed: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    """Put the seeded value back for the named keys (re-adding seed-only keys); others are untouched."""
    seeded = {k.get("keyName"): k for k in seed}
    unknown = [n for n in names if n not in seeded]
    if unknown:
        raise KeyError(", ".join(unknown))
    restored = [dict(seeded[k["keyName"]]) if k.get("keyName") in names else k for k in current]
    present = {k.get("keyName") for k in current}
    restored += [dict(seeded[n]) for n in names if n not in present]
    return restored


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
