#!/usr/bin/env python3
"""Lab login gateway auth service (nginx auth_request sidecar).

Students and FAIG super admins sign in with their FortiAIGate account. The
service keeps each student's FAIG session server-side, answers nginx's
auth_request with HMAC-signed identity headers for the upstream app, and lets
an upstream (the student chatbot) read that student's Traffic Log entries
through an internal API without ever seeing the FAIG session.

Standard library only. Sessions live in memory (one replica); a restart signs
everyone out. Fallback mode checks salted PBKDF2 password hashes from a
mounted JSON file instead of FAIG (no Traffic Log access in that mode).

Environment:
  LAB_AUTH_PORT              listen port (default 8090)
  LAB_FAIG_URL               FAIG origin reachable in-cluster (https://...)
  LAB_FAIG_VERIFY_TLS        "true" to verify FAIG's certificate (default false)
  LAB_HTTPS_PORT             public HTTPS port; HTTP logins redirect there
  LAB_MAX_SESSION_HOURS      absolute session lifetime (default 8)
  LAB_IDLE_MINUTES           idle timeout (default 120)
  LAB_SIGNING_KEY_FILE       file with the HMAC key shared with upstreams
  LAB_SIGNATURE_MAX_AGE      seconds a signed identity stays valid (default 300)
  LAB_AUTH_MODE              "faig" (default) or "fallback"
  LAB_FALLBACK_FILE          JSON {username: {salt, hash, iterations, student, role}}
  LAB_STUDENT_PATTERN        workspace regex (default ^(student\\d{2,})_workspace$)
"""
from __future__ import annotations

import hashlib
import hmac
import html
import http.cookiejar
import json
import os
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("LAB_AUTH_PORT", "8090"))
FAIG_URL = os.environ.get("LAB_FAIG_URL", "https://ingress-nginx-controller.ingress-nginx.svc.cluster.local").rstrip("/")
FAIG_VERIFY_TLS = os.environ.get("LAB_FAIG_VERIFY_TLS", "false").lower() in {"1", "true", "yes", "on"}
HTTPS_PORT = os.environ.get("LAB_HTTPS_PORT", "")
MAX_SESSION = float(os.environ.get("LAB_MAX_SESSION_HOURS", "8")) * 3600
IDLE = float(os.environ.get("LAB_IDLE_MINUTES", "120")) * 60
SIGNATURE_MAX_AGE = int(os.environ.get("LAB_SIGNATURE_MAX_AGE", "300"))
MODE = os.environ.get("LAB_AUTH_MODE", "faig")
FALLBACK_FILE = os.environ.get("LAB_FALLBACK_FILE", "")
STUDENT_PATTERN = re.compile(os.environ.get("LAB_STUDENT_PATTERN", r"^(student\d{2,})_workspace$"))
COOKIE = "lab_session"
IDENTITY_FIELDS = ("user", "student", "role", "workspace_id", "ts")


def load_signing_key() -> bytes:
    path = os.environ.get("LAB_SIGNING_KEY_FILE", "")
    if path and os.path.exists(path):
        return open(path, "rb").read().strip()
    return secrets.token_bytes(32)  # tests/standalone only; upstreams cannot verify


SIGNING_KEY = load_signing_key()


# ------------------------------------------------------------------ identity signing

def sign_identity(identity: dict, key: bytes = None) -> str:
    message = "|".join(str(identity.get(f, "")) for f in IDENTITY_FIELDS).encode()
    return hmac.new(key or SIGNING_KEY, message, hashlib.sha256).hexdigest()


def verify_identity(headers: dict, key: bytes = None, now: float = None) -> dict | None:
    """Return the identity from X-Lab-* headers when the signature is valid and fresh."""
    identity = {f: headers.get("x-lab-" + f.replace("_", "-"), "") for f in IDENTITY_FIELDS}
    signature = headers.get("x-lab-signature", "")
    if not signature or not hmac.compare_digest(signature, sign_identity(identity, key)):
        return None
    try:
        age = (now or time.time()) - float(identity["ts"])
    except ValueError:
        return None
    return identity if 0 <= age <= SIGNATURE_MAX_AGE else None


# ------------------------------------------------------------------ FAIG client

