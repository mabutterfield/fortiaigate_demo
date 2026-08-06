from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import scenario_matrix  # noqa: E402


def scenario_preview(
    scenario_id: str,
    *,
    mcp_enabled: bool,
    frontend_profile: str = "none",
) -> dict:
    display_name = scenario_id.replace("-", " ").title()
    frontend_profiles = [
        {
            "id": "none",
            "display_name": "No Frontend Instructions",
            "source_type": "none",
        }
    ]
    if frontend_profile != "none":
        frontend_profiles.append(
            {
                "id": frontend_profile,
                "display_name": "Compromised Frontend",
                "source_type": "file",
                "source": "frontend.txt",
            }
        )
    return {
        "scenario_id": scenario_id,
        "display_name": display_name,
        "local_profile": f"chatbot/scenarios/local/{scenario_id}/profile.json",
        "content_hash": f"content-{scenario_id}",
        "source_hash": f"source-{scenario_id}",
        "source_update_available": False,
        "model_alias": scenario_id,
        "llm_target": "llm-default",
        "instruction_profile": {
            "source": "scenario_instruction",
            "position": "append",
            "enabled": True,
        },
        "instruction_file": f"chatbot/scenarios/local/{scenario_id}/instructions.txt",
        "mcp": {
            "enabled": mcp_enabled,
            "default_transport": "direct",
            "default_tool_set": "scenario",
            "required_tools": [f"{scenario_id}_tool"] if mcp_enabled else [],
            "extended_tool_sets": (
                [
                    {
                        "id": "cross-domain",
                        "display_name": "Cross Domain",
                        "tools": ["shared_tool"],
                    }
                ]
                if mcp_enabled
                else []
            ),
            "max_tool_rounds": 5,
        },
        "entry_points": [
            {
                "role": "detect",
                "display_name": "Detect Only",
                "uri": f"/v1/{scenario_id}/detect",
                "route": f"{scenario_id}-detect",
                "suggested_flow_name": f"{scenario_id}-detect",
                "suggested_guard_name": f"{scenario_id}_detect".replace("-", "_"),
                "guard_template": "detect_only",
                "guard_next_hop_model": scenario_id,
                "expected_behavior": "Allow and log.",
                "required_for_release": True,
            }
        ],
        "frontend_instruction_profiles": frontend_profiles,
        "chatbot_profiles": [
            {
                "id": f"{scenario_id}-direct",
                "display_name": f"{display_name} Direct",
                "provider_path": "direct",
                "context_mode": "recent",
                "context_window": 8,
                "frontend_instruction_profile": frontend_profile,
            },
            {
                "id": f"{scenario_id}-detect",
                "display_name": f"{display_name} Detect",
                "provider_path": "faig-static",
                "entry_point_role": "detect",
                "context_mode": "recent",
                "context_window": 8,
                "frontend_instruction_profile": frontend_profile,
            },
        ],
        "faig_chain": {"enabled": False},
    }


