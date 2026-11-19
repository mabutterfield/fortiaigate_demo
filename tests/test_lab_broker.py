"""Tests for the gateway broker: caller tokens, session handles and FAIG allowlists."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

FILES = Path(__file__).resolve().parents[1] / "chatbot/https-gateway/chart/files"
sys.path.insert(0, str(FILES))
import lab_broker  # noqa: E402

spec = importlib.util.spec_from_file_location("lab_auth_broker_test", FILES / "lab_auth.py")
lab_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_auth)

TOKEN = "a" * 64


class AllowlistTests(unittest.TestCase):
    def test_exact_paths_only(self):
        ok = [("GET", "/api/v1/admin/ai-providers"), ("GET", "/api/v1/admin/ai-providers/litellm-direct"),
              ("PUT", "/api/v1/admin/ai-providers/litellm-direct"), ("GET", "/api/v1/admin/users?offset=0&limit=100")]
        bad = [("DELETE", "/api/v1/admin/ai-providers/litellm-direct"),       # method swap
               ("GET", "/api/v1/admin/ai-providers/../licenses"),           # traversal
               ("GET", "/api/v1/admin/ai-providers/x%2F..%2Flicenses"),      # encoded slash
               ("GET", "/api/v1/admin/ai-providers//x"),
               ("GET", "/api/v1/admin/users?offset=0&role=admin"),          # extra query
               ("GET", "/api/v1/admin/users?limit=1;drop"),
               ("GET", "https://evil/api/v1/admin/ai-providers"),
               ("GET", "/api/v1/admin/licenses"),
               ("POST", "/api/v1/admin/users/x/password/reset"),
               ("GET", "/api/v1/admin/ai-providers#frag")]
        for method, path in ok:
            self.assertTrue(lab_broker.allowed(method, path), (method, path))
        for method, path in bad:
            self.assertFalse(lab_broker.allowed(method, path), (method, path))

    def test_caller_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "lab-management").write_text(TOKEN + "\n")
            Path(tmp, "unknown-caller").write_text("b" * 64)
            Path(tmp, "short").write_text("x")
            tokens = lab_broker.load_caller_tokens(tmp)
        self.assertEqual(tokens, {TOKEN: "lab-management"})
        self.assertEqual(lab_broker.caller_for("Bearer " + TOKEN, tokens), "lab-management")
        self.assertIsNone(lab_broker.caller_for("Bearer " + "b" * 64, tokens))
        self.assertIsNone(lab_broker.caller_for(TOKEN, tokens))
        self.assertIsNone(lab_broker.caller_for("", tokens))


class FakeFaig:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if self.error:
            raise self.error
        return {"providerId": "litellm-direct"}


class FakeHandler:
    """Minimal stand-in for lab_auth.Handler for the broker endpoint."""

    def __init__(self, headers, body):
        raw = json.dumps(body).encode()
        self.headers = dict(headers, **{"Content-Length": str(len(raw))})
        self.rfile = io.BytesIO(raw)
        self.replies = []

    def json_reply(self, status, value):
        self.replies.append((status, value))


def proxy(headers, body):
    handler = FakeHandler(headers, body)
    lab_auth.Handler.admin_faig_proxy(handler)
    return handler.replies[-1]


class ProxyTests(unittest.TestCase):
    def setUp(self):
        lab_auth.SESSIONS.data.clear()
        self.admin_faig = FakeFaig()
        token = lab_auth.SESSIONS.create({"user": "admin@lab", "student": "", "role": "admin", "workspace_id": "",
                                          "workspace": ""}, self.admin_faig)
        self.admin_handle = lab_auth.SESSIONS.data[token]["handle"]
        token = lab_auth.SESSIONS.create({"user": "s1@lab", "student": "student01", "role": "student",
                                          "workspace_id": "w1", "workspace": "student01_workspace"}, FakeFaig())
        self.student_handle = lab_auth.SESSIONS.data[token]["handle"]
        patcher = patch.object(lab_broker, "load_caller_tokens", return_value={TOKEN: "lab-management"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.get = {"method": "GET", "path": "/api/v1/admin/ai-providers/litellm-direct"}

    def test_admin_handle_with_management_token_is_forwarded(self):
        status, value = proxy({"Authorization": "Bearer " + TOKEN, "X-Lab-Session": self.admin_handle}, self.get)
        self.assertEqual((status, value["status"]), (200, 200))
        self.assertEqual(self.admin_faig.calls, [("GET", "/api/v1/admin/ai-providers/litellm-direct", None)])

    def test_forged_or_missing_credentials_rejected(self):
        cases = [({"X-Lab-Session": self.admin_handle}, 403),                                  # no token
                 ({"Authorization": "Bearer " + "c" * 64, "X-Lab-Session": self.admin_handle}, 403),
                 ({"Authorization": "Bearer " + TOKEN}, 401),                                    # no handle
                 ({"Authorization": "Bearer " + TOKEN, "X-Lab-Session": "made-up"}, 401),
                 ({"Authorization": "Bearer " + TOKEN, "X-Lab-Session": self.student_handle}, 403),
                 # signed-looking identity headers carry no authority
                 ({"Authorization": "Bearer " + TOKEN, "X-Lab-Role": "admin", "X-Lab-User": "admin@lab"}, 401)]
        for headers, expected in cases:
            self.assertEqual(proxy(headers, self.get)[0], expected, headers)
        self.assertEqual(self.admin_faig.calls, [])

    def test_disallowed_path_and_bad_body(self):
        auth = {"Authorization": "Bearer " + TOKEN, "X-Lab-Session": self.admin_handle}
        self.assertEqual(proxy(auth, {"method": "GET", "path": "/api/v1/admin/licenses"})[0], 403)
        self.assertEqual(proxy(auth, dict(self.get, extra=1))[0], 400)
        self.assertEqual(self.admin_faig.calls, [])

    def test_faig_session_expiry_ends_session(self):
        self.admin_faig.error = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"{}"))
        auth = {"Authorization": "Bearer " + TOKEN, "X-Lab-Session": self.admin_handle}
        self.assertEqual(proxy(auth, self.get)[0], 401)
        self.assertIsNone(lab_auth.SESSIONS.by_handle(self.admin_handle))

    def test_faig_error_and_unknown_outcome(self):
        auth = {"Authorization": "Bearer " + TOKEN, "X-Lab-Session": self.admin_handle}
        self.admin_faig.error = urllib.error.HTTPError("u", 422, "x", {}, io.BytesIO(b'{"error": "bad"}'))
        self.assertEqual(proxy(auth, self.get), (200, {"status": 422, "body": {"error": "bad"}}))
        self.admin_faig.error = TimeoutError("slow")
        self.assertEqual(proxy(auth, self.get)[0], 504)

    def test_handle_expires_with_session(self):
        session = lab_auth.SESSIONS.by_handle(self.admin_handle)
        self.assertIsNotNone(session)
        self.assertIsNone(lab_auth.SESSIONS.by_handle(self.admin_handle, now=session["created"] + lab_auth.MAX_SESSION + 1))


class Store:
    def __init__(self):
        self.data = {"credentials": {}, "roster": {}}
        self.writes = []

    def get(self, kind, student):
        return dict(self.data[kind].get(student, {}))

    def put(self, kind, student, value):
        self.writes.append((kind, student, value.get("status")))
        self.data[kind][student] = dict(value)

    def all(self, kind):
        return self.data[kind]


class StudentFaig:
    """Fake FAIG org for student creation (admin side)."""

    def __init__(self, strong=True, accept_fails=False):
        self.users, self.workspaces, self.projects, self.invites = [], [], [], {}
        self.passwords, self.strong, self.accept_fails, self.calls = {}, strong, accept_fails, []

    def call(self, method, path, payload=None):
        self.calls.append((method, path.split("?")[0]))
        if path.startswith("/api/v1/admin/users"):
            return {"items": list(self.users), "total": len(self.users)}
        if path == "/api/v1/me/password/strength":
            return {"isStrong": self.strong, "digitOk": self.strong}
        if path == "/api/v1/admin/user-invitations":
            self.invites["inv1"] = payload["emails"][0]
            return {"id": "inv1"}
        if path == "/api/v1/admin/workspaces" and method == "GET":
            return list(self.workspaces)
        if path == "/api/v1/admin/workspaces":
            ws = {"id": "ws-" + payload["workspaceName"], "workspaceName": payload["workspaceName"],
                  "admins": payload["admins"]}
            self.workspaces.append(ws)
            return ws
        if path.startswith("/api/v1/admin/ai-providers/"):
            return {"providerId": "litellm-direct", "platform": "custom", "name": "litellm-direct",
                    "apiKeys": [{"id": "k1", "name": "key"}]}
        if path == "/api/v1/admin/projects" and method == "GET":
            return list(self.projects)
        if path == "/api/v1/admin/projects":
            self.projects.append({"name": payload["name"], "workspaceId": payload["workspaceId"]})
            return self.projects[-1]
        raise AssertionError((method, path))

    def session_factory(self):
        org = self

        class Anonymous:
            def call(self, method, path, payload=None):
                if path.endswith("/identify"):
                    return {"outcome": "needs-registration"}
                if path.endswith("/accept"):
                    org.users.append({"id": "u-" + payload["email"], "email": payload["email"]})
                    org.passwords[payload["email"]] = payload["password"]
                    if org.accept_fails:
                        raise TimeoutError("lost reply")
                    return {"createdAccount": True}
                if path == "/api/v1/me/workspaces":
                    return [{"id": w["id"], "membershipRole": "admin"} for w in org.workspaces
                            if {"id": "u-" + self.email} in w["admins"]]
                return {}

            def login(self, email, password):
                assert org.passwords.get(email) == password, "wrong password"
                self.email = email
        return Anonymous


REQUEST = {"number": 1, "password": {"mode": "base", "value": "Lab_Pass"}, "providers": ["litellm-direct"],
           "projects": ["hr-tool-dlp", "fortistore-injection"]}


class StudentTests(unittest.TestCase):
    def test_passwords(self):
        self.assertEqual(lab_broker.student_password({"mode": "base", "value": "Lab_"}, 7), "Lab_07")
        self.assertEqual(lab_broker.student_password({"mode": "shared", "value": "Same_1"}, 7), "Same_1")
        generated = lab_broker.student_password({"mode": "generated"}, 1)
        self.assertEqual(len(generated), 24)
        for bad in ({"mode": "shared"}, {"mode": "base", "value": "a\nb"}, {"mode": "other", "value": "x"}):
            with self.assertRaises(ValueError):
                lab_broker.student_password(bad, 1)
        with self.assertRaises(ValueError):
            lab_broker.student_names(100)

    def test_create_then_rerun_is_idempotent(self):
        faig, store = StudentFaig(), Store()
        out = lab_broker.ensure_student(faig, faig.session_factory(), store, REQUEST, "admin@lab")
        self.assertEqual((out["account"], out["password"], out["workspace"], out["verified"]),
                         ("created", "stored", "created", True))
        self.assertEqual(set(out["projects"].values()), {"created"})
        self.assertEqual(faig.passwords["student01@fortiai.lab"], "Lab_Pass01")
        # password stored as pending BEFORE the account existed, then active
        self.assertEqual([w for w in store.writes if w[0] == "credentials"],
                         [("credentials", "student01", "pending"), ("credentials", "student01", "active")])
        self.assertEqual(store.data["roster"]["student01"]["username"], "student01@fortiai.lab")
        again = lab_broker.ensure_student(faig, faig.session_factory(), store, REQUEST, "admin@lab")
        self.assertEqual((again["account"], again["workspace"]), ("exists", "exists"))
        self.assertEqual(set(again["projects"].values()), {"exists"})
        self.assertEqual(len(faig.workspaces), 1)
        self.assertEqual(sum(1 for c in faig.calls if c == ("POST", "/api/v1/admin/user-invitations")), 1)

    def test_weak_or_instructor_password_creates_nothing(self):
        faig, store = StudentFaig(strong=False), Store()
        with self.assertRaises(ValueError):
            lab_broker.ensure_student(faig, faig.session_factory(), store, REQUEST, "admin@lab")
        faig = StudentFaig()
        with self.assertRaises(ValueError):
            lab_broker.ensure_student(faig, faig.session_factory(), store, REQUEST, "admin@lab",
                                      same_as_instructor=lambda pw: pw == "Lab_Pass01")
        self.assertEqual((faig.users, store.writes), ([], []))

    def test_lost_accept_reply_is_reconciled_from_faig(self):
        faig, store = StudentFaig(accept_fails=True), Store()
        out = lab_broker.ensure_student(faig, faig.session_factory(), store, REQUEST, "admin@lab")
        self.assertEqual((out["account"], out["verified"]), ("created", True))
        self.assertIn("did not confirm", out["notes"][0])
        self.assertEqual(store.data["credentials"]["student01"]["status"], "active")

    def test_existing_account_without_password_is_flagged_not_reset(self):
        faig, store = StudentFaig(), Store()
        faig.users.append({"id": "u-student01@fortiai.lab", "email": "student01@fortiai.lab"})
        out = lab_broker.ensure_student(faig, faig.session_factory(), store, REQUEST, "admin@lab")
        self.assertEqual((out["account"], out["password"], out["verified"]), ("exists", "unknown", False))
        self.assertNotIn(("POST", "/api/v1/admin/user-invitations"), faig.calls)

    def test_roster_hides_passwords_unless_revealed(self):
        roster = {"student01": {"number": 1, "display_name": "Ana", "username": "student01@fortiai.lab"}}
        creds = {"student01": {"password": "P_ss1234word"}}
        faig_rows = [{"student": "student01", "email": "student01@fortiai.lab", "workspace": "student01_workspace",
                      "active": True, "keys": 0}]
        hidden = lab_broker.roster_rows(roster, creds, faig_rows, reveal=False)
        self.assertNotIn("password", hidden[0])
        self.assertTrue(hidden[0]["password_stored"])
        self.assertEqual(lab_broker.roster_rows(roster, creds, faig_rows, reveal=True)[0]["password"], "P_ss1234word")
        self.assertTrue(lab_broker.DISPLAY_NAME.fullmatch("Ana María"))
        self.assertFalse(lab_broker.DISPLAY_NAME.fullmatch("<script>"))


if __name__ == "__main__":
    unittest.main()
