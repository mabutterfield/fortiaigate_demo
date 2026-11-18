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


if __name__ == "__main__":
    unittest.main()
