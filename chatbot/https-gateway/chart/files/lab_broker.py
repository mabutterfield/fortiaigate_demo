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
CALLER_SCOPES = {"lab-management": "admin", "lab-chatbot": "student"}
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


# ---------------------------------------------------------------- students (Change 2026-11-19)
#
# Student accounts are created by lab_auth with the instructor's FAIG session.
# Passwords never leave lab_auth except in the instructor share view. They are
# written to the lab-credentials Secret (write-ahead, status "pending") before
# FAIG is asked to create the account, so a crash cannot lose a password that
# FAIG accepted.

import secrets as _secrets
import string as _string
import time as _time
import urllib.error as _urlerror

STUDENT_DOMAIN = os.environ.get("LAB_STUDENT_DOMAIN", "fortiai.lab")
SCENARIO_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
PASSWORD_MODES = ("generated", "shared", "base")


def student_names(number: int, domain: str = None) -> dict:
    if type(number) is not int or not 1 <= number <= 99:
        raise ValueError("student number must be 1-99")
    student = f"student{number:02d}"
    return {"number": number, "student": student, "email": f"{student}@{domain or STUDENT_DOMAIN}",
            "workspace": f"{student}_workspace"}


def generate_password() -> str:
    """24 characters with every FAIG class; '_' is the special character (copy-friendly)."""
    pools = (_string.ascii_uppercase, _string.ascii_lowercase, _string.digits, "_")
    chars = [_secrets.choice(pool) for pool in pools]
    chars += [_secrets.choice("".join(pools)) for _ in range(20)]
    _secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def student_password(policy: dict, number: int) -> str:
    """Final password for one student; supplied values are never altered beyond the agreed suffix."""
    mode = (policy or {}).get("mode")
    if mode == "generated":
        return generate_password()
    value = (policy or {}).get("value")
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n") or len(value) > 128:
        raise ValueError("a non-empty single-line password is required for this mode")
    if mode == "shared":
        return value
    if mode == "base":
        return f"{value}{number:02d}"
    raise ValueError("password mode must be generated, shared or base")


def provider_access(providers: list) -> tuple[list, list, list]:
    """Workspace access, default key bindings and project access for whole providers (no secrets)."""
    access, bindings, project_access = [], [], []
    for p in providers:
        keys = p.get("apiKeys", [])
        if not keys or any(not k.get("id") for k in keys):
            raise ValueError("provider has no saved credential: " + str(p.get("providerId")))
        common = {"providerId": p["providerId"], "platform": p["platform"], "name": p["name"],
                  "allModels": True, "models": [], "blockedModelUuids": []}
        project_access.append(dict(common))
        access.append({**common, "allKeys": True, "keys": [], "excludedKeyIds": []})
        bindings.append({"providerId": p["providerId"], "keyIds": [k["id"] for k in keys]})
    return access, bindings, project_access


def _items(response):
    """List payload of a FAIG response: a bare list, or {"items"|"providers"|"data": [...]}."""
    if isinstance(response, dict):
        for key in ("items", "providers", "data"):
            if isinstance(response.get(key), list):
                return response[key]
        return []
    return response if isinstance(response, list) else []


def _all_users(admin) -> list:
    users = []
    while True:
        page = admin.call("GET", f"/api/v1/admin/users?offset={len(users)}&limit=100")
        batch = _items(page)
        users += batch
        if not batch or len(users) >= int(page.get("total", len(users)) if isinstance(page, dict) else len(users)):
            return users


def _accept_invitation(new_session, invitation_id: str, email: str, number: int, password: str):
    path = "/api/v1/invitations/" + urllib.parse.quote(invitation_id, safe="")
    new_session.call("GET", path)
    identity = new_session.call("POST", path + "/identify", {"email": email})
    if identity.get("outcome") != "needs-registration":
        raise RuntimeError("invitation is not awaiting registration")
    result = new_session.call("POST", path + "/accept",
                              {"email": email, "displayName": f"Student {number:02d}", "password": password})
    if result.get("createdAccount") is not True:
        raise RuntimeError("FAIG did not report a new account")


