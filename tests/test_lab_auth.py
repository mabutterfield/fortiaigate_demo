"""Unit tests for the lab login gateway auth service (https-gateway chart)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lab_auth", REPO_ROOT / "chatbot" / "https-gateway" / "chart" / "files" / "lab_auth.py")
lab_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_auth)
KEY = b"unit-test-key"


def headers_for(identity, key=KEY):
    signed = dict(identity)
    out = {"x-lab-" + f.replace("_", "-"): str(signed[f]) for f in lab_auth.IDENTITY_FIELDS}
    out["x-lab-signature"] = lab_auth.sign_identity(signed, key)
    return out


class IdentityTests(unittest.TestCase):
    IDENTITY = {"user": "student02@fortiai.lab", "student": "student02", "role": "student",
                "workspace_id": "ws-2", "ts": "1000"}

    def test_valid_signature_round_trip(self):
        self.assertEqual(lab_auth.verify_identity(headers_for(self.IDENTITY), KEY, now=1100)["student"], "student02")

    def test_tampered_or_foreign_signature_is_rejected(self):
        tampered = headers_for(self.IDENTITY)
        tampered["x-lab-student"] = "student01"
        self.assertIsNone(lab_auth.verify_identity(tampered, KEY, now=1100))
        self.assertIsNone(lab_auth.verify_identity(headers_for(self.IDENTITY, b"other"), KEY, now=1100))
        self.assertIsNone(lab_auth.verify_identity({}, KEY, now=1100))

    def test_stale_or_future_signature_is_rejected(self):
        self.assertIsNone(lab_auth.verify_identity(headers_for(self.IDENTITY), KEY, now=1000 + lab_auth.SIGNATURE_MAX_AGE + 1))
        self.assertIsNone(lab_auth.verify_identity(headers_for(self.IDENTITY), KEY, now=900))


class AccountMappingTests(unittest.TestCase):
    def test_student_workspace_admin(self):
        identity = lab_auth.classify_faig_user(
            {"email": "student02@fortiai.lab", "role": "workspace_admin"},
            [{"id": "ws-2", "workspaceName": "student02_workspace", "membershipRole": "admin"}])
        self.assertEqual((identity["student"], identity["role"], identity["workspace_id"]), ("student02", "student", "ws-2"))

    def test_super_admin(self):
        identity = lab_auth.classify_faig_user({"email": "admin@example.com", "role": "super_admin"}, [])
        self.assertEqual((identity["role"], identity["student"]), ("admin", ""))

    def test_other_accounts_are_refused(self):
        self.assertIsNone(lab_auth.classify_faig_user({"role": "workspace_admin"},
                                                      [{"workspaceName": "finance_workspace", "membershipRole": "admin"}]))
        self.assertIsNone(lab_auth.classify_faig_user({"role": "org_member"},
                                                      [{"workspaceName": "student02_workspace", "membershipRole": "member"}]))


class AdminHelperTests(unittest.TestCase):
    USERS = [
        {"id": "u1", "email": "student01@fortiai.lab", "isActive": True, "keyCount": 9,
         "workspaces": [{"workspaceId": "w1", "workspaceName": "student01_workspace", "spend": 12.345}]},
        {"id": "u0", "email": "admin@example.com", "isActive": True, "workspaces": []},
        {"id": "u9", "email": "x@lab", "workspaces": [{"workspaceId": "w9", "workspaceName": "finance_workspace"}]},
    ]

    def test_student_rows_only_lab_students(self):
        rows = lab_auth.student_rows(self.USERS)
        self.assertEqual([(r["student"], r["user_id"], r["workspace_id"], r["spend"]) for r in rows],
                         [("student01", "u1", "w1", 12.35)])

    def test_weak_requirements(self):
        self.assertEqual(lab_auth.weak_requirements({"lengthOk": True, "specialCharOk": False, "digitOk": False}),
                         ["a digit", "a special character"])

    def test_fallback_entry_logs_in(self):
        entry = lab_auth.fallback_entry("N3w!password", "student01", "w1", "student01_workspace", iterations=1000)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"student01@fortiai.lab": entry}, handle)
        identity = lab_auth.fallback_login("student01@fortiai.lab", "N3w!password", handle.name)
        self.assertEqual((identity["student"], identity["workspace_id"]), ("student01", "w1"))
        self.assertNotIn("N3w!password", json.dumps(entry))
        Path(handle.name).unlink()


class FallbackTests(unittest.TestCase):
    def test_pbkdf2_store(self):
        salt = "00" * 16
        store = {"student01@fortiai.lab": {"salt": salt, "iterations": 1000, "student": "student01", "role": "student",
                                           "hash": lab_auth.hash_password("right", salt, 1000)}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(store, handle)
        self.assertEqual(lab_auth.fallback_login("student01@fortiai.lab", "right", handle.name)["student"], "student01")
        self.assertIsNone(lab_auth.fallback_login("student01@fortiai.lab", "wrong", handle.name))
        self.assertIsNone(lab_auth.fallback_login("nobody", "right", handle.name))
        Path(handle.name).unlink()


class SessionTests(unittest.TestCase):
    def test_idle_and_absolute_expiry(self):
        sessions = lab_auth.Sessions()
        token = sessions.create({"user": "u", "student": "s"}, None)
        created = sessions.data[token]["created"]
        self.assertIsNotNone(sessions.get(token, now=created + 10))
        self.assertIsNone(sessions.get(token, now=created + 10 + lab_auth.IDLE + 1))
        token = sessions.create({"user": "u", "student": "s"}, None)
        created = sessions.data[token]["created"]
        sessions.data[token]["seen"] = created + lab_auth.MAX_SESSION
        self.assertIsNone(sessions.get(token, now=created + lab_auth.MAX_SESSION + 1))

    def test_safe_next_blocks_open_redirects(self):
        self.assertEqual(lab_auth.safe_next("/chat?x=1"), "/chat?x=1")
        for bad in ("https://evil.example/", "//evil.example/", "javascript:alert(1)", "/_lab/login"):
            self.assertEqual(lab_auth.safe_next(bad), "/")



class KeyValueCheckTests(unittest.TestCase):
    """Change 2026-11-20: pasted key values are checked with FAIG before they are stored."""

    def check(self, outcome):
        import urllib.error, urllib.request
        class Opener:
            def open(self, request, timeout=0):
                if isinstance(outcome, Exception):
                    raise outcome
                class R:
                    status = outcome
                    def __enter__(self): return self
                    def __exit__(self, *a): return False
                return R()
        original = urllib.request.build_opener
        urllib.request.build_opener = lambda *a: Opener()
        try:
            return lab_auth.check_key_value("faig_" + "x" * 40, base="https://faig")
        finally:
            urllib.request.build_opener = original

    def test_outcomes(self):
        import urllib.error
        self.assertEqual(self.check(200), "ok")
        self.assertEqual(self.check(urllib.error.HTTPError("u", 401, "no", {}, None)), "invalid")
        self.assertEqual(self.check(urllib.error.HTTPError("u", 500, "err", {}, None)), "unknown")
        self.assertEqual(self.check(urllib.error.URLError("down")), "unknown")


class InternalLogsTests(unittest.TestCase):
    """Change 2026-11-20: an admin acting as a student reads that student's workspace log."""

    def run_logs(self, identity, query, roster=None):
        calls = []
        class Faig:
            def call(self, method, path, payload=None):
                calls.append(path)
                return {"items": [{"keyAlias": "student01_x", "timeStamp": 5}]}
        replies = []
        handler = lab_auth.Handler.__new__(lab_auth.Handler)
        handler.headers = {}
        handler.respond = lambda status, body=b"", **k: replies.append((status, json.loads(body)))
        saved = (lab_auth.verify_identity, lab_auth.SESSIONS.latest_for, lab_auth.LabDataStore)
        lab_auth.verify_identity = lambda headers: identity
        lab_auth.SESSIONS.latest_for = lambda user: {"faig": Faig(), "identity": {"workspace_id": "own-ws-0001"}}
        class Store:
            def get(self, kind, student): return roster
        lab_auth.LabDataStore = Store
        try:
            handler.internal_logs(query)
        finally:
            lab_auth.verify_identity, lab_auth.SESSIONS.latest_for, lab_auth.LabDataStore = saved
        return replies[0], calls

    def test_student_reads_own_workspace(self):
        (status, body), calls = self.run_logs({"user": "s", "role": "student"}, {"key": "student01_x"})
        self.assertEqual(status, 200)
        self.assertIn("/workspaces/own-ws-0001/", calls[0])

    def test_admin_acting_reads_student_workspace(self):
        (status, body), calls = self.run_logs({"user": "a", "role": "admin"}, {"key": "student01_x", "student": "student01"},
                                              roster={"workspace_id": "0123abcd-0000"})
        self.assertEqual(status, 200)
        self.assertIn("/workspaces/0123abcd-0000/", calls[0])
        self.assertEqual(len(body["items"]), 1)

    def test_admin_without_student_and_student_with_student_are_refused(self):
        self.assertEqual(self.run_logs({"user": "a", "role": "admin"}, {})[0][0], 403)
        self.assertEqual(self.run_logs({"user": "s", "role": "student"}, {"student": "student02"})[0][0], 403)

    def test_unknown_student_workspace_is_404(self):
        self.assertEqual(self.run_logs({"user": "a", "role": "admin"}, {"student": "student09"}, roster={})[0][0], 404)


if __name__ == "__main__":
    unittest.main()