class ScenarioMatrixTests(unittest.TestCase):
    def test_empty_matrix_exposes_only_global_simplified_controls(self) -> None:
        matrix = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [], "stale_faig_objects": []}
        )
        self.assertEqual(
            [profile["id"] for profile in matrix["chatbot_simplified_profiles"]],
            ["direct-passthrough", "faig-passthrough"],
        )
        self.assertEqual(
            [model["name"] for model in matrix["litellm_models"]],
            ["pass-model"],
        )

    def test_installed_scenarios_generate_litellm_chatbot_and_faig_objects(self) -> None:
        preview = {
            "installed_scenarios": [
                scenario_preview("fortistore-injection", mcp_enabled=False),
                scenario_preview("hr-tool-dlp", mcp_enabled=True),
            ],
            "stale_faig_objects": [],
        }
        matrix = scenario_matrix.build_scenario_matrix(preview)
        self.assertEqual(
            [model["name"] for model in matrix["litellm_models"]],
            ["fortistore-injection", "hr-tool-dlp", "pass-model"],
        )
        self.assertEqual(
            matrix["litellm_model_instruction_profiles"]["pass-model"],
            "passthrough",
        )
        instruction_profiles = {
            profile["name"]: profile
            for profile in matrix["litellm_instruction_profiles"]
        }
        self.assertEqual(
            instruction_profiles["fortistore-injection"]["position"],
            "append",
        )
        self.assertEqual(
            [
                profile["id"]
                for profile in matrix["chatbot_frontend_instruction_profiles"]
            ],
            ["none"],
        )
        route_names = [route["name"] for route in matrix["chatbot_faig_static_routes"]]
        self.assertIn("fortistore-injection-detect", route_names)
        self.assertIn("hr-tool-dlp-detect", route_names)
        simplified_ids = [
            profile["id"] for profile in matrix["chatbot_simplified_profiles"]
        ]
        self.assertNotIn("direct-passthrough", simplified_ids)
        self.assertNotIn("faig-passthrough", simplified_ids)
        self.assertEqual(len(matrix["faig_work_order"]), 2)
        self.assertNotIn("demo-a", json.dumps(matrix))

    def test_mcp_profiles_distinguish_scenario_extended_and_debug_sets(self) -> None:
        preview = {
            "installed_scenarios": [
                scenario_preview("hr-tool-dlp", mcp_enabled=True),
            ],
            "stale_faig_objects": [],
        }
        matrix = scenario_matrix.build_scenario_matrix(
            preview,
            include_debug_all_server_tools=True,
        )
        profiles = {
            profile["name"]: profile
            for profile in matrix["chatbot_mcp_tool_profiles"]
        }
        self.assertEqual(profiles["hr-tool-dlp"]["kind"], "scenario")
        self.assertEqual(
            profiles["hr-tool-dlp-cross-domain"]["tools"],
            ["hr-tool-dlp_tool", "shared_tool"],
        )
        self.assertEqual(profiles["all-installed"]["tools"], ["hr-tool-dlp_tool"])
        self.assertTrue(profiles["all-server"]["allow_all"])

    def test_fortiweb_mcp_requires_intent_installation_and_endpoint(self) -> None:
        preview = {
            "installed_scenarios": [scenario_preview("hr-tool-dlp", mcp_enabled=True)],
            "stale_faig_objects": [],
        }
        incomplete = scenario_matrix.build_scenario_matrix(
            preview,
            capabilities={"fortiweb_mcp_desired": True},
        )
        self.assertEqual(
            [path["name"] for path in incomplete["chatbot_mcp_paths"]],
            ["direct"],
        )
        self.assertTrue(incomplete["warnings"])

        enabled = scenario_matrix.build_scenario_matrix(
            preview,
            capabilities={
                "fortiweb_mcp_desired": True,
                "fortiweb_installed": True,
                "fortiweb_mcp_base_url": "https://fortiweb.example/mcp",
            },
        )
        self.assertEqual(
            [path["name"] for path in enabled["chatbot_mcp_paths"]],
            ["direct", "fortiweb"],
        )
        self.assertTrue(enabled["capabilities"]["fortiweb_mcp_enabled"])

    def test_matrix_output_is_deterministic_for_scenario_order(self) -> None:
        first = scenario_preview("fortistore-injection", mcp_enabled=False)
        second = scenario_preview("hr-tool-dlp", mcp_enabled=True)
        matrix_a = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [first, second], "stale_faig_objects": []}
        )
        matrix_b = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [second, first], "stale_faig_objects": []}
        )
        self.assertEqual(
            scenario_matrix.canonical_json(matrix_a),
            scenario_matrix.canonical_json(matrix_b),
        )

    def test_duplicate_frontend_profiles_are_rejected(self) -> None:
        first = scenario_preview(
            "fortistore-injection",
            mcp_enabled=False,
            frontend_profile="shared-frontend",
        )
        second = scenario_preview(
            "hr-tool-dlp",
            mcp_enabled=True,
            frontend_profile="shared-frontend",
        )
        with self.assertRaisesRegex(
            scenario_matrix.ScenarioMatrixError,
            "Duplicate frontend instruction profile",
        ):
            scenario_matrix.build_scenario_matrix(
                {"installed_scenarios": [first, second], "stale_faig_objects": []}
            )

    def test_work_order_contains_exact_generated_contract(self) -> None:
        preview = {
            "installed_scenarios": [
                scenario_preview("fortistore-injection", mcp_enabled=False)
            ],
            "stale_faig_objects": [],
        }
        matrix = scenario_matrix.build_scenario_matrix(preview)
        work_order = scenario_matrix.render_work_order(matrix)
        self.assertIn("`/v1/fortistore-injection/detect`", work_order)
        self.assertIn("`fortistore_injection_detect`", work_order)
        self.assertIn("`fortistore-injection`", work_order)


if __name__ == "__main__":
    unittest.main()