def ensure_student(admin, new_session, store, request: dict, actor: str, same_as_instructor=lambda pw: False) -> dict:
    """Create or reconcile one student: account, password, workspace, projects, roster.

    admin        FAIG session of the instructor (org admin)
    new_session  factory for a fresh, cookie-less FAIG session (invitation / student login)
    store        lab-data store with get/put(kind, student[, value]) for "credentials" and "roster"
    request      {"number", "password": {"mode", "value"?}, "providers": [ids], "projects": [scenario ids]}
    """
    names = student_names(request.get("number"))
    projects = request.get("projects") or []
    if not isinstance(projects, list) or any(not isinstance(p, str) or not SCENARIO_ID.fullmatch(p) for p in projects):
        raise ValueError("invalid project list")
    provider_ids = request.get("providers") or []
    if not isinstance(provider_ids, list) or not provider_ids or any(not re.fullmatch(_PROVIDER, str(p)) for p in provider_ids):
        raise ValueError("invalid provider list")
    student, email = names["student"], names["email"]
    out = {"student": student, "email": email, "account": "", "password": "", "workspace": "", "projects": {},
           "verified": False, "notes": []}

    users = {u.get("email"): u for u in _all_users(admin)}
    stored = store.get("credentials", student) or {}
    user = users.get(email)
    if user is None:
        if stored.get("status") == "pending":
            password = stored["password"]  # an earlier attempt may or may not have reached FAIG
        else:
            password = student_password(request.get("password"), names["number"])
            strength = admin.call("POST", "/api/v1/me/password/strength", {"password": password})
            if not strength.get("isStrong"):
                missing = [k for k, v in strength.items() if k.endswith("Ok") and v is False]
                raise ValueError("FAIG rejects this password as weak: " + ", ".join(missing))
            if same_as_instructor(password):
                raise ValueError("student passwords must differ from the instructor's password")
        store.put("credentials", student, {"username": email, "password": password, "status": "pending",
                                           "updated_at": int(_time.time())})
        invitation = admin.call("POST", "/api/v1/admin/user-invitations", {"orgRole": "org_member", "emails": [email]})
        invitation_id = invitation.get("id") or (_items(invitation) or [{}])[0].get("id")
        try:
            _accept_invitation(new_session(), invitation_id, email, names["number"], password)
        except (_urlerror.URLError, OSError, RuntimeError):
            out["notes"].append("invitation acceptance did not confirm; checking FAIG")
        users = {u.get("email"): u for u in _all_users(admin)}
        user = users.get(email)
        if user is None:
            raise RuntimeError(f"{email} was not created; the stored pending password will be reused on retry")
        store.put("credentials", student, {"username": email, "password": password, "status": "active",
                                           "updated_at": int(_time.time())})
        out["account"], out["password"] = "created", "stored"
    else:
        out["account"] = "exists"
        if stored.get("password") and stored.get("status") in ("active", "pending"):
            out["password"] = "stored"
            if stored.get("status") == "pending":
                store.put("credentials", student, dict(stored, status="active", updated_at=int(_time.time())))
        else:
            out["password"] = "unknown"
            out["notes"].append("existing account without a stored password; use Reset password to manage it")

    # Workspace (instructor creates it; the student is its admin).
    workspaces = {w.get("workspaceName"): w for w in _items(admin.call("GET", "/api/v1/admin/workspaces"))}
    providers = [admin.call("GET", "/api/v1/admin/ai-providers/" + urllib.parse.quote(p, safe="")) for p in provider_ids]
    access, bindings, project_access = provider_access(providers)
    workspace = workspaces.get(names["workspace"])
    if workspace is None:
        workspace = admin.call("POST", "/api/v1/admin/workspaces", {
            "workspaceName": names["workspace"], "admins": [{"id": user["id"]}],
            "description": "Student lab workspace", "budget": None, "budgetCycle": "monthly", "policyIds": [],
            "providerAccess": access, "modelGroups": [], "defaultKeyBindings": bindings})
        out["workspace"] = "created"
    else:
        out["workspace"] = "exists"
    workspace_id = workspace.get("id") or workspace.get("workspaceId")
    out["workspace_id"], out["workspace_name"] = workspace_id, names["workspace"]

    existing_projects = {p.get("name") for p in _items(admin.call("GET", "/api/v1/admin/projects"))
                         if p.get("workspaceId") == workspace_id}
    for scenario in projects:
        name = f"{student}_{scenario}"
        if name in existing_projects:
            out["projects"][name] = "exists"
            continue
        admin.call("POST", "/api/v1/admin/projects", {
            "name": name, "description": "Student scenario project", "workspaceId": workspace_id,
            "providerAccess": project_access, "modelGroups": [], "budget": None, "policyIds": []})
        out["projects"][name] = "created"

    # Verify with the student's own session when the password is known.
    credentials = store.get("credentials", student) or {}
    if credentials.get("password"):
        check = new_session()
        check.login(email, credentials["password"])
        memberships = _items(check.call("GET", "/api/v1/me/workspaces"))
        out["verified"] = any(w.get("id") == workspace_id and w.get("membershipRole") == "admin" for w in memberships)
        if not out["verified"]:
            out["notes"].append("student login did not show admin membership of the workspace")

    roster = store.get("roster", student) or {}
    store.put("roster", student, {
        "number": names["number"], "display_name": roster.get("display_name", ""), "username": email,
        "faig_user_id": user.get("id", ""), "workspace": names["workspace"], "workspace_id": workspace_id,
        "created_at": roster.get("created_at") or int(_time.time()),
        "created_by": roster.get("created_by") or actor, "updated_at": int(_time.time())})
    return out


