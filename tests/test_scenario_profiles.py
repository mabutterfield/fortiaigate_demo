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

import scenario_profiles  # noqa: E402


BASELINE_IDS = ["fortistore-injection", "hr-tool-dlp", "resume-tool-injection"]
CANDIDATE_IDS = [
    "fortigate-operator",
]


class ScenarioCatalogLifecycleTests(unittest.TestCase):
    def test_default_selection_contains_only_baseline_scenarios(self) -> None:
        self.assertEqual(scenario_profiles.scenario_ids(), BASELINE_IDS)

    def test_candidate_selection_keeps_future_scenarios_discoverable(self) -> None:
        selected = scenario_profiles.scenario_ids(include_candidates=True)
        self.assertEqual(selected, sorted(BASELINE_IDS + CANDIDATE_IDS))

    def test_catalog_contract_is_valid(self) -> None:
        self.assertEqual(scenario_profiles.catalog_validation_errors(scenario_profiles.catalog()), [])

    def test_candidate_cannot_be_marked_active(self) -> None:
        catalog_data = copy.deepcopy(scenario_profiles.catalog())
        catalog_data["scenarios"]["fortigate-operator"]["active"] = True
        errors = scenario_profiles.catalog_validation_errors(catalog_data)
        self.assertTrue(any("active must be false" in error for error in errors), errors)


class ScenarioProfileSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.available_tools = scenario_profiles.shared_mcp_tool_names()

    def load_baseline(self, scenario_id: str) -> tuple[Path, dict]:
        return scenario_profiles.load_scenario(scenario_id)

    def validate(self, scenario_id: str, profile_path: Path, profile: dict) -> list[str]:
        errors, _symbols = scenario_profiles.baseline_profile_validation(
            scenario_id,
            profile_path,
            profile,
            self.available_tools,
        )
        return errors

    def test_committed_schema_is_draft_2020_12_and_requires_v2(self) -> None:
        schema = json.loads(scenario_profiles.SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], 2)
        self.assertIn("matrix", schema["required"])

    def test_baseline_profiles_satisfy_semantic_validation(self) -> None:
        for scenario_id in BASELINE_IDS:
            with self.subTest(scenario_id=scenario_id):
                profile_path, profile = self.load_baseline(scenario_id)
                self.assertEqual(self.validate(scenario_id, profile_path, profile), [])

    def test_builtin_profile_names_follow_the_chatbot_display_convention(self) -> None:
        expected = {
            "fortistore-injection": [
                "FortiStore Injection - LLM Direct",
                "FortiStore Injection - Baseline",
                "FortiStore Injection - Alert",
                "FortiStore Injection - Deny",
            ],
            "hr-tool-dlp": [
                "HR Tool DLP - LLM Direct",
                "HR Tool DLP - Alert",
                "HR Tool DLP - Redact",
                "HR Tool DLP - Deny",
            ],
            "resume-tool-injection": [
                "Resume Tool Injection - LLM Direct",
                "Resume Tool Injection - Alert",
                "Resume Tool Injection - Deny",
            ],
        }
        for scenario_id, labels in expected.items():
            _profile_path, profile = self.load_baseline(scenario_id)
            self.assertEqual(
                [item["display_name"] for item in profile["matrix"]["chatbot_profiles"]],
                labels,
            )
            self.assertNotIn("chatbot_demo_profiles", profile)

    def test_builtin_mcp_scenarios_prefer_fortiweb_and_chains_default_off(self) -> None:
        for scenario_id in BASELINE_IDS:
            _profile_path, profile = self.load_baseline(scenario_id)
            self.assertFalse(profile["matrix"]["faig_chain"]["enabled"])
            if profile["mcp"]["enabled"]:
                self.assertEqual(profile["mcp"]["default_transport"], "fortiweb")

    def test_local_profile_may_opt_in_to_faig_chain(self) -> None:
        profile_path, profile = self.load_baseline("fortistore-injection")
        profile = copy.deepcopy(profile)
        profile["matrix"]["faig_chain"]["enabled"] = True
        self.assertEqual(self.validate("fortistore-injection", profile_path, profile), [])

    def test_profile_id_must_match_catalog_id(self) -> None:
        profile_path, profile = self.load_baseline("fortistore-injection")
        profile = copy.deepcopy(profile)
        profile["id"] = "different-id"
        errors = self.validate("fortistore-injection", profile_path, profile)
        self.assertIn("profile id must equal the catalog scenario ID", errors)

    def test_unsupported_matrix_fields_are_rejected(self) -> None:
        profile_path, profile = self.load_baseline("fortistore-injection")
        profile = copy.deepcopy(profile)
        profile["matrix"]["scenario_id"] = "fortistore-injection"
        errors = self.validate("fortistore-injection", profile_path, profile)
        self.assertIn("matrix contains unsupported fields: scenario_id", errors)

    def test_alert_action_must_be_unique_and_detect_only(self) -> None:
        profile_path, profile = self.load_baseline("hr-tool-dlp")
        profile = copy.deepcopy(profile)
        profile["matrix"]["entry_points"].append(
            copy.deepcopy(profile["matrix"]["entry_points"][0])
        )
        errors = self.validate("hr-tool-dlp", profile_path, profile)
        self.assertTrue(any("duplicate actions: alert" in error for error in errors), errors)
        self.assertIn("matrix.entry_points must contain exactly one alert action", errors)

    def test_chatbot_profile_references_must_resolve(self) -> None:
        profile_path, profile = self.load_baseline("fortistore-injection")
        profile = copy.deepcopy(profile)
        profile["matrix"]["chatbot_profiles"][0]["frontend_instruction_profile"] = "missing"
        errors = self.validate("fortistore-injection", profile_path, profile)
        self.assertTrue(any("unknown frontend instruction profile" in error for error in errors), errors)

    def test_chatbot_profile_tool_set_must_resolve(self) -> None:
        profile_path, profile = self.load_baseline("hr-tool-dlp")
        profile = copy.deepcopy(profile)
        profile["matrix"]["chatbot_profiles"][0]["mcp_tool_set"] = "missing"
        errors = self.validate("hr-tool-dlp", profile_path, profile)
        self.assertTrue(any("unknown mcp_tool_set" in error for error in errors), errors)

    def test_guard_template_must_match_action(self) -> None:
        profile_path, profile = self.load_baseline("hr-tool-dlp")
        profile = copy.deepcopy(profile)
        deny = next(
            entry
            for entry in profile["matrix"]["entry_points"]
            if entry["action"] == "deny"
        )
        deny["guard_template"] = "output_dlp_redact"
        errors = self.validate("hr-tool-dlp", profile_path, profile)
        self.assertTrue(any("invalid for action deny" in error for error in errors), errors)

    def test_package_file_cannot_escape_scenario_directory(self) -> None:
        profile_path, profile = self.load_baseline("fortistore-injection")
        profile = copy.deepcopy(profile)
        profile["instruction_file"] = "../outside.txt"
        errors = self.validate("fortistore-injection", profile_path, profile)
        self.assertTrue(any("must stay inside the scenario package" in error for error in errors), errors)

    def test_generated_symbol_collisions_are_reported(self) -> None:
        registry = {
            "model_alias": {},
            "route_uri": {},
            "guard_name": {},
            "chatbot_profile": {},
            "frontend_profile": {},
        }
        symbols = {
            "model_alias": ["shared"],
            "route_uri": [],
            "guard_name": [],
            "chatbot_profile": [],
            "frontend_profile": [],
        }
        self.assertEqual(
            scenario_profiles.register_generated_symbols(registry, "scenario-one", symbols),
            [],
        )
        errors = scenario_profiles.register_generated_symbols(registry, "scenario-two", symbols)
        self.assertEqual(
            errors,
            ["generated model_alias shared collides with scenario scenario-one"],
        )


if __name__ == "__main__":
    unittest.main()
