from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from functional_test import curl_renderer
from scripts import scenario_local


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = REPO_ROOT / "chatbot" / "scenarios" / "examples"


class FunctionalCurlRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temporary_directory.name)
        self.store = scenario_local.LocalScenarioStore(
            repo_root=REPO_ROOT,
            local_root=self.temp_root / "local",
            raw_output_root=self.temp_root / "work-orders",
        )
        for scenario_id in (
            "fortistore-injection",
            "hr-tool-dlp",
            "resume-tool-injection",
        ):
            self.store.add(
                scenario_id,
                SCENARIO_ROOT / scenario_id / "profile.json",
                now=100,
            )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def args(self, scenario: str, action: str, case_id: str) -> argparse.Namespace:
        return argparse.Namespace(
            scenario=scenario,
            action=action,
            case_id=case_id,
        )

    def test_every_validation_case_renders_from_installed_metadata(self) -> None:
        expected_cases = {
            "fortistore-injection": {"alert-attack", "deny-attack"},
            "hr-tool-dlp": {"alert-attack", "deny-attack", "redact-attack"},
            "resume-tool-injection": {"alert-attack", "deny-attack"},
        }
        with mock.patch.object(
            curl_renderer.scenario_local,
            "LocalScenarioStore",
            return_value=self.store,
        ):
            for scenario_id, case_ids in expected_cases.items():
                profile = json.loads(
                    (self.store.scenario_path(scenario_id) / "profile.json").read_text(
                        encoding="utf-8"
                    )
                )
                actions = {
                    case["id"]: case["action"]
                    for case in profile["validation"]["cases"]
                }
                self.assertEqual(set(actions), case_ids)
                for case_id, action in actions.items():
                    with self.subTest(scenario=scenario_id, case=case_id):
                        body, metadata = curl_renderer.render_request(
                            self.args(scenario_id, action, case_id)
                        )
                        self.assertEqual(body["model"], scenario_id)
                        self.assertEqual(metadata["action"], action)
                        self.assertEqual(metadata["case"], case_id)
                        self.assertEqual(
                            metadata["request_path"],
                            f"/v1/{scenario_id}/{action}/chat/completions",
                        )

    def test_fortistore_frontend_instructions_are_rendered_dynamically(self) -> None:
        with mock.patch.object(
            curl_renderer.scenario_local,
            "LocalScenarioStore",
            return_value=self.store,
        ):
            body, metadata = curl_renderer.render_request(
                self.args("fortistore-injection", "deny", "deny-attack")
            )
        self.assertEqual(
            metadata["frontend_instruction_profile"],
            "fortistore-injection-compromised",
        )
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn("misconfigured for testing", body["messages"][0]["content"])

    def test_resume_request_stops_at_poisoned_tool_result(self) -> None:
        with mock.patch.object(
            curl_renderer.scenario_local,
            "LocalScenarioStore",
            return_value=self.store,
        ):
            body, _metadata = curl_renderer.render_request(
                self.args("resume-tool-injection", "deny", "deny-attack")
            )
        executed = [
            tool_call["function"]["name"]
            for message in body["messages"]
            for tool_call in message.get("tool_calls", [])
        ]
        self.assertEqual(executed, ["document_upload_simulation", "document_read"])
        self.assertNotIn("cloud_bucket_list_demo", executed)


if __name__ == "__main__":
    unittest.main()
