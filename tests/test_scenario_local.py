from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import scenario_local  # noqa: E402


class LocalScenarioStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temporary_directory.name)
        self.repo_root = self.test_root / "repo"
        self.source_package = self.repo_root / "chatbot" / "scenarios" / "examples" / "test-scenario"
        self.local_root = self.repo_root / "chatbot" / "scenarios" / "local"
        self.raw_output_root = self.repo_root / "docs" / "raw-output" / "scenario-work-orders"
        self.source_package.mkdir(parents=True)
        self.source_profile = self.source_package / "profile.json"
        self.source_profile.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "id": "test-scenario",
                    "instruction_file": "instructions.txt",
                    "mcp": {
                        "enabled": False,
                        "default_transport": "direct",
                        "default_tool_set": "scenario",
                        "tool_profile": "",
                        "required_tools": [],
                        "extended_tool_sets": [],
                        "max_tool_rounds": 3,
                        "data_sources": [],
                    },
                    "matrix": {
                        "llm_target": "llm-default",
                        "entry_points": [
                            {
                                "role": "detect",
                                "display_name": "Detect Only",
                                "guard_template": "detect_only",
                                "expected_behavior": "Allow and log.",
                                "required_for_release": True,
                            },
                            {
                                "role": "protect-input",
                                "display_name": "Protect Input",
                                "guard_template": "protect_input",
                                "expected_behavior": "Protect input.",
                                "required_for_release": True,
                            },
                        ],
                        "frontend_instruction_profiles": [
                            {
                                "id": "none",
                                "display_name": "None",
                                "source_type": "none",
                            }
                        ],
                        "chatbot_profiles": [],
                        "faig_chain": {"enabled": False},
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.source_package / "instructions.txt").write_text(
            "tracked instructions\n",
            encoding="utf-8",
        )
        self.store = scenario_local.LocalScenarioStore(
            repo_root=self.repo_root,
            local_root=self.local_root,
            raw_output_root=self.raw_output_root,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def local_instruction_path(self) -> Path:
        return self.local_root / "test-scenario" / "instructions.txt"

    def test_add_creates_an_editable_copy_and_atomic_state(self) -> None:
        result = self.store.add("test-scenario", self.source_profile, now=100)
        self.assertTrue(result["changed"])
        self.assertEqual(self.local_instruction_path().read_text(encoding="utf-8"), "tracked instructions\n")
        state = self.store.load_state()
        self.assertEqual([entry["scenario_id"] for entry in state["installed_scenarios"]], ["test-scenario"])
        self.assertFalse(any(self.local_root.glob(".installed-scenarios.json.*.tmp")))
        self.assertFalse(any(self.local_root.glob(".scenario-stage-*")))

    def test_add_existing_warns_without_overwriting_local_edits(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        self.local_instruction_path().write_text("local tuning\n", encoding="utf-8")
        result = self.store.add("test-scenario", self.source_profile, now=200)
        self.assertFalse(result["changed"])
        self.assertIn("already installed", result["warning"])
        self.assertEqual(self.local_instruction_path().read_text(encoding="utf-8"), "local tuning\n")

    def test_status_reports_local_edits_and_source_updates_separately(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        self.local_instruction_path().write_text("local tuning\n", encoding="utf-8")
        status = self.store.list_installed()["installed_scenarios"][0]
        self.assertTrue(status["local_modified"])
        self.assertFalse(status["source_update_available"])

        (self.source_package / "instructions.txt").write_text(
            "new tracked instructions\n",
            encoding="utf-8",
        )
        status = self.store.list_installed()["installed_scenarios"][0]
        self.assertTrue(status["local_modified"])
        self.assertTrue(status["source_update_available"])

    def test_update_without_force_never_changes_local_files(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        self.local_instruction_path().write_text("local tuning\n", encoding="utf-8")
        result = self.store.update("test-scenario", self.source_profile, now=200)
        self.assertFalse(result["changed"])
        self.assertIn("update --force", result["warning"])
        self.assertEqual(self.local_instruction_path().read_text(encoding="utf-8"), "local tuning\n")

    def test_forced_update_backs_up_then_replaces_local_package(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        self.local_instruction_path().write_text("local tuning\n", encoding="utf-8")
        (self.source_package / "instructions.txt").write_text(
            "new tracked instructions\n",
            encoding="utf-8",
        )
        result = self.store.update(
            "test-scenario",
            self.source_profile,
            force=True,
            now=200,
        )
        self.assertTrue(result["changed"])
        self.assertEqual(
            self.local_instruction_path().read_text(encoding="utf-8"),
            "new tracked instructions\n",
        )
        backup_path = Path(result["backup_path"])
        self.assertEqual(
            (backup_path / "instructions.txt").read_text(encoding="utf-8"),
            "local tuning\n",
        )
        status = result["status"]
        self.assertFalse(status["local_modified"])
        self.assertFalse(status["source_update_available"])

    def test_remove_is_recoverable_and_records_stale_faig_objects(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        result = self.store.remove("test-scenario", now=200)
        self.assertTrue(result["changed"])
        self.assertFalse((self.local_root / "test-scenario").exists())
        archive_path = Path(result["archive_path"])
        self.assertTrue((archive_path / "profile.json").is_file())
        self.assertEqual(
            [entry["role"] for entry in result["stale_entry_points"]],
            ["detect", "protect-input"],
        )
        state = self.store.load_state()
        self.assertEqual(state["installed_scenarios"], [])
        self.assertEqual(len(state["stale_faig_objects"]), 1)
        self.assertIn("/v1/test-scenario/detect/*", self.store.render_work_order())

    def test_update_records_removed_roles_and_clears_them_if_restored(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        source_profile = json.loads(self.source_profile.read_text(encoding="utf-8"))
        original_entry_points = source_profile["matrix"]["entry_points"]
        source_profile["matrix"]["entry_points"] = [original_entry_points[0]]
        self.source_profile.write_text(
            json.dumps(source_profile, indent=2) + "\n",
            encoding="utf-8",
        )
        self.store.update(
            "test-scenario",
            self.source_profile,
            force=True,
            now=200,
        )
        stale = self.store.load_state()["stale_faig_objects"]
        self.assertEqual(
            [entry["role"] for entry in stale[0]["entry_points"]],
            ["protect-input"],
        )

        source_profile["matrix"]["entry_points"] = original_entry_points
        self.source_profile.write_text(
            json.dumps(source_profile, indent=2) + "\n",
            encoding="utf-8",
        )
        self.store.update(
            "test-scenario",
            self.source_profile,
            force=True,
            now=300,
        )
        self.assertEqual(self.store.load_state()["stale_faig_objects"], [])

    def test_acknowledge_stale_clears_only_the_requested_scenario(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        self.store.remove("test-scenario", now=200)
        result = self.store.acknowledge_stale("test-scenario")
        self.assertTrue(result["changed"])
        self.assertEqual(result["acknowledged"], 1)
        self.assertEqual(self.store.load_state()["stale_faig_objects"], [])

    def test_orphan_local_package_is_reported_and_not_overwritten(self) -> None:
        orphan = self.local_root / "test-scenario"
        orphan.mkdir(parents=True)
        (orphan / "instructions.txt").write_text("unregistered\n", encoding="utf-8")
        self.assertEqual(self.store.list_installed()["orphan_packages"], ["test-scenario"])
        with self.assertRaisesRegex(scenario_local.LocalScenarioError, "not registered"):
            self.store.add("test-scenario", self.source_profile, now=100)
        self.assertEqual((orphan / "instructions.txt").read_text(encoding="utf-8"), "unregistered\n")

    def test_duplicate_installed_state_is_rejected(self) -> None:
        self.local_root.mkdir(parents=True)
        entry = {
            "scenario_id": "test-scenario",
            "installed_at": 100,
            "updated_at": 100,
            "source_profile": str(self.source_profile),
            "source_hash": "abc",
            "installed_hash": "abc",
        }
        self.store.state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "installed_scenarios": [entry, entry],
                    "stale_faig_objects": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(scenario_local.LocalScenarioError, "duplicate IDs"):
            self.store.load_state()

    def test_matrix_preview_uses_scenario_owned_names(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        matrix = self.store.matrix_summary()
        self.assertEqual(matrix["global"]["passthrough_model_alias"], "pass-model")
        scenario = matrix["installed_scenarios"][0]
        self.assertEqual(scenario["model_alias"], "test-scenario")
        self.assertEqual(
            [entry["uri"] for entry in scenario["entry_points"]],
            [
                "/v1/test-scenario/detect",
                "/v1/test-scenario/protect-input",
            ],
        )
        self.assertNotIn("demo-a", json.dumps(matrix))

    def test_work_order_output_requires_force_to_replace(self) -> None:
        self.store.add("test-scenario", self.source_profile, now=100)
        output_path = self.raw_output_root / "work-order.md"
        self.store.write_work_order(output_path)
        self.assertIn("/v1/test-scenario/detect", output_path.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(scenario_local.LocalScenarioError, "already exists"):
            self.store.write_work_order(output_path)
        self.store.write_work_order(output_path, force=True)


if __name__ == "__main__":
    unittest.main()
