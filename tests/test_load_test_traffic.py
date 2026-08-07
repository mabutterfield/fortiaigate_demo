from __future__ import annotations

import types
import unittest
from collections import Counter

from functional_test import validation as scenario_validation
from load_test import statistics, traffic_generator


class TrafficGeneratorMatrixTests(unittest.TestCase):
    @staticmethod
    def passthrough_config() -> dict[str, object]:
        return {
            "action": "passthrough",
            "provider": "faig-static",
            "route": "passthrough",
            "model": "pass-model",
            "mcp_enabled": False,
            "mcp_path": "direct",
            "tool_profile": "",
            "max_tool_rounds": 3,
            "frontend_instruction_profile": "none",
        }

    def test_path_test_cases_are_derived_from_matrix(self) -> None:
        args = types.SimpleNamespace(
            legacy_routes=False,
            path_test_path=["alert", "passthrough"],
            path_test_passthrough_model="",
            path_test_base_url="https://faig.example",
            endpoint="",
            target="local",
            path_test_execution="direct",
        )
        matrix = {
            "chatbot_faig_static_routes": [
                {
                    "name": "fortistore-injection-alert",
                    "base_path": "/v1/fortistore-injection/alert",
                    "action": "alert",
                    "model": "fortistore-injection",
                },
                {
                    "name": "passthrough",
                    "base_path": "/v1/passthrough",
                    "action": "passthrough",
                    "model": "pass-model",
                },
            ]
        }
        cases = traffic_generator.path_test_cases(args, matrix)
        self.assertEqual(
            [case["path"] for case in cases],
            ["/v1/fortistore-injection/alert", "/v1/passthrough"],
        )
        self.assertEqual(cases[1]["model"], "pass-model")

    def test_traffic_plan_uses_matrix_path_configuration(self) -> None:
        args = types.SimpleNamespace(
            seed=42,
            traffic_profile="clean",
            duration=10,
            rate=6.0,
            tool_profile="",
            model="",
            mcp_path="",
            max_tool_rounds=0,
            frontend_profile="",
        )
        profiles = {
            "hr-tool-dlp": {
                "id": "hr-tool-dlp",
                "clean_prompts": ["Show the employee table."],
                "attack_prompts": [],
                "mcp": {"enabled": True, "tool_profile": "hr-tool-dlp"},
            }
        }
        path_config = {
            "action": "redact",
            "provider": "faig-static",
            "route": "hr-tool-dlp-redact",
            "model": "hr-tool-dlp",
            "mcp_enabled": True,
            "mcp_path": "direct",
            "tool_profile": "hr-tool-dlp",
            "max_tool_rounds": 5,
            "frontend_instruction_profile": "none",
        }
        plan = traffic_generator.build_plan(
            args,
            profiles,
            path_configs_by_scenario={"hr-tool-dlp": [path_config]},
        )
        self.assertEqual(plan[0]["route"], "redact")
        self.assertEqual(
            plan[0]["path_config"]["route"],
            "hr-tool-dlp-redact",
        )
        self.assertEqual(plan[0]["tool_profile"], "hr-tool-dlp")

    def test_phase11_load_mix_is_exact_and_covers_every_scenario_lane(self) -> None:
        args = types.SimpleNamespace(
            seed=42,
            traffic_profile="attack",
            duration=150,
            rate=6.0,
            tool_profile="",
            model="",
            mcp_path="",
            max_tool_rounds=0,
            frontend_profile="",
            passthrough_percent=80.0,
            passthrough_output_words=1200,
        )
        scenario_ids = [
            "fortistore-injection",
            "hr-tool-dlp",
            "resume-tool-injection",
        ]
        profiles = {
            scenario_id: {
                "id": scenario_id,
                "clean_prompts": [f"clean {scenario_id}"],
                "attack_prompts": [f"attack {scenario_id}"],
                "mcp": {"enabled": False, "tool_profile": ""},
            }
            for scenario_id in scenario_ids
        }
        path_configs = {
            scenario_id: [
                {
                    "action": "alert",
                    "provider": "faig-static",
                    "route": f"{scenario_id}-alert",
                    "model": scenario_id,
                    "mcp_enabled": False,
                    "mcp_path": "direct",
                    "tool_profile": "",
                    "max_tool_rounds": 3,
                    "frontend_instruction_profile": "none",
                }
            ]
            for scenario_id in scenario_ids
        }

        plan = traffic_generator.build_plan(
            args,
            profiles,
            path_configs_by_scenario=path_configs,
            passthrough_config=self.passthrough_config(),
        )

        self.assertEqual(len(plan), 15)
        self.assertEqual(Counter(item["route"] for item in plan), {"passthrough": 12, "alert": 3})
        self.assertEqual(
            {item["scenario"] for item in plan if item["route"] == "alert"},
            set(scenario_ids),
        )
        passthrough_items = [item for item in plan if item["route"] == "passthrough"]
        self.assertTrue(all(item["path_config"]["model"] == "pass-model" for item in passthrough_items))
        self.assertTrue(all(item["path_config"]["mcp_enabled"] is False for item in passthrough_items))
        self.assertTrue(all("1200 words" in item["prompt"] for item in passthrough_items))

    def test_phase11_load_mix_rejects_too_few_requests_for_lane_coverage(self) -> None:
        args = types.SimpleNamespace(
            seed=42,
            traffic_profile="attack",
            duration=60,
            rate=6.0,
            tool_profile="",
            model="",
            mcp_path="",
            max_tool_rounds=0,
            frontend_profile="",
            passthrough_percent=80.0,
            passthrough_output_words=1200,
        )
        profiles = {
            scenario_id: {
                "id": scenario_id,
                "clean_prompts": [],
                "attack_prompts": [f"attack {scenario_id}"],
                "mcp": {"enabled": False, "tool_profile": ""},
            }
            for scenario_id in traffic_generator.BASELINE_SCENARIOS
        }
        path_configs = {
            scenario_id: [
                {
                    "action": "alert",
                    "provider": "faig-static",
                    "route": f"{scenario_id}-alert",
                    "model": scenario_id,
                    "mcp_enabled": False,
                    "mcp_path": "direct",
                    "tool_profile": "",
                    "max_tool_rounds": 3,
                    "frontend_instruction_profile": "none",
                }
            ]
            for scenario_id in profiles
        }

        with self.assertRaisesRegex(SystemExit, "leaves 1 scenario requests for 3"):
            traffic_generator.build_plan(
                args,
                profiles,
                path_configs_by_scenario=path_configs,
                passthrough_config=self.passthrough_config(),
            )

    def test_baseline_family_is_the_three_current_scenarios(self) -> None:
        args = types.SimpleNamespace(scenario=None, scenario_family="baseline")
        installed = {
            **{scenario_id: {} for scenario_id in traffic_generator.BASELINE_SCENARIOS},
            "fortigate-operator": {},
        }
        self.assertEqual(
            traffic_generator.selected_installed_scenarios(args, installed),
            traffic_generator.BASELINE_SCENARIOS,
        )

    def test_action_expectations_validate_deny_redact_and_resume_trace(self) -> None:
        base_item = {
            "scenario": "hr-tool-dlp",
            "prompt_kind": "attack",
            "path_config": {"action": "deny"},
        }
        blocked_result = {
            "status": "ok",
            "security_disposition": "blocked",
            "tool_names": ["employee_table_with_cc"],
        }
        self.assertEqual(scenario_validation.expected_result(base_item), "blocked")
        self.assertTrue(
            scenario_validation.result_matches_expected("blocked", base_item, blocked_result)
        )

        redact_item = {
            **base_item,
            "path_config": {"action": "redact"},
        }
        redacted_result = {
            **blocked_result,
            "scenario_verdict": "redacted",
        }
        self.assertEqual(scenario_validation.expected_result(redact_item), "redacted")
        self.assertTrue(
            scenario_validation.result_matches_expected("redacted", redact_item, redacted_result)
        )

        resume_deny_item = {
            **base_item,
            "scenario": "resume-tool-injection",
        }
        self.assertFalse(
            scenario_validation.result_matches_expected(
                "blocked",
                resume_deny_item,
                {**blocked_result, "tool_names": ["cloud_bucket_list_demo"]},
            )
        )

    def test_path_results_report_expected_over_total_for_each_provider_route(self) -> None:
        events = [
            {
                "provider_route": "hr-tool-dlp-deny",
                "scenario_id": "hr-tool-dlp",
                "expected_result": "blocked",
                "actual_result": "blocked",
                "result_matches_expected": True,
            },
            {
                "provider_route": "hr-tool-dlp-deny",
                "scenario_id": "hr-tool-dlp",
                "expected_result": "blocked",
                "actual_result": "no-sensitive-output",
                "result_matches_expected": False,
            },
            {
                "provider_route": "hr-tool-dlp-redact",
                "scenario_id": "hr-tool-dlp",
                "expected_result": "redacted",
                "actual_result": "redacted",
                "result_matches_expected": True,
            },
        ]
        rows = statistics.path_result_rows(events)
        self.assertEqual(rows["hr-tool-dlp-deny"]["expected_results"], 1)
        self.assertEqual(rows["hr-tool-dlp-deny"]["total_results"], 2)
        self.assertEqual(rows["hr-tool-dlp-redact"]["expected_results"], 1)
        self.assertEqual(rows["hr-tool-dlp-redact"]["total_results"], 1)


if __name__ == "__main__":
    unittest.main()
