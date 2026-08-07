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
    default_tool_set: str = "scenario",
    default_transport: str = "direct",
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
            "default_transport": default_transport,
            "default_tool_set": default_tool_set,
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
                "action": "alert",
                "display_name": "Alert",
                "uri": f"/v1/{scenario_id}/alert",
                "route": f"{scenario_id}-alert",
                "suggested_flow_name": f"{scenario_id}-alert",
                "suggested_guard_name": f"{scenario_id}_alert",
                "guard_template": "detect_only",
                "guard_next_hop_model": scenario_id,
                "expected_behavior": "Allow and log.",
                "required_for_release": True,
            }
        ],
        "frontend_instruction_profiles": frontend_profiles,
        "chatbot_profiles": [
            {
                "id": f"{scenario_id}-llm-direct",
                "display_name": f"{display_name} - LLM Direct",
                "provider_path": "direct",
                "context_mode": "recent",
                "context_window": 8,
                "frontend_instruction_profile": frontend_profile,
            },
            {
                "id": f"{scenario_id}-alert",
                "display_name": f"{display_name} Alert",
                "provider_path": "faig-static",
                "entry_point_action": "alert",
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
            {"installed_scenarios": []}
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
        self.assertIn("fortistore-injection-alert", route_names)
        self.assertIn("hr-tool-dlp-alert", route_names)
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
        self.assertEqual(
            profiles["all-installed"]["tools"],
            ["hr-tool-dlp_tool", "shared_tool"],
        )
        self.assertTrue(profiles["all-server"]["allow_all"])

    def test_default_and_per_profile_extended_tool_sets_are_resolved(self) -> None:
        scenario = scenario_preview(
            "resume-tool-injection",
            mcp_enabled=True,
            default_tool_set="cross-domain",
        )
        scenario["chatbot_profiles"][1]["mcp_tool_set"] = "scenario"
        matrix = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [scenario]}
        )
        simplified = {
            profile["id"]: profile
            for profile in matrix["chatbot_simplified_profiles"]
        }
        self.assertEqual(
            simplified["resume-tool-injection-llm-direct"]["mcp_tool_profile"],
            "resume-tool-injection-cross-domain",
        )
        self.assertEqual(
            simplified["resume-tool-injection-alert"]["mcp_tool_profile"],
            "resume-tool-injection",
        )
        self.assertEqual(
            matrix["chatbot_advanced_controls"]["default_mcp_tool_profile"],
            "resume-tool-injection-cross-domain",
        )

    def test_fortiweb_mcp_requires_intent_installation_and_endpoint(self) -> None:
        preview = {
            "installed_scenarios": [scenario_preview("hr-tool-dlp", mcp_enabled=True)],
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

    def test_fortiweb_is_preferred_and_direct_is_deterministic_fallback(self) -> None:
        scenario = scenario_preview(
            "hr-tool-dlp",
            mcp_enabled=True,
            default_transport="fortiweb",
        )
        fallback = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [scenario]}
        )
        self.assertEqual(fallback["chatbot_advanced_controls"]["default_mcp_path"], "direct")
        self.assertEqual(
            {profile["mcp_path"] for profile in fallback["chatbot_simplified_profiles"]},
            {"direct"},
        )
        self.assertTrue(any("FortiWeb MCP was requested" in warning for warning in fallback["warnings"]))

        enabled = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [scenario]},
            capabilities={
                "fortiweb_installed": True,
                "fortiweb_mcp_base_url": "http://fortiweb.example:30084",
            },
        )
        self.assertEqual(enabled["chatbot_advanced_controls"]["default_mcp_path"], "fortiweb")
        self.assertEqual(
            {profile["mcp_path"] for profile in enabled["chatbot_simplified_profiles"]},
            {"fortiweb"},
        )

    def test_opted_in_faig_chain_generates_loop_safe_topology(self) -> None:
        scenario = scenario_preview("fortistore-injection", mcp_enabled=False)
        scenario["faig_chain"]["enabled"] = True
        matrix = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [scenario]}
        )
        self.assertTrue(matrix["capabilities"]["faig_chain_available"])
        self.assertIn(
            "faig-chain-reentry",
            [target["name"] for target in matrix["llm_targets"]],
        )
        self.assertIn(
            "fortistore-injection-faig-chain",
            [model["name"] for model in matrix["litellm_models"]],
        )
        self.assertEqual(
            matrix["faig_work_order"][0]["guard_next_hop_model"],
            "fortistore-injection-faig-chain",
        )
        self.assertEqual(matrix["faig_chains"][0]["reentry_uri"], "/v1/passthrough")
        self.assertEqual(matrix["faig_chains"][0]["downstream_model"], "pass-model")

    def test_faig_chain_rejects_disabled_capability_and_non_passthrough_reentry(self) -> None:
        scenario = scenario_preview("fortistore-injection", mcp_enabled=False)
        scenario["faig_chain"]["enabled"] = True
        with self.assertRaisesRegex(scenario_matrix.ScenarioMatrixError, "capability is disabled"):
            scenario_matrix.build_scenario_matrix(
                {"installed_scenarios": [scenario]},
                capabilities={"faig_chain_available": False},
            )
        with self.assertRaisesRegex(scenario_matrix.ScenarioMatrixError, "must re-enter"):
            scenario_matrix.build_scenario_matrix(
                {"installed_scenarios": [scenario]},
                capabilities={"faig_chain_reentry_uri": "/v1/fortistore-injection/alert"},
            )

    def test_matrix_output_is_deterministic_for_scenario_order(self) -> None:
        first = scenario_preview("fortistore-injection", mcp_enabled=False)
        second = scenario_preview("hr-tool-dlp", mcp_enabled=True)
        matrix_a = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [first, second]}
        )
        matrix_b = scenario_matrix.build_scenario_matrix(
            {"installed_scenarios": [second, first]}
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
                {"installed_scenarios": [first, second]}
            )

    def test_work_order_contains_exact_generated_contract(self) -> None:
        preview = {
            "installed_scenarios": [
                scenario_preview("fortistore-injection", mcp_enabled=False)
            ],
        }
        matrix = scenario_matrix.build_scenario_matrix(preview)
        work_order = scenario_matrix.render_work_order(matrix)
        self.assertIn("`/v1/fortistore-injection/alert/*`", work_order)
        self.assertIn("`fortistore-injection_alert`", work_order)
        self.assertIn("`fortistore-injection`", work_order)


if __name__ == "__main__":
    unittest.main()
