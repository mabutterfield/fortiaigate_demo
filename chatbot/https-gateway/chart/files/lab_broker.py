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
    return response.get("items", response) if isinstance(response, dict) else response


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