def roster_rows(roster: dict, credentials: dict, faig_rows: list, reveal: bool) -> list:
    """Instructor roster: lab-roster entries merged with FAIG's student list."""
    faig = {r["student"]: r for r in faig_rows}
    rows = []
    for student in sorted(set(roster) | set(faig)):
        entry, live = roster.get(student, {}), faig.get(student, {})
        row = {"student": student, "number": entry.get("number") or int(student[len("student"):] or 0),
               "display_name": entry.get("display_name", ""), "username": entry.get("username") or live.get("email", ""),
               "workspace": entry.get("workspace") or live.get("workspace", ""), "in_faig": bool(live),
               "active": live.get("active", False), "keys": live.get("keys", 0),
               "password_stored": bool((credentials.get(student) or {}).get("password"))}
        if reveal:
            row["password"] = (credentials.get(student) or {}).get("password", "")
        rows.append(row)
    return rows


DISPLAY_NAME = re.compile(r"[^\x00-\x1f<>]{0,80}")


# ---------------------------------------------------------------- prepopulation (Change 2026-11-19)
#
# Creates one student's detectors, guardrails, policies and keys from the
# catalog plan, acting AS THE STUDENT (workspace objects must be created by a
# workspace admin) and approving each layer with the instructor's session.
# Ported from experiments/faig-api-lab/scenario_lab.py (Prepopulate).
# New key secrets are written to the lab-keys Secret as soon as FAIG returns
# them; FAIG shows a secret only once.

OBJECT_NAME = re.compile(r"student\d{2}[_-][a-z0-9][a-z0-9_-]{0,120}")
APPROVE = {"detector": "/api/v1/admin/detectors/{}/approve",
           "guardrail": "/api/v1/admin/guardrails/{}/approve",
           "policy": "/api/v1/admin/policies/{}/approve"}
LAYER_PATH = {"detector": "/detectors", "guardrail": "/guardrails", "policy": "/policies"}


def _rid():
    return "policy-" + _secrets.token_hex(5)


def ai_copy_body(builtin: dict, name: str, description: str, action: str) -> dict:
    """Copy a built-in AI detector's rules, as the GUI's duplicate flow does."""
    ai_rules, flat = [], []
    for rule in builtin["rules"]:
        conditions = [{"id": _rid(), "description": text} for text in rule.get("violateIf", [])]
        flat.extend({"id": _rid(), "description": c["description"]} for c in conditions)
        ai_rules.append({"id": _rid(), "name": rule["name"], "description": rule.get("description", ""),
                         "enabled": rule.get("enabled", True), "violateIf": list(rule.get("violateIf", [])),
                         "exemptIf": list(rule.get("exemptIf", [])), "conditions": conditions})
    return {"name": name, "description": description, "inputGuards": ["AI descriptions"],
            "outputGuards": ["AI descriptions"], "sensitivity": None, "detectorType": "ai",
            "managedEngine": None, "action": action, "regexRules": None, "aiRules": ai_rules, "rules": flat}


