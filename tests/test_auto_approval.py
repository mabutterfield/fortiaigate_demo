"""Auto-approval worker, gateway wiring and Lab Management preference (Change 2026-11-20)."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY = REPO_ROOT / "chatbot" / "https-gateway" / "chart" / "files"
sys.path.insert(0, str(GATEWAY))
import lab_broker  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeFaig:
    def __init__(self, queue, fail=None, queue_error=None):
        self.queue, self.fail, self.queue_error, self.calls = queue, fail or {}, queue_error, []

    def call(self, method, path, payload=None):
        self.calls.append((method, path))
        if path == "/api/v1/admin/review-queue":
            if self.queue_error:
                raise urllib.error.HTTPError(path, self.queue_error, "x", {}, None)
            return {"items": list(self.queue)}
        for oid, code in self.fail.items():
            if f"/{oid}/" in path:
                raise urllib.error.HTTPError(path, code, "x", {}, None)
        self.queue = [i for i in self.queue if f"/{i['id']}/" not in path]
        return {}


QUEUE = [
    {"id": "p1", "type": "policy", "name": "student01_pol", "changeKind": "delete", "submittedAt": "2"},
    {"id": "g1", "type": "guardrail", "name": "student01_gr", "changeKind": "create", "submittedAt": "3"},
    {"id": "d1", "type": "detector", "name": "student02_det", "changeKind": "update", "submittedAt": "1"},
    {"id": "x1", "type": "model-group", "name": "other", "submittedAt": "0"},
]


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class WorkerTests(unittest.TestCase):
    def worker(self, clock=None, interval=60):
        return lab_broker.AutoApprover(interval=interval, max_session=8 * 3600, clock=clock or Clock(), start_thread=False)

    def test_approves_everything_in_layer_order_including_deletions(self):
        faig = FakeFaig(QUEUE)
        result = lab_broker.approve_pending(faig)
        posts = [p for m, p in faig.calls if m == "POST"]
        self.assertEqual(posts, ["/api/v1/admin/detectors/d1/approve", "/api/v1/admin/guardrails/g1/approve",
                                 "/api/v1/admin/policies/p1/approve"])
        self.assertEqual(len(result["approved"]), 3)
        self.assertIn("[delete]", result["approved"][2])
        self.assertEqual(len(result["skipped"]), 1)  # unknown type is reported, not approved

    def test_failed_item_does_not_stop_the_pass(self):
        result = lab_broker.approve_pending(FakeFaig(QUEUE, fail={"g1": 409}))
        self.assertEqual(len(result["approved"]), 2)
        self.assertIn("HTTP 409", result["failed"][0])

    def test_tick_counts_and_status_has_no_session(self):
        clock = Clock()
        worker = self.worker(clock)
        session = {"faig": FakeFaig(QUEUE), "created": clock.now, "identity": {"user": "admin@lab"}}
        status = worker.start(session, "admin@lab", 2)
        self.assertEqual((status["state"], status["ends_at"]), ("running", int(clock.now + 7200)))
        self.assertTrue(worker.tick(worker.generation))
        status = worker.status()
        self.assertEqual(status["totals"], {"approved": 3, "failed": 0})
        self.assertEqual(status["last_result"]["approved"], 3)
        json.dumps(status)  # serializable: no session or FAIG objects
        self.assertNotIn("faig", json.dumps(status))
        self.assertTrue(worker.owns(session))

    def test_401_expires_and_releases_session(self):
        worker = self.worker()
        session = {"faig": FakeFaig([], queue_error=401), "created": 1000.0}
        worker.start(session, "admin@lab", 1)
        self.assertFalse(worker.tick(worker.generation))
        status = worker.status()
        self.assertEqual((status["state"], status["enabled"]), ("expired", False))
        self.assertIn("HTTP 401", status["stop_reason"])
        self.assertFalse(worker.owns(session))

    def test_queue_outage_keeps_running_with_error(self):
        worker = self.worker()
        worker.start({"faig": FakeFaig([], queue_error=502), "created": 1000.0}, "a", 1)
        self.assertTrue(worker.tick(worker.generation))
        self.assertEqual(worker.status()["state"], "error")
        self.assertIn("HTTP 502", worker.status()["last_result"]["errors"][0])

    def test_chosen_duration_and_session_cap(self):
        clock = Clock()
        worker = self.worker(clock)
        worker.start({"faig": FakeFaig([]), "created": clock.now}, "a", 1)
        clock.now += 3601
        self.assertFalse(worker.tick(worker.generation))
        self.assertEqual((worker.status()["state"], worker.status()["stop_reason"]), ("stopped", "chosen duration ended"))
        # Signed in 7.5 h ago: an 8 h request is capped by FAIG's session limit and ends as expired.
        worker.start({"faig": FakeFaig([]), "created": clock.now - 7.5 * 3600}, "a", 8)
        self.assertEqual(worker.status()["ends_at"], int(clock.now + 0.5 * 3600))
        clock.now += 0.5 * 3600 + 1
        self.assertFalse(worker.tick(worker.generation))
        self.assertEqual(worker.status()["state"], "expired")

    def test_stop_and_restart_bump_generation(self):
        worker = self.worker()
        worker.start({"faig": FakeFaig([]), "created": 1000.0}, "a", 1)
        old = worker.generation
        worker.start({"faig": FakeFaig([]), "created": 1000.0}, "b", 2)
        self.assertFalse(worker.tick(old))
        worker.stop("turned off by b")
        self.assertEqual((worker.status()["state"], worker.status()["stop_reason"]), ("stopped", "turned off by b"))
        self.assertFalse(worker.tick(worker.generation))

    def test_hours_bounds(self):
        worker = self.worker()
        for hours in (0, 0.1, 9):
            with self.assertRaises(ValueError):
                worker.start({"faig": FakeFaig([]), "created": 1000.0}, "a", hours)


class GatewayWiringTests(unittest.TestCase):
    def setUp(self):
        self.auth = load("lab_auth_auto_approval", GATEWAY / "lab_auth.py")
        self.auth.AUTO_APPROVER = lab_broker.AutoApprover(start_thread=False)

    def handler(self, path, headers=None):
        h = self.auth.Handler.__new__(self.auth.Handler)
        h.path, h.headers, h.replies = path, headers or {}, []
        h.respond = lambda status, body=b"", headers=None, content_type="": h.replies.append(status)
        h.redirect = lambda location, headers=None: h.replies.append(302)
        return h

    def test_logout_stops_the_owners_worker_only(self):
        session = {"faig": FakeFaig([]), "created": 1000.0, "identity": {"user": "a"}, "seen": 1000.0, "handle": "h"}
        self.auth.SESSIONS.data["tok"] = session
        self.auth.SESSIONS.data["other"] = dict(session)
        self.auth.AUTO_APPROVER.start(session, "a", 1)
        self.handler("/_lab/logout", {"Cookie": f"{self.auth.COOKIE}=other"}).do_GET()
        self.assertEqual(self.auth.AUTO_APPROVER.status()["state"], "running")
        self.handler("/_lab/logout", {"Cookie": f"{self.auth.COOKIE}=tok"}).do_GET()
        status = self.auth.AUTO_APPROVER.status()
        self.assertEqual(status["state"], "stopped")
        self.assertIn("signed out", status["stop_reason"])


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.lm = load("lab_management_auto_approval",
                       REPO_ROOT / "chatbot" / "lab-management" / "chart" / "files" / "lab_management.py")
        self.dir = tempfile.TemporaryDirectory()
        self.db = self.lm.connect(self.dir.name + "/t.sqlite3")

    def tearDown(self):
        self.db.close()
        self.dir.cleanup()

    def test_default_on_for_eight_hours_then_saved(self):
        self.assertEqual(self.lm.auto_approval_preference(self.db), {"enabled": True, "hours": 8})
        self.lm.save_auto_approval_preference(self.db, False, 2.5)
        self.assertEqual(self.lm.auto_approval_preference(self.db), {"enabled": False, "hours": 2.5})
        self.lm.save_auto_approval_preference(self.db, True, 8)
        self.assertEqual(self.lm.auto_approval_preference(self.db), {"enabled": True, "hours": 8.0})

    def test_rejects_bad_values(self):
        for enabled, hours in ((1, 2), (True, 0), (True, 9), (True, True), (True, "2")):
            with self.assertRaises(ValueError):
                self.lm.save_auto_approval_preference(self.db, enabled, hours)


if __name__ == "__main__":
    unittest.main()
