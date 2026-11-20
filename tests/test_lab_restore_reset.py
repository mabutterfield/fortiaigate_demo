"""Key restore by rotation and student password reset (Change 2026-11-20)."""
from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_broker import PrepopAdmin, PrepopFaig, Store, StudentFaig, hr_plan, lab_broker  # noqa: E402


class RotatingFaig(PrepopFaig):
    def __init__(self, rotate_error=None):
        super().__init__()
        self.rotate_error, self.rotated = rotate_error, []

    def call(self, method, path, payload=None):
        if path.startswith("/api/v1/me/virtual-keys/") and path.endswith("/rotate"):
            kid = path.split("/")[-2]
            if self.rotate_error:
                raise urllib.error.HTTPError(path, self.rotate_error, "x", {}, None)
            self.rotated.append((kid, payload))
            return {"id": kid, "secretKey": "faig_" + kid.replace("-", "") + "_new_secret"}
        return super().call(method, path, payload)


LOST = {"id": "aaaa-bbbb", "keyName": "student03_hr-tool-dlp_redact", "policyIds": []}


class RestoreTests(unittest.TestCase):
    def run_restore(self, faig, restore=True, stored=None):
        store = Store()
        store.data["keys"] = {"student03": {"schema": 1, "keys": stored or []}}
        faig.keys.append(dict(LOST))
        out = lab_broker.prepopulate_student(PrepopAdmin(faig), faig, store, "student03", hr_plan(), lambda _: None,
                                             restore=restore)
        return out, store

    def test_lost_key_is_rotated_and_stored_with_its_mapping(self):
        faig = RotatingFaig()
        out, store = self.run_restore(faig)
        self.assertEqual(out["keys_restored"], ["student03_hr-tool-dlp_redact"])
        self.assertEqual(faig.rotated, [("aaaa-bbbb", {})])  # FAIG needs a JSON body
        record = next(k for k in store.data["keys"]["student03"]["keys"] if k["faig_key_id"] == "aaaa-bbbb")
        self.assertEqual((record["scenario_id"], record["action"], record["status"]), ("hr-tool-dlp", "redact", "untested"))
        self.assertTrue(record["secret"].startswith("faig_aaaabbbb"))
        self.assertFalse(any("without a stored secret" in n for n in out["notes"]))

    def test_key_with_a_stored_value_is_not_rotated(self):
        faig = RotatingFaig()
        out, _ = self.run_restore(faig, stored=[{"faig_key_id": "aaaa-bbbb", "secret": "faig_aaaabbbb_kept"}])
        self.assertEqual((faig.rotated, out["keys_restored"]), ([], []))

    def test_without_restore_it_is_only_reported(self):
        faig = RotatingFaig()
        out, _ = self.run_restore(faig, restore=False)
        self.assertEqual(faig.rotated, [])
        self.assertTrue(any("restore (rotate) it" in n for n in out["notes"]))

    def test_refused_and_unknown_rotation_are_reported_not_stored(self):
        out, store = self.run_restore(RotatingFaig(rotate_error=409))
        self.assertTrue(any("refused the rotation (HTTP 409); nothing changed" in n for n in out["notes"]))
        out, store = self.run_restore(RotatingFaig(rotate_error=502))
        self.assertTrue(any("rotation outcome unknown (HTTP 502)" in n for n in out["notes"]))
        self.assertFalse(any(k["faig_key_id"] == "aaaa-bbbb" for k in store.data["keys"]["student03"]["keys"]))



class RacingFaig(PrepopFaig):
    """Auto-approval approves each submission immediately (before prepopulation reads the queue)."""

    def call(self, method, path, payload=None):
        for kind in self.objects:
            collection = f"/api/v1/workspaces/w3/{kind}"
            if method == "GET" and path.startswith(collection + "/"):
                oid = path.rsplit("/", 1)[1]
                return next(o for o in self.objects[kind] if o["id"] == oid)
        out = super().call(method, path, payload)
        if path.endswith("/submit"):
            oid = path.split("/")[-2]
            for objs in self.objects.values():
                for obj in objs:
                    if obj["id"] == oid:
                        obj["status"] = "active"
            self.queue = [q for q in self.queue if q["id"] != oid]
            out = dict(out, status="pending")  # the student saw it pending
        return out


class LateApproveAdmin(PrepopAdmin):
    """The item is still listed, but auto-approval wins: our approve call gets 409."""

    def call(self, method, path, payload=None):
        if path.endswith("/approve"):
            oid = path.split("/")[-2]
            for objs in self.faig.objects.values():
                for obj in objs:
                    if obj["id"] == oid:
                        obj["status"] = "active"
            raise urllib.error.HTTPError(path, 409, "already approved", {}, None)
        return super().call(method, path, payload)


class AutoApprovalRaceTests(unittest.TestCase):
    def test_item_approved_before_queue_read(self):
        faig, store = RacingFaig(), Store()
        out = lab_broker.prepopulate_student(PrepopAdmin(faig), faig, store, "student03", hr_plan(), lambda _: None)
        self.assertEqual(out["approved"], [])
        self.assertTrue(any("(approved by auto-approval)" in e for e in out["existing"]))
        self.assertEqual(len(out["keys_saved"]), 4)

    def test_item_approved_between_queue_read_and_approve(self):
        class Lister(PrepopFaig):
            def call(self, method, path, payload=None):
                for kind in self.objects:
                    collection = f"/api/v1/workspaces/w3/{kind}"
                    if method == "GET" and path.startswith(collection + "/"):
                        oid = path.rsplit("/", 1)[1]
                        return next(o for o in self.objects[kind] if o["id"] == oid)
                return super().call(method, path, payload)
        faig, store = Lister(), Store()
        out = lab_broker.prepopulate_student(LateApproveAdmin(faig), faig, store, "student03", hr_plan(), lambda _: None)
        self.assertEqual(out["approved"], [])
        self.assertEqual(len(out["keys_saved"]), 4)