def dlp_body(name: str, description: str, disposition: str, categories: list) -> dict:
    rules = []
    for number, category in enumerate(categories, 1):
        rule = {"id": f"r{number}", "disposition": disposition, "category": category, "threshold": 0.7}
        if disposition == "redact":
            rule["replacement"] = "[REDACTED_" + re.sub(r"[^A-Z0-9]+", "_", category.upper()).strip("_") + "]"
        rules.append(rule)
    return {"name": name, "description": description, "inputGuards": list(categories),
            "outputGuards": list(categories), "sensitivity": None, "detectorType": "managed",
            "managedEngine": "dlp", "action": None, "rules": rules, "regexRules": None, "aiRules": None}


def _model_access(provider: dict, model: dict, with_keys: bool) -> dict:
    access = {"providerId": provider["providerId"], "platform": provider["platform"], "name": provider["name"],
              "allModels": False, "blockedModelUuids": [],
              "models": [{"uuid": model["uuid"], "modelId": model["modelId"],
                          "publicName": model.get("publicName", model["modelId"]), "enabled": True}]}
    if with_keys:
        access.update({"allKeys": True, "keys": [], "excludedKeyIds": []})
    return access


def _key_body(name, workspace_id, project_id, policy_id, provider, model):
    return {"keyName": name, "keyType": "user", "scope": "workspace", "workspaceId": workspace_id,
            "projectId": project_id, "policyIds": [policy_id] if policy_id else [],
            "providerAccess": [_model_access(provider, model, True)], "modelGroups": [],
            "budgetWindows": {"hourly": None, "daily": None, "weekly": None, "monthly": None},
            "tpm": None, "rpm": None, "expiresAt": None}


def _oid(obj):
    return obj.get("uuid") or obj.get("id")


def _status(obj):
    status = obj.get("status") or obj.get("approvalStatus")
    return "active" if status == "approved" else status


def validate_plan(student: str, plan: dict) -> None:
    """Reject anything outside the expected shape before touching FAIG."""
    if not isinstance(plan, dict) or set(plan) - {"entries", "passthrough"}:
        raise ValueError("bad plan")
    names = []
    for entry in plan.get("entries") or []:
        for field in ("scenario", "action", "model", "provider", "project", "key", "policy", "guardrail", "guard"):
            if field not in entry:
                raise ValueError(f"plan entry missing {field}")
        if not SCENARIO_ID.fullmatch(entry["scenario"]) or entry["action"] not in ("alert", "redact", "block"):
            raise ValueError("bad scenario or action")
        names += [entry["project"], entry["key"], entry["policy"], entry["guardrail"]]
        names += [d["name"] for d in entry["guard"].get("detectors", [])]
        if entry["guard"].get("direction") not in ("input", "output", "both"):
            raise ValueError("bad guard direction")
    passthrough = plan.get("passthrough")
    if passthrough:
        names.append(passthrough["key"])
    for name in names:
        if not OBJECT_NAME.fullmatch(name) or not name.startswith(student):
            raise ValueError(f"object name {name!r} is not a valid name for {student}")