class FaigSession:
    """A signed-in FAIG session (cookie jar + CSRF token) kept server-side."""

    def __init__(self, base: str = FAIG_URL, verify: bool = FAIG_VERIFY_TLS):
        self.base = base
        context = ssl.create_default_context() if verify else ssl._create_unverified_context()
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar),
                                                  urllib.request.HTTPSHandler(context=context))
        self.csrf = ""

    def call(self, method: str, path: str, payload=None):
        headers = {"Origin": self.base, "Referer": self.base + "/"}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        with self.opener.open(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def login(self, username: str, password: str) -> dict:
        self.csrf = self.call("POST", "/api/v1/login", {"username": username, "password": password})["csrf_token"]
        return self.call("GET", "/api/v1/user")


def items(response):
    return response.get("items", response) if isinstance(response, dict) else response


def classify_faig_user(user: dict, workspaces: list) -> dict | None:
    """Map a FAIG account to a lab identity: a student workspace admin or a super admin."""
    if user.get("role") == "super_admin":
        return {"user": user.get("email", ""), "student": "", "role": "admin", "workspace_id": "",
                "workspace": ""}
    for workspace in workspaces:
        match = STUDENT_PATTERN.match(workspace.get("workspaceName") or "")
        if match and workspace.get("membershipRole") == "admin":
            return {"user": user.get("email", ""), "student": match.group(1), "role": "student",
                    "workspace_id": workspace.get("id", ""), "workspace": workspace.get("workspaceName", "")}
    return None


# ------------------------------------------------------------------ fallback store

def hash_password(password: str, salt: str, iterations: int = 210000) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations).hex()


def fallback_login(username: str, password: str, path: str = None) -> dict | None:
    path = path or FALLBACK_FILE
    if not path or not os.path.exists(path):
        return None
    entry = json.load(open(path, encoding="utf-8")).get(username)
    if not entry:
        return None
    candidate = hash_password(password, entry["salt"], int(entry.get("iterations", 210000)))
    if not hmac.compare_digest(candidate, entry["hash"]):
        return None
    return {"user": username, "student": entry.get("student", ""), "role": entry.get("role", "student"),
            "workspace_id": entry.get("workspace_id", ""), "workspace": entry.get("workspace", "")}


# ------------------------------------------------------------------ sessions

class Sessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.data: dict[str, dict] = {}

    def create(self, identity: dict, faig: FaigSession | None) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.lock:
            self.data[token] = {"identity": identity, "faig": faig, "created": now, "seen": now}
        return token

    def get(self, token: str, now: float = None) -> dict | None:
        now = now or time.time()
        with self.lock:
            session = self.data.get(token or "")
            if not session:
                return None
            if now - session["created"] > MAX_SESSION or now - session["seen"] > IDLE:
                self.data.pop(token, None)
                return None
            session["seen"] = now
            return session

    def drop(self, token: str):
        with self.lock:
            self.data.pop(token or "", None)

    def latest_for(self, user: str) -> dict | None:
        with self.lock:
            live = [s for s in self.data.values() if s["identity"]["user"] == user and s["faig"]]
        return max(live, key=lambda s: s["seen"]) if live else None


SESSIONS = Sessions()


