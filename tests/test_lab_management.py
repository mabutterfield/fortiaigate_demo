"""Unit and render tests for the lab management page (chatbot/lab-management)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART = REPO_ROOT / "chatbot/lab-management/chart"
GATEWAY_CHART = REPO_ROOT / "chatbot/https-gateway/chart"

spec = importlib.util.spec_from_file_location("lab_management", CHART / "files/lab_management.py")
lm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lm)


def student_view():
    from catalog802.loader import build_views, load
    catalog, errors = load(REPO_ROOT)
    assert not errors, errors
    return build_views(catalog)["student"]


class CatalogTests(unittest.TestCase):
    def test_preview_from_rendered_student_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "catalog-student.json").write_text(json.dumps(student_view()))
            items, platform, error = lm.load_catalog(tmp)
        self.assertIsNone(error)
        hr = next(i for i in items if i["id"] == "hr-tool-dlp")
        self.assertEqual([a["id"] for a in hr["actions"]], ["alert", "redact", "block"])
        self.assertTrue(hr["prompts"]["attack"][0]["text"])
        self.assertEqual(hr["models"][0]["public_name"], "hr-tool-dlp")
        self.assertEqual(platform["currency"], "USD")
        # Backend instructions are not part of the instructor preview.
        self.assertFalse({"instruction", "instruction_text", "backend_instruction"} & set(hr))

    def test_missing_or_invalid_catalog_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(lm.load_catalog(tmp)[2], "catalog unavailable: catalog-student.json not found")
            Path(tmp, "catalog-student.json").write_text('{"view": "faig", "items": []}')
            items, _, error = lm.load_catalog(tmp)
        self.assertEqual(items, [])
        self.assertIn("catalog unavailable", error)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "journal.sqlite3")
        self.db = lm.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_selection_is_validated_and_survives_restart(self):
        lm.select(self.db, ["hr-tool-dlp"], {"hr-tool-dlp"})
        with self.assertRaises(ValueError):
            lm.select(self.db, ["unknown"], {"hr-tool-dlp"})
        self.db.close()
        self.db = lm.connect(self.path)
        self.assertEqual(lm.selected(self.db), ["hr-tool-dlp"])

    def test_jobs_are_blocked_and_reject_extra_fields(self):
        with self.assertRaises(ValueError):
            lm.create_job(self.db, "models", "admin@lab", {})  # nothing selected
        lm.select(self.db, ["hr-tool-dlp"], {"hr-tool-dlp"})
        lm.create_job(self.db, "models", "admin@lab", {})
        lm.create_job(self.db, "students", "admin@lab",
                      {"count": 2, "start_index": 1, "prepopulate": False, "password_mode": "base"})
        self.assertEqual({j["kind"]: j["status"] for j in lm.jobs(self.db)}, {"models": "queued", "students": "queued"})
        ok = {"count": 2, "start_index": 1, "prepopulate": False, "password_mode": "generated"}
        for bad in (dict(ok, password="secret"),          # passwords never reach the journal
                    dict(ok, count=0), dict(ok, start_index=100), dict(ok, start_index=98, count=5),
                    dict(ok, count="2"), dict(ok, password_mode="weak"), dict(ok, prepopulate="yes")):
            with self.assertRaises(ValueError):
                lm.create_job(self.db, "students", "admin@lab", bad)
        self.assertNotIn("secret", json.dumps(lm.jobs(self.db)))


class AuthorizationTests(unittest.TestCase):
    ADMIN = {"X-Lab-Role": "admin", "X-Lab-User": "admin@lab", "X-Lab-Ts": "1", "X-Lab-Signature": "sig"}

    def setUp(self):
        lm._auth_cache.clear()

    def test_non_admin_or_incomplete_identity_denied_without_calling_gateway(self):
        with patch.object(lm, "AUTH_URL", "http://auth"), patch("urllib.request.build_opener") as opener:
            self.assertFalse(lm.authorize({"X-Lab-Role": "student"}))
            self.assertFalse(lm.authorize({"X-Lab-Role": "admin"}))
            opener.assert_not_called()

    def test_gateway_failure_denies(self):
        with patch.object(lm, "AUTH_URL", "http://auth"), \
                patch("urllib.request.build_opener", side_effect=OSError("offline")):
            self.assertFalse(lm.authorize(self.ADMIN))

    def test_positive_result_is_cached_briefly(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return b'{"items": []}'
        with patch.object(lm, "AUTH_URL", "http://auth"), patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = Response()
            self.assertTrue(lm.authorize(self.ADMIN, now=100))
            self.assertTrue(lm.authorize(self.ADMIN, now=110))
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertTrue(lm.authorize(self.ADMIN, now=200))
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_origin_must_match_gateway_forwarded_host(self):
        base = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "lab.example:30444", "X-Lab-Request": "1"}
        with patch.object(lm, "PUBLIC_ORIGIN", ""):
            self.assertTrue(lm.origin_ok(dict(base, Origin="https://lab.example:30444")))
            self.assertFalse(lm.origin_ok(dict(base, Origin="https://evil.example")))
            self.assertFalse(lm.origin_ok({**base, "Origin": "https://lab.example:30444", "X-Lab-Request": ""}))
            self.assertFalse(lm.origin_ok({"Origin": "https://lab.example:30444", "X-Lab-Request": "1"}))
        with patch.object(lm, "PUBLIC_ORIGIN", "https://fixed.example"):
            self.assertTrue(lm.origin_ok(dict(base, Origin="https://fixed.example")))


class StaticPageTests(unittest.TestCase):
    def test_page_uses_relative_urls_for_the_manage_prefix(self):
        html = (CHART / "files/index.html").read_text()
        js = (CHART / "files/app.js").read_text()
        self.assertNotIn('href="/', html)
        self.assertNotIn('src="/', html)
        self.assertNotIn("api('/", js)


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class RenderTests(unittest.TestCase):
    def helm(self, chart, *args):
        return subprocess.run(["helm", "template", "t", str(chart), *args],
                              check=True, capture_output=True, text=True).stdout

    def test_management_chart_has_no_token_and_one_writer(self):
        out = self.helm(CHART)
        self.assertIn("automountServiceAccountToken: false", out)
        self.assertIn("type: Recreate", out)
        self.assertIn("name: lab-catalog", out)
        self.assertIn("readOnlyRootFilesystem: true", out)
        self.assertNotIn("kind: Secret", out)

    def test_gateway_prefix_route_and_internal_block(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml") as values:
            values.write(
                "routes:\n"
                "  - name: chatbot\n    externalPort: 30444\n    auth: true\n"
                "    upstream: http://lab-chatbot.lab-chatbot.svc.cluster.local:80\n"
                "    prefixRoutes:\n      - path: /manage/\n"
                "        upstream: http://lab-management.lab-management.svc.cluster.local:80\n"
                "labAuth:\n  enabled: true\n")
            values.flush()
            out = self.helm(GATEWAY_CHART, "-f", values.name, "--show-only", "templates/configmap.yaml")
        self.assertIn("location /_lab/internal/ {\n          return 404;", out)
        self.assertIn("location = /manage {", out)
        block = out[out.index("location /manage/ {"):]
        block = block[:block.index("location / {")]
        self.assertIn("auth_request /_lab_auth;", block)
        self.assertIn("proxy_set_header X-Lab-Signature $lab_signature;", block)
        # set must precede rewrite ... break or the upstream variable stays empty.
        self.assertLess(block.index("set $proxy_upstream"), block.index("rewrite ^/manage/"))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- models job (Change 2026-11-19)

PROVIDER = {
    "providerId": "litellm-direct", "platform": "custom", "name": "litellm-direct", "endpoint": "/v1",
    "description": None, "autoSyncNewModels": False, "updatedAt": "t1",
    "apiKeys": [{"id": "k1", "name": "litellm-direct/litellm-key", "enabled": True, "weight": 1,
                 "apiKeyMasked": "sk-***abcd"}],
    "models": [
        {"uuid": "u1", "modelId": "pass-model", "publicName": "pass-model", "enabled": True, "isCustom": True,
         "customizedCost": True, "customInputCost": 3000, "customOutputCost": 8000,
         "customCacheReadCost": None, "customCacheWriteCost": None},
        {"uuid": "u2", "modelId": "other-model", "publicName": "other-model", "enabled": True, "isCustom": True,
         "customizedCost": False, "customInputCost": None, "customOutputCost": None,
         "customCacheReadCost": None, "customCacheWriteCost": None},
    ],
}


class FakeFaig:
    """Stands in for the broker: keeps one provider and applies PUTs like FAIG."""

    def __init__(self, provider, fail_put=None):
        self.provider = json.loads(json.dumps(provider))
        self.calls = []
        self.fail_put = fail_put

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            return json.loads(json.dumps(self.provider))
        if method == "PUT":
            self.provider["models"] = [dict(m, uuid=m.get("uuid") or "new-" + m["modelId"]) for m in body["models"]]
            self.provider["apiKeys"] = [dict(k, apiKeyMasked="sk-***abcd") for k in body["apiKeys"]]
            if self.fail_put:
                raise self.fail_put
            return self.provider
        raise AssertionError(method)


class ModelsJobTests(unittest.TestCase):
    def setUp(self):
        from catalog802.loader import build_views, load
        catalog, errors = load(REPO_ROOT)
        self.assertFalse(errors)
        self.view = build_views(catalog)["faig"]

    def test_prices_convert_to_api_numbers(self):
        self.assertEqual(lm.api_number("5000"), 5000)
        self.assertEqual(lm.api_number("0.25"), 0.25)
        self.assertIsNone(lm.api_number(None))
        with self.assertRaises(ValueError):
            lm.api_number("lots")
        self.assertEqual(lm.cost_fields({"input": "1", "output": None})["customizedCost"], True)
        self.assertEqual(lm.cost_fields({})["customizedCost"], False)

    def test_adds_missing_model_keeps_others_and_credentials(self):
        faig, lines = FakeFaig(PROVIDER), []
        lm.run_models_job(faig, self.view, {"hr-tool-dlp"}, lines.append)
        put = next(body for method, _, body in faig.calls if method == "PUT")
        self.assertEqual(put["apiKeys"], [{"id": "k1", "name": "litellm-direct/litellm-key", "description": None,
                                           "enabled": True, "weight": 1}])  # no secret, no mask
        ids = [m["modelId"] for m in put["models"]]
        self.assertEqual(ids, ["pass-model", "other-model", "hr-tool-dlp"])
        hr = put["models"][-1]
        self.assertEqual((hr["customInputCost"], hr["customOutputCost"], hr["customizedCost"]), (5000, 10000, True))
        self.assertEqual(put["models"][1]["customizedCost"], False)  # unrelated model untouched
        self.assertIn("saved and verified", lines[-1])

    def test_no_change_means_no_write(self):
        provider = json.loads(json.dumps(PROVIDER))
        provider["models"].append({"uuid": "u3", "modelId": "hr-tool-dlp", "publicName": "hr-tool-dlp",
                                   "enabled": True, "isCustom": True, "customizedCost": True,
                                   "customInputCost": 5000, "customOutputCost": 10000,
                                   "customCacheReadCost": None, "customCacheWriteCost": None})
        faig, lines = FakeFaig(provider), []
        lm.run_models_job(faig, self.view, {"hr-tool-dlp"}, lines.append)
        self.assertEqual([m for m, _, _ in faig.calls], ["GET"])
        self.assertIn("no change", lines[0])

    def test_unknown_put_outcome_is_verified_by_reading_back(self):
        faig, lines = FakeFaig(PROVIDER, fail_put=lm.UnknownOutcome("timeout")), []
        lm.run_models_job(faig, self.view, {"hr-tool-dlp"}, lines.append)
        self.assertEqual([m for m, _, _ in faig.calls], ["GET", "PUT", "GET"])
        self.assertIn("outcome unknown", " ".join(lines))
        self.assertIn("saved and verified", lines[-1])

    def test_lost_model_after_save_fails_loudly(self):
        class Lossy(FakeFaig):
            def __call__(self, method, path, body=None):
                result = super().__call__(method, path, body)
                if method == "PUT":
                    self.provider["models"] = [m for m in self.provider["models"] if m["modelId"] != "other-model"]
                return result
        with self.assertRaises(lm.BrokerError) as raised:
            lm.run_models_job(Lossy(PROVIDER), self.view, {"hr-tool-dlp"}, lambda _: None)
        self.assertIn("other-model", str(raised.exception))

    def test_unknown_selected_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            lm.desired_models(self.view, {"no-such-scenario"})


class ExecuteTests(unittest.TestCase):
    def test_session_loss_and_restart_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "j.sqlite3")
            db = lm.connect(path)
            lm.select(db, ["hr-tool-dlp"], {"hr-tool-dlp"})
            job = lm.create_job(db, "models", "admin@lab", {})
            self.assertEqual(db.execute("SELECT status FROM jobs").fetchone()[0], "queued")
            with patch.object(lm, "load_faig_view", return_value={}), \
                    patch.object(lm, "run_models_job", side_effect=lm.SessionLost("x")):
                lm.execute(job, "models", {"scenarios": ["hr-tool-dlp"]}, "handle", db_path=path)
            self.assertEqual(db.execute("SELECT status FROM jobs").fetchone()[0], "needs-sign-in")
            job2 = lm.create_job(db, "models", "admin@lab", {})
            lm.interrupt_unfinished(db)
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?", (job2,)).fetchone()[0], "interrupted")
            db.close()

    def test_broker_requires_token_and_handle(self):
        with patch.object(lm, "caller_token", return_value=""), patch.object(lm, "AUTH_URL", "http://auth"):
            with self.assertRaises(lm.BrokerError):
                lm.broker("h", "GET", "/api/v1/admin/ai-providers")
        with patch.object(lm, "caller_token", return_value="t" * 64), patch.object(lm, "AUTH_URL", "http://auth"):
            with self.assertRaises(lm.SessionLost):
                lm.broker("", "GET", "/api/v1/admin/ai-providers")


class StudentsJobTests(unittest.TestCase):
    def setUp(self):
        from catalog802.loader import build_views, load
        catalog, errors = load(REPO_ROOT)
        self.view = build_views(catalog)["faig"]

    def test_each_student_is_ensured_with_policy_and_catalog_providers(self):
        calls, lines = [], []
        def ensure(body):
            calls.append(body)
            return {"account": "created", "password": "stored", "workspace": "created",
                    "projects": {f"student{body['number']:02d}_hr-tool-dlp": "created"}, "verified": True, "notes": []}
        request = {"count": 2, "start_index": 3, "password_mode": "base", "scenarios": ["hr-tool-dlp"]}
        lm.run_students_job(ensure, self.view, request, "Base_Pass", lines.append)
        self.assertEqual([c["number"] for c in calls], [3, 4])
        self.assertEqual(calls[0]["password"], {"mode": "base", "value": "Base_Pass"})
        self.assertEqual(calls[0]["providers"], ["litellm-direct"])
        self.assertEqual(calls[0]["projects"], ["hr-tool-dlp"])
        self.assertTrue(lines[0].startswith("student03: account created"))
        self.assertNotIn("Base_Pass", " ".join(lines))

    def test_generated_mode_sends_no_value_and_failures_are_reported(self):
        calls, lines = [], []
        def ensure(body):
            calls.append(body)
            if body["number"] == 2:
                raise lm.BrokerError("FAIG rejects this password as weak: digitOk")
            return {"account": "exists", "password": "stored", "workspace": "exists", "projects": {},
                    "verified": True, "notes": []}
        request = {"count": 2, "start_index": 1, "password_mode": "generated", "scenarios": ["hr-tool-dlp"]}
        with self.assertRaises(lm.BrokerError):
            lm.run_students_job(ensure, self.view, request, None, lines.append)
        self.assertEqual(calls[0]["password"], {"mode": "generated"})
        self.assertIn("student02: FAILED", lines[1])

    def test_session_loss_stops_the_batch(self):
        def ensure(body):
            raise lm.SessionLost("sign in again")
        with self.assertRaises(lm.SessionLost):
            lm.run_students_job(ensure, self.view, {"count": 3, "start_index": 1, "password_mode": "generated",
                                                    "scenarios": ["hr-tool-dlp"]}, None, lambda _: None)


class PrepopulationPlanTests(unittest.TestCase):
    def test_plan_uses_catalog_naming_and_resolved_guards(self):
        from catalog802.loader import build_views, load
        catalog, _ = load(REPO_ROOT)
        view = build_views(catalog)["faig"]
        plan = lm.prepopulation_plan(view, {"hr-tool-dlp"}, "student03")
        self.assertEqual([e["action"] for e in plan["entries"]], ["alert", "redact", "block"])
        redact = plan["entries"][1]
        self.assertEqual(redact["key"], "student03_hr-tool-dlp_redact")
        self.assertEqual(redact["policy"], "student03_hr-tool-dlp_redact_policy")
        self.assertEqual(redact["project"], "student03_hr-tool-dlp")
        self.assertEqual(redact["guard"]["direction"], "output")
        self.assertEqual({d["disposition"] for d in redact["guard"]["detectors"]}, {"redact"})
        self.assertTrue(all(d["name"].startswith("student03_") for d in redact["guard"]["detectors"]))
        self.assertEqual(plan["passthrough"], {"key": "student03_passthrough", "model": "pass-model",
                                               "provider": "litellm-direct"})
        self.assertEqual(lm.prepopulation_plan(view, set(), "student03")["entries"], [])

    def test_prepopulate_job_reports_each_student(self):
        from catalog802.loader import build_views, load
        catalog, _ = load(REPO_ROOT)
        view = build_views(catalog)["faig"]
        calls, lines = [], []
        def prepopulate(body):
            calls.append(body)
            return {"created": ["key a"], "approved": ["policy p"], "existing": [], "keys_saved": ["a"],
                    "skipped": [], "notes": []}
        lm.run_prepopulate_job(prepopulate, view, {"count": 2, "start_index": 3, "scenarios": ["hr-tool-dlp"]},
                               lines.append)
        self.assertEqual([c["number"] for c in calls], [3, 4])
        self.assertTrue(lines[0].startswith("student03: prepopulated — 1 created, 1 approved"))
        self.assertNotIn("secret", json.dumps(calls).lower())