def prepopulate_student(admin, student_session, store, student: str, plan: dict, log) -> dict:
    """Create and approve one student's objects and keys; returns a summary."""
    validate_plan(student, plan)
    workspace = next((w for w in _items(student_session.call("GET", "/api/v1/me/workspaces"))
                      if w.get("workspaceName") == f"{student}_workspace"), None)
    if not workspace:
        raise RuntimeError(f"{student} is not a member of {student}_workspace")
    base = f"/api/v1/workspaces/{workspace['id']}"
    grantable = {p.get("providerId"): p for p in _items(student_session.call("GET", base + "/grantable-providers"))}

    def model_for(provider_id, model_id):
        provider = grantable.get(provider_id)
        models = {m["modelId"]: m for m in (provider or {}).get("models", [])
                  if m.get("effectiveEnabled", m.get("enabled", True)) is not False}
        return provider, models.get(model_id)

    summary = {"created": [], "existing": [], "approved": [], "skipped": [], "keys_saved": [], "notes": []}
    entries = []
    for entry in plan.get("entries") or []:
        provider, model = model_for(entry["provider"], entry["model"])
        if not model:
            summary["skipped"].append(f"{entry['scenario']}/{entry['action']} (model {entry['model']} not available)")
        else:
            entries.append(dict(entry, _provider=provider, _model=model))

    # Projects (admin-owned).
    projects = {p.get("name"): p for p in _items(admin.call("GET", "/api/v1/admin/projects"))
                if p.get("workspaceId") == workspace["id"]}
    for name in dict.fromkeys(e["project"] for e in entries):
        if name not in projects:
            provider = entries[[e["project"] for e in entries].index(name)]["_provider"]
            projects[name] = admin.call("POST", "/api/v1/admin/projects", {
                "name": name, "description": "Student scenario project", "workspaceId": workspace["id"],
                "providerAccess": [{"providerId": provider["providerId"], "platform": provider["platform"],
                                    "name": provider["name"], "allModels": True, "models": [], "blockedModelUuids": []}],
                "modelGroups": [], "budget": None, "policyIds": []})
            summary["created"].append("project " + name)

    def ensure_layer(kind, specs):
        """specs: [(key, name, body)] -> {key: id}; create/submit as student, approve as instructor."""
        collection = base + LAYER_PATH[kind]
        existing = {o.get("name"): o for o in _items(student_session.call("GET", collection))}
        result, pending = {}, {}
        for key, name, body in specs:
            obj = existing.get(name)
            if obj is None:
                obj = student_session.call("POST", collection, body)
                summary["created"].append(f"{kind} {name}")
            else:
                summary["existing"].append(f"{kind} {name}")
            status = _status(obj)
            if status == "rejected":
                raise RuntimeError(f"{kind} {name} was rejected: {obj.get('rejectionReason')}")
            if status == "draft":
                obj = student_session.call("POST", f"{collection}/{_oid(obj)}/submit")
                status = _status(obj)
            if status == "pending" or obj.get("hasPendingChange"):
                pending[_oid(obj)] = name
            elif status != "active":
                raise RuntimeError(f"{kind} {name} has unexpected status {status}")
            result[key] = _oid(obj)
        if pending:
            queue = {i.get("id") for i in _items(admin.call("GET", "/api/v1/admin/review-queue")) if i.get("type") == kind}
            for oid, name in pending.items():
                if oid not in queue:
                    raise RuntimeError(f"{kind} {name} is pending but not in the review queue")
                admin.call("POST", APPROVE[kind].format(oid))
                summary["approved"].append(f"{kind} {name}")
        return result

    # Detectors (deduplicated by name across entries).
    builtins, detector_specs = None, {}
    for entry in entries:
        for det in entry["guard"].get("detectors", []):
            if det["name"] in detector_specs:
                continue
            if det["kind"] == "ai_copy":
                if builtins is None:
                    builtins = {b["id"]: b for b in _items(student_session.call("GET", base + "/built-in-detectors"))}
                if det["source"] not in builtins:
                    raise RuntimeError("built-in detector not found: " + det["source"])
                body = ai_copy_body(builtins[det["source"]], det["name"], det.get("description", ""), det["action"])
            elif det["kind"] == "dlp":
                body = dlp_body(det["name"], det.get("description", ""), det["disposition"], det["categories"])
            else:
                raise ValueError("unsupported detector kind: " + str(det["kind"]))
            detector_specs[det["name"]] = (det["name"], det["name"], body)
    detectors = ensure_layer("detector", list(detector_specs.values())) if detector_specs else {}

    guardrails = ensure_layer("guardrail", [
        (e["guardrail"], e["guardrail"], {
            "name": e["guardrail"], "description": f"{e['scenario']} {e['action']}",
            "detectorIds": [detectors[d["name"]] for d in e["guard"].get("detectors", [])]
                           + list(e["guard"].get("builtin_detectors", [])),
            "denySuspiciousCharacters": bool(e["guard"].get("deny_suspicious_characters"))})
        for e in entries]) if entries else {}

    policies = ensure_layer("policy", [
        (e["policy"], e["policy"], {
            "name": e["policy"], "description": f"{e['scenario']} {e['action']}",
            "inputGuardrailIds": [guardrails[e["guardrail"]]] if e["guard"]["direction"] in ("input", "both") else [],
            "outputGuardrailIds": [guardrails[e["guardrail"]]] if e["guard"]["direction"] in ("output", "both") else [],
            "responseScanMode": "post_stream", "providerAccess": [_model_access(e["_provider"], e["_model"], False)]})
        for e in entries]) if entries else {}

    # Keys: one per scenario action, plus the passthrough key (no policy).
    existing_keys = {k.get("keyName"): k for k in _items(student_session.call("GET", "/api/v1/me/virtual-keys"))}
    stored = {k.get("faig_key_id"): k for k in (store.get("keys", student) or {}).get("keys", [])}
    wanted = [(e["key"], e["scenario"], e["action"], e["model"], projects[e["project"]]["id"], policies[e["policy"]],
               e["_provider"], e["_model"]) for e in entries]
    passthrough = plan.get("passthrough")
    if passthrough:
        provider, model = model_for(passthrough["provider"], passthrough["model"])
        if model:
            wanted.append((passthrough["key"], "passthrough", "passthrough", passthrough["model"], None, None,
                           provider, model))
        else:
            summary["skipped"].append(f"passthrough (model {passthrough['model']} not available)")
    for name, scenario, action, model_id, project_id, policy_id, provider, model in wanted:
        current = existing_keys.get(name)
        if current:
            if current.get("id") in stored and stored[current["id"]].get("secret"):
                summary["existing"].append("key " + name)
            else:
                summary["existing"].append("key " + name)
                summary["notes"].append(f"key {name} exists in FAIG without a stored secret; restore (rotate) it to use it")
            continue
        response = student_session.call("POST", "/api/v1/me/virtual-keys",
                                        _key_body(name, workspace["id"], project_id, policy_id, provider, model))
        secret = response.get("secretKey")
        if not secret:
            raise RuntimeError(f"FAIG did not return a secret for {name}")
        record = {"faig_key_id": response.get("id"), "key_name": name, "scenario_id": scenario, "action": action,
                  "origin": "seeded", "secret": secret, "model": model_id,
                  "policy_ids": [policy_id] if policy_id else [], "status": "untested", "verified_at": None,
                  "updated_at": int(_time.time())}
        try:
            keys = (store.get("keys", student) or {}).get("keys", [])
            keys = [k for k in keys if k.get("faig_key_id") != record["faig_key_id"]] + [record]
            store.put("keys", student, {"schema": 1, "keys": keys})
            summary["keys_saved"].append(name)
        except Exception as exc:  # noqa: BLE001 - FAIG shows the secret once; report clearly
            summary["notes"].append(f"key {name} created but its secret could not be saved ({type(exc).__name__}); "
                                    "restore (rotate) it to recover")
        summary["created"].append("key " + name)
        secret = None
    log(summary)
    return summary



