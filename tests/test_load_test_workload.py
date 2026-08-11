from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from functional_test import validation as scenario_validation
from load_test import statistics, traffic_generator, workload


REPO_ROOT = Path(__file__).resolve().parents[1]


class DashboardWorkloadTests(unittest.TestCase):
    @staticmethod
    def profiles() -> dict[str, dict]:
        return {
            scenario_id: json.loads(
                (
                    REPO_ROOT
                    / "chatbot"
                    / "scenarios"
                    / "examples"
                    / scenario_id
                    / "profile.json"
                ).read_text(encoding="utf-8")
            )
            for scenario_id in traffic_generator.BASELINE_SCENARIOS
        }

    @classmethod
    def matrix(cls) -> dict:
        routes = []
        chatbot_profiles = []
        for scenario_id, profile in cls.profiles().items():
            for entry in profile["matrix"]["entry_points"]:
                action = entry["action"]
                name = f"{scenario_id}-{action}"
                routes.append(
                    {
                        "name": name,
                        "label": name,
                        "base_path": f"/v1/{scenario_id}/{action}",
                        "action": action,
                        "scenario_id": scenario_id,
                        "model": scenario_id,
                    }
                )
                chatbot_profiles.append(
                    {
                        "scenario_id": scenario_id,
                        "provider_path": "faig-static",
                        "route": name,
                        "model": scenario_id,
                        "mcp_enabled": profile["mcp"]["enabled"],
                        "mcp_path": "direct",
                        "mcp_tool_profile": profile["mcp"]["tool_profile"],
                        "mcp_max_tool_rounds": profile["mcp"]["max_tool_rounds"],
                        "frontend_instruction_profile": "none",
                    }
                )
        return {
            "global": {"passthrough_model_alias": "pass-model"},
            "chatbot_faig_static_routes": routes,
            "chatbot_simplified_profiles": chatbot_profiles,
        }

    def test_metadata_declares_every_current_protected_path(self) -> None:
        items = scenario_validation.validation_plan_items(
            self.matrix(), self.profiles(), traffic_generator.BASELINE_SCENARIOS
        )
        self.assertEqual(len(items), 7)
        self.assertEqual(
            Counter(item["route"] for item in items),
            {"alert": 3, "deny": 3, "redact": 1},
        )
        resume_deny = next(
            item
            for item in items
            if item["scenario"] == "resume-tool-injection" and item["route"] == "deny"
        )
        self.assertIn("cloud_bucket_list_demo", resume_deny["forbidden_tools"])

    def test_24_hour_plan_varies_volume_and_preserves_hourly_action_floors(self) -> None:
        _path, profile = workload.load_profile("dashboard-balanced-24h")
        plan, hourly = workload.build_plan(
            profile,
            self.matrix(),
            self.profiles(),
            traffic_generator.high_token_prompt_templates(),
        )
        self.assertEqual(len(hourly), 24)
        self.assertEqual(len(plan), sum(hour["total_requests"] for hour in hourly))
        self.assertGreater(len({hour["total_requests"] for hour in hourly}), 1)
        for hour in hourly:
            self.assertGreaterEqual(hour["action_counts"].get("alert", 0), 1)
            self.assertGreaterEqual(hour["action_counts"].get("deny", 0), 1)
            self.assertGreaterEqual(hour["action_counts"].get("redact", 0), 1)
            self.assertGreaterEqual(hour["total_requests"], 12)
            self.assertLessEqual(hour["total_requests"], 30)
        normal = sum(hour["normal_requests"] for hour in hourly)
        self.assertGreaterEqual(normal / len(plan), 0.70)
        self.assertLessEqual(normal / len(plan), 0.80)
        self.assertEqual(
            [item["scheduled_offset_seconds"] for item in plan],
            sorted(item["scheduled_offset_seconds"] for item in plan),
        )

    def test_statistics_are_written_atomically_with_approximate_tokens(self) -> None:
        event = {
            "request_id": "req-00001",
            "scenario_id": "passthrough",
            "provider_route": "passthrough",
            "route": "passthrough",
            "outcome": "success",
            "completion_status": "ok",
            "latency_ms": 100,
            "approx_input_tokens": 25,
            "approx_response_length": 400,
            "expected_result": "completed",
            "actual_result": "completed",
            "result_matches_expected": True,
        }
        value = statistics.live_statistics(
            run_label="test",
            status="running",
            started_at="2026-08-06T00:00:00Z",
            plan=[{}],
            events=[event],
            submitted_requests=1,
            active_requests=0,
            gpu_samples=[],
        )
        self.assertEqual(value["approximate_input_tokens"], 25)
        self.assertEqual(value["approximate_output_tokens"], 100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "statistics.json"
            statistics.atomic_write_json(path, value)
            self.assertEqual(json.loads(path.read_text())["completed_requests"], 1)
            self.assertFalse((Path(directory) / ".statistics.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
