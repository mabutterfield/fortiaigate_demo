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


if __name__ == "__main__":
    unittest.main()