# ---------------------------------------------------------------- student keys (Change 2026-11-19)
#
# The chatbot reads and manages a student's own keys through lab_auth. Key
# records live in lab-data/lab-keys (one data key per student):
#   {faig_key_id, key_name, scenario_id, action, origin, secret, model,
#    policy_ids, status, verified_at, updated_at}
# Mapping a key to a scenario/action is the student's choice; FAIG facts
# (name, policies, models) are refreshed from FAIG with the student's session.

KEY_ACTIONS = ("alert", "redact", "block", "passthrough")
KEY_STATUSES = ("untested", "ok", "invalid", "denied", "unavailable", "error", "unmapped", "missing",
                "rotation-pending", "rotation-unsaved", "rotation-unknown")
UUID_RE = re.compile(_UUID)


def public_key(record: dict) -> dict:
    """A key record safe to show in a browser: no secret, only whether one is stored."""
    out = {k: v for k, v in record.items() if k != "secret"}
    out["has_secret"] = bool(record.get("secret"))
    return out


def faig_facts(faig_key: dict) -> dict:
    models = [m.get("modelId") for p in faig_key.get("providerAccess") or [] for m in p.get("models") or []]
    return {"key_name": faig_key.get("keyName", ""), "policy_ids": list(faig_key.get("policyIds") or []),
            "models": models, "faig_status": faig_key.get("status", "")}