class ResetFaig(StudentFaig):
    def __init__(self, reset_error=None, applies=True, **kw):
        super().__init__(**kw)
        self.reset_error, self.applies = reset_error, applies
        self.users = [{"id": "u-student01@fortiai.lab", "email": "student01@fortiai.lab"}]
        self.passwords = {"student01@fortiai.lab": "Old_Pass_01"}

    def call(self, method, path, payload=None):
        if path.endswith("/password/reset"):
            if self.reset_error and self.reset_error >= 500 and self.applies:
                self.passwords["student01@fortiai.lab"] = payload["password"]
            if self.reset_error:
                raise urllib.error.HTTPError(path, self.reset_error, "x", {}, None)
            self.passwords["student01@fortiai.lab"] = payload["password"]
            return {}
        return super().call(method, path, payload)

    def session_factory(self):
        org = self

        class Session:
            def login(self, email, password):
                if org.passwords.get(email) != password:
                    raise urllib.error.HTTPError("/login", 401, "no", {}, None)
        return Session


class ResetTests(unittest.TestCase):
    REQ = {"number": 1, "password": {"mode": "shared", "value": "New_Pass_99"}}

    def store(self):
        store = Store()
        store.data["credentials"]["student01"] = {"username": "student01@fortiai.lab", "password": "Old_Pass_01",
                                                  "status": "active"}
        return store

    def test_success_stores_and_verifies(self):
        faig, store = ResetFaig(), self.store()
        out = lab_broker.reset_student_password(faig, faig.session_factory(), store, self.REQ)
        self.assertEqual((out["student"], out["verified"], out["password"]), ("student01", True, "stored"))
        cred = store.data["credentials"]["student01"]
        self.assertEqual((cred["password"], cred["status"]), ("New_Pass_99", "active"))
        self.assertNotIn("previous_password", cred)
        self.assertEqual([w[2] for w in store.writes], ["reset-pending", "active"])  # write-ahead first

    def test_refusal_keeps_previous_password(self):
        faig, store = ResetFaig(reset_error=400), self.store()
        with self.assertRaises(urllib.error.HTTPError):
            lab_broker.reset_student_password(faig, faig.session_factory(), store, self.REQ)
        self.assertEqual(store.data["credentials"]["student01"]["password"], "Old_Pass_01")

    def test_unknown_outcome_is_settled_by_sign_in(self):
        faig, store = ResetFaig(reset_error=502, applies=True), self.store()
        self.assertTrue(lab_broker.reset_student_password(faig, faig.session_factory(), store, self.REQ)["verified"])
        self.assertEqual(store.data["credentials"]["student01"]["password"], "New_Pass_99")
        faig, store = ResetFaig(reset_error=502, applies=False), self.store()
        with self.assertRaises(RuntimeError):
            lab_broker.reset_student_password(faig, faig.session_factory(), store, self.REQ)
        self.assertEqual(store.data["credentials"]["student01"]["password"], "Old_Pass_01")

    def test_rules(self):
        faig, store = ResetFaig(strong=False), self.store()
        with self.assertRaises(ValueError):
            lab_broker.reset_student_password(faig, faig.session_factory(), store, self.REQ)
        faig = ResetFaig()
        with self.assertRaises(ValueError):
            lab_broker.reset_student_password(faig, faig.session_factory(), self.store(), self.REQ,
                                              same_as_instructor=lambda pw: True)
        with self.assertRaises(KeyError):
            lab_broker.reset_student_password(faig, faig.session_factory(), self.store(),
                                              {"number": 7, "password": {"mode": "generated"}})



class JobValidationTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        import json
        import tempfile
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("lm_jobs", root / "chatbot/lab-management/chart/files/lab_management.py")
        self.lm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lm)
        self.dir = tempfile.TemporaryDirectory()
        self.db = self.lm.connect(self.dir.name + "/t.sqlite3")
        self.lm.select(self.db, ["hr-tool-dlp"], {"hr-tool-dlp"})
        self.json = json

    def tearDown(self):
        self.db.close()
        self.dir.cleanup()

    def request_of(self, job):
        return self.json.loads(self.db.execute("SELECT request FROM jobs WHERE id=?", (job,)).fetchone()[0])

    def test_prepopulate_restore_flag(self):
        job = self.lm.create_job(self.db, "prepopulate", "a", {"count": 1, "start_index": 3, "restore": True})
        self.assertTrue(self.request_of(job)["restore"])
        job = self.lm.create_job(self.db, "prepopulate", "a", {"count": 1, "start_index": 3})
        self.assertFalse(self.request_of(job)["restore"])
        with self.assertRaises(ValueError):
            self.lm.create_job(self.db, "prepopulate", "a", {"count": 1, "start_index": 3, "restore": "yes"})

    def test_password_job_never_journals_the_password(self):
        job = self.lm.create_job(self.db, "password", "a", {"number": 2, "password_mode": "generated"})
        self.assertEqual(self.request_of(job), {"number": 2, "password_mode": "generated"})
        for bad in ({"number": 0, "password_mode": "generated"}, {"number": 2, "password_mode": "x"},
                    {"number": 2, "password_mode": "shared", "password": "secret"}):
            with self.assertRaises(ValueError):
                self.lm.create_job(self.db, "password", "a", bad)

if __name__ == "__main__":
    unittest.main()