# ------------------------------------------------------------------ HTTP

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font-family:system-ui,sans-serif;background:#f4f5f7;color:#1d2330;margin:0}}
main{{max-width:520px;margin:8vh auto;background:#fff;border-radius:10px;padding:28px 32px;box-shadow:0 2px 12px #0001}}
h1{{font-size:1.3rem;margin:0 0 12px}} label{{display:block;margin:12px 0 4px;font-weight:600}}
input{{width:100%;box-sizing:border-box;padding:9px;border:1px solid #c8ccd4;border-radius:6px}}
button{{margin-top:18px;padding:9px 18px;border:0;border-radius:6px;background:#c8102e;color:#fff;font-weight:600;cursor:pointer}}
.err{{color:#b00020}} .muted{{color:#5c6475;font-size:.9rem}} table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;padding:4px 6px;border-bottom:1px solid #eee;font-size:.9rem}}
@media (prefers-color-scheme:dark){{body{{background:#14171c;color:#e4e7ec}}main{{background:#1d2128}}input{{background:#14171c;color:#e4e7ec;border-color:#3a404b}}td,th{{border-color:#2a2f38}}}}
</style></head><body><main>{body}</main></body></html>"""


def page(title: str, body: str) -> bytes:
    return PAGE.format(title=html.escape(title), body=body).encode()


def parse_cookies(header: str) -> dict:
    cookies = {}
    for part in (header or "").split(";"):
        if "=" in part:
            name, value = part.strip().split("=", 1)
            cookies[name] = value
    return cookies


def safe_next(value: str) -> str:
    """Only allow same-site relative redirects."""
    return value if value.startswith("/") and not value.startswith("//") and not value.startswith("/_lab/login") else "/"


class Handler(BaseHTTPRequestHandler):
    server_version = "lab-auth/1.0"

    def log_message(self, fmt, *args):  # never log query strings or bodies
        print(f"{self.address_string()} {self.command} {urllib.parse.urlsplit(self.path).path} -> {args[1] if len(args) > 1 else ''}",
              flush=True)

    # helpers
    def respond(self, status: int, body: bytes = b"", headers: dict = None, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if body:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location: str, headers: dict = None):
        self.respond(302, b"", {"Location": location, **(headers or {})})

    def is_https(self) -> bool:
        return self.headers.get("X-Forwarded-Proto", "http") == "https"

    def session(self):
        return SESSIONS.get(parse_cookies(self.headers.get("Cookie", "")).get(COOKIE, ""))

    def https_url(self, path: str) -> str:
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").split(":")[0]
        return f"https://{host}:{HTTPS_PORT}{path}" if HTTPS_PORT else path

    # routes
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/_lab/health":
            return self.respond(200, b'{"status":"ok"}', content_type="application/json")
        if url.path == "/_lab/verify":
            return self.verify()
        if url.path == "/_lab/login":
            if not self.is_https():
                return self.redirect(self.https_url("/_lab/login?next=" + urllib.parse.quote(safe_next(query.get("next", "/")))))
            return self.login_form(safe_next(query.get("next", "/")))
        if url.path == "/_lab/logout":
            SESSIONS.drop(parse_cookies(self.headers.get("Cookie", "")).get(COOKIE, ""))
            return self.redirect("/_lab/login", {"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
        if url.path in ("/_lab/whoami", "/"):
            return self.whoami()
        if url.path == "/_lab/internal/traffic-logs":
            return self.internal_logs(query)
        return self.respond(404, page("Not found", "<h1>Not found</h1>"))

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/_lab/login":
            return self.respond(404, page("Not found", "<h1>Not found</h1>"))
        if not self.is_https():
            return self.redirect(self.https_url("/_lab/login"))
        length = min(int(self.headers.get("Content-Length", "0") or 0), 8192)
        form = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode(errors="replace")))
        username, password = form.get("username", "").strip(), form.get("password", "")
        next_path = safe_next(form.get("next", "/"))
        identity, faig, error = None, None, "Sign-in failed. Check your FortiAIGate email and password."
        if username and password:
            if MODE == "fallback":
                identity = fallback_login(username, password)
            else:
                faig = FaigSession()
                try:
                    user = faig.login(username, password)
                    identity = classify_faig_user(user, items(faig.call("GET", "/api/v1/me/workspaces")))
                    if identity is None:
                        error = "This account is not a lab student or administrator."
                except (urllib.error.URLError, KeyError, ValueError):
                    identity = None
        password = None
        if not identity:
            return self.login_form(next_path, error, status=401)
        token = SESSIONS.create(identity, faig)
        cookie = f"{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={int(MAX_SESSION)}"
        return self.redirect(next_path, {"Set-Cookie": cookie})

    def login_form(self, next_path: str, error: str = "", status: int = 200):
        mode_note = ("Fallback sign-in is active; Traffic Log views are unavailable."
                     if MODE == "fallback" else "Use your FortiAIGate email and password.")
        body = (f"<h1>FortiAIGate Lab sign-in</h1><p class='muted'>{html.escape(mode_note)}</p>"
                + (f"<p class='err'>{html.escape(error)}</p>" if error else "")
                + "<form method='post' action='/_lab/login'>"
                f"<input type='hidden' name='next' value='{html.escape(next_path, quote=True)}'>"
                "<label for='u'>Email</label><input id='u' name='username' autocomplete='username' required>"
                "<label for='p'>Password</label><input id='p' name='password' type='password' autocomplete='current-password' required>"
                "<button type='submit'>Sign in</button></form>")
        return self.respond(status, page("Lab sign-in", body))

    def verify(self):
        session = self.session()
        if not session:
            return self.respond(401)
        identity = dict(session["identity"], ts=str(int(time.time())))
        headers = {"X-Lab-User": identity["user"], "X-Lab-Student": identity["student"], "X-Lab-Role": identity["role"],
                   "X-Lab-Workspace-Id": identity["workspace_id"], "X-Lab-Ts": identity["ts"],
                   "X-Lab-Signature": sign_identity(identity)}
        return self.respond(200, b"", headers)

    def whoami(self):
        session = self.session()
        if not session:
            return self.redirect("/_lab/login?next=" + urllib.parse.quote(self.path))
        identity = session["identity"]
        expires = time.strftime("%H:%M UTC", time.gmtime(session["created"] + MAX_SESSION))
        rows = ""
        note = "Traffic Log check unavailable (fallback sign-in)." if not session["faig"] else ""
        if session["faig"] and identity["role"] == "student":
            try:
                logs = items(session["faig"].call("GET", f"/api/v1/workspaces/{identity['workspace_id']}/traffic-logs?limit=5"))
                rows = "".join(f"<tr><td>{html.escape(str(r.get('keyAlias')))}</td><td>{html.escape(str(r.get('verdictLabel')))}</td>"
                               f"<td>{html.escape(str(r.get('model')))}</td></tr>" for r in logs)
                note = f"Latest {len(logs)} Traffic Log entries for your workspace (read with your FAIG session):"
            except urllib.error.HTTPError as exc:
                note = f"Traffic Log check failed (HTTP {exc.code}); your FAIG session may have expired. Sign in again."
        body = (f"<h1>Signed in</h1><table><tr><th>Account</th><td>{html.escape(identity['user'])}</td></tr>"
                f"<tr><th>Role</th><td>{html.escape(identity['role'])}</td></tr>"
                f"<tr><th>Student</th><td>{html.escape(identity['student'] or '-')}</td></tr>"
                f"<tr><th>Workspace</th><td>{html.escape(identity['workspace'] or '-')}</td></tr>"
                f"<tr><th>Session ends</th><td>by {expires} (idle timeout {int(IDLE // 60)} min)</td></tr></table>"
                f"<p class='muted'>{html.escape(note)}</p>"
                + (f"<table><tr><th>Key</th><th>Verdict</th><th>Model</th></tr>{rows}</table>" if rows else "")
                + "<p class='muted'>The student chatbot will replace this page.</p><p><a href='/_lab/logout'>Sign out</a></p>")
        return self.respond(200, page("Signed in", body))

    def internal_logs(self, query: dict):
        """Upstream apps fetch the caller's own Traffic Log entries with signed identity headers."""
        identity = verify_identity({k.lower(): v for k, v in self.headers.items()})
        if not identity or identity["role"] != "student":
            return self.respond(403, b'{"error":"invalid or expired identity"}', content_type="application/json")
        session = SESSIONS.latest_for(identity["user"])
        if not session:
            return self.respond(409, b'{"error":"no active FAIG session; sign in again"}', content_type="application/json")
        workspace = session["identity"]["workspace_id"]
        try:
            if query.get("uuid"):
                if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", query["uuid"]):
                    return self.respond(400, b'{"error":"bad uuid"}', content_type="application/json")
                data = session["faig"].call("GET", f"/api/v1/workspaces/{workspace}/traffic-logs/{query['uuid']}")
            else:
                limit = max(1, min(int(query.get("limit", "50")), 200))
                rows = items(session["faig"].call("GET", f"/api/v1/workspaces/{workspace}/traffic-logs?limit={limit}&offset=0"))
                since = int(query.get("since", "0") or 0)
                key = query.get("key", "")
                data = {"items": [r for r in rows if (not key or r.get("keyAlias") == key) and r.get("timeStamp", 0) >= since]}
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                SESSIONS.drop(next((t for t, s in SESSIONS.data.items() if s is session), ""))
            return self.respond(502, json.dumps({"error": f"FAIG returned HTTP {exc.code}"}).encode(),
                                content_type="application/json")
        except ValueError:
            return self.respond(400, b'{"error":"bad query"}', content_type="application/json")
        return self.respond(200, json.dumps(data).encode(), content_type="application/json")


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"lab-auth listening on {PORT} (mode={MODE}, FAIG {FAIG_URL})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