def merge_refresh(records: list, faig_keys: list, now: int = None) -> list:
    """Update stored records with FAIG facts; add unknown keys as unmapped; mark vanished ones missing."""
    now = int(_time.time()) if now is None else now
    by_id = {r.get("faig_key_id"): dict(r) for r in records if r.get("faig_key_id")}
    seen = set()
    for key in faig_keys:
        kid = key.get("id")
        if not kid:
            continue
        seen.add(kid)
        facts = faig_facts(key)
        record = by_id.get(kid) or {"faig_key_id": kid, "scenario_id": "", "action": "", "origin": "student",
                                    "secret": "", "status": "unmapped", "verified_at": None}
        record.update(facts)
        record["model"] = facts["models"][0] if len(facts["models"]) == 1 else ""
        if record.get("status") == "missing":
            record["status"] = "untested" if record.get("scenario_id") else "unmapped"
        record["updated_at"] = now
        by_id[kid] = record
    for kid, record in by_id.items():
        if kid not in seen and record.get("status") != "missing":
            record["status"], record["updated_at"] = "missing", now
    return sorted(by_id.values(), key=lambda r: (r.get("key_name") or "", r.get("faig_key_id")))


def mapping_warnings(record: dict, expected_model: str = "") -> list:
    """Warnings for the owner's 1 key -> 1 policy -> 1 model rule (never a silent rejection)."""
    warnings = []
    policies, models = record.get("policy_ids") or [], record.get("models") or []
    if record.get("action") == "passthrough":
        if policies:
            warnings.append("passthrough key has a policy")
    elif len(policies) != 1:
        warnings.append(f"key has {len(policies)} policies; this lab expects exactly 1")
    if len(models) != 1:
        warnings.append(f"key allows {len(models)} models; this lab expects exactly 1")
    elif expected_model and models[0] != expected_model:
        warnings.append(f"key model {models[0]} is not this scenario's model {expected_model}")
    return warnings


def apply_mapping(records: list, faig_key_id: str, scenario_id: str, action: str, secret: str = None,
                  expected_model: str = "", now: int = None) -> tuple[list, dict]:
    """Map one known key to a scenario/action and optionally store its pasted secret."""
    if not UUID_RE.fullmatch(faig_key_id or ""):
        raise ValueError("bad key id")
    if not (scenario_id == "passthrough" or SCENARIO_ID.fullmatch(scenario_id or "")) or action not in KEY_ACTIONS:
        raise ValueError("bad scenario or action")
    if (scenario_id == "passthrough") != (action == "passthrough"):
        raise ValueError("passthrough keys map to scenario 'passthrough' and action 'passthrough'")
    if secret is not None:
        secret = secret.strip()
        if not re.fullmatch(r"faig_[A-Za-z0-9_-]{20,200}", secret):
            raise ValueError("that is not a FAIG key value")
        if faig_key_id.replace("-", "").lower() not in secret.lower():
            raise ValueError("that key value belongs to a different key")
    now = int(_time.time()) if now is None else now
    records = [dict(r) for r in records]
    record = next((r for r in records if r.get("faig_key_id") == faig_key_id), None)
    if record is None:
        raise KeyError("unknown key; refresh first")
    record.update(scenario_id=scenario_id, action=action, updated_at=now)
    if secret:
        record.update(secret=secret, status="untested", verified_at=None)
    elif record.get("status") == "unmapped":
        record["status"] = "untested"
    return records, {"warnings": mapping_warnings(record, expected_model), "key": public_key(record)}
