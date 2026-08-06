from __future__ import annotations

import types
import unittest

from scripts import traffic_generator


class TrafficGeneratorMatrixTests(unittest.TestCase):
    def test_path_test_cases_are_derived_from_matrix(self) -> None:
        args = types.SimpleNamespace(
            legacy_routes=False,
            path_test_path=["detect", "passthrough"],
            path_test_passthrough_model="",
            path_test_base_url="https://faig.example",
            endpoint="",
            target="local",
            path_test_execution="direct",
        )
        matrix = {
            "chatbot_faig_static_routes": [
                {
                    "name": "fortistore-injection-detect",
                    "base_path": "/v1/fortistore-injection/detect",
                    "role": "detect",
                    "model": "fortistore-injection",
                },
                {
                    "name": "passthrough",
                    "base_path": "/v1/passthrough",
                    "role": "passthrough",
                    "model": "pass-model",
                },
            ]
        }
        cases = traffic_generator.path_test_cases(args, matrix)
        self.assertEqual(
            [case["path"] for case in cases],
            ["/v1/fortistore-injection/detect", "/v1/passthrough"],
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
            "path_role": "output-dlp-redact",
            "provider": "faig-static",
            "route": "hr-tool-dlp-output-dlp-redact",
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
        self.assertEqual(plan[0]["route"], "output-dlp-redact")
        self.assertEqual(
            plan[0]["path_config"]["route"],
            "hr-tool-dlp-output-dlp-redact",
        )
        self.assertEqual(plan[0]["tool_profile"], "hr-tool-dlp")


if __name__ == "__main__":
    unittest.main()
