from __future__ import annotations

import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import user_profile  # noqa: E402


class UserProfileScenarioArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temporary_directory.name)
        self.original_repo_root = user_profile.REPO_ROOT
        self.source_root = self.test_root / "source"
        self.prepare_config(self.source_root, "source")
        user_profile.REPO_ROOT = self.source_root

    def tearDown(self) -> None:
        user_profile.REPO_ROOT = self.original_repo_root
        self.temporary_directory.cleanup()

    def prepare_config(self, root: Path, marker: str) -> None:
        files = {
            "terraform/user.tfvars": f'name_prefix = "{marker}"\n',
            "ansible/group_vars/user.yml": f"profile_marker: {marker}\n",
        }
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def scenario_entry(self, scenario_id: str) -> dict:
        return {
            "scenario_id": scenario_id,
            "installed_at": 100,
            "updated_at": 100,
            "source_profile": f"chatbot/scenarios/examples/{scenario_id}/profile.json",
            "source_hash": f"source-{scenario_id}",
            "installed_hash": f"installed-{scenario_id}",
        }

    def install_scenario(self, root: Path, scenario_id: str, instruction: str) -> None:
        package = root / "chatbot/scenarios/local" / scenario_id
        package.mkdir(parents=True, exist_ok=True)
        (package / "profile.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "id": scenario_id,
                    "display_name": scenario_id.replace("-", " ").title(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (package / "instructions.txt").write_text(instruction, encoding="utf-8")

    def write_state(self, root: Path, scenario_ids: list[str]) -> None:
        state_path = root / user_profile.SCENARIO_STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "installed_scenarios": [
                        self.scenario_entry(scenario_id) for scenario_id in scenario_ids
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def export_source(self, scenario_ids: list[str]) -> Path:
        self.write_state(self.source_root, scenario_ids)
        archive_path = self.test_root / "user-profile.tgz"
        user_profile.export_profile(archive_path)
        return archive_path

    def test_export_includes_registered_packages_and_excludes_history(self) -> None:
        self.install_scenario(
            self.source_root,
            "fortistore-injection",
            "local tuning\n",
        )
        history_paths = [
            self.source_root
            / "chatbot/scenarios/local/_backups/fortistore-injection/old/instructions.txt",
            self.source_root
            / "chatbot/scenarios/local/_removed/retired/old/instructions.txt",
        ]
        for path in history_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("history\n", encoding="utf-8")

        archive_path = self.export_source(["fortistore-injection"])
        with tarfile.open(archive_path, "r:gz") as archive:
            names = set(archive.getnames())

        self.assertIn("chatbot/scenarios/local/installed-scenarios.json", names)
        self.assertIn(
            "chatbot/scenarios/local/fortistore-injection/instructions.txt",
            names,
        )
        self.assertFalse(any("/_backups/" in name for name in names))
        self.assertFalse(any("/_removed/" in name for name in names))

    def test_export_import_round_trip_restores_scenario_state(self) -> None:
        self.install_scenario(self.source_root, "hr-tool-dlp", "tuned HR prompt\n")
        archive_path = self.export_source(["hr-tool-dlp"])

        destination_root = self.test_root / "destination"
        user_profile.REPO_ROOT = destination_root
        user_profile.import_profile(archive_path, yes=True)

        self.assertEqual(
            (
                destination_root
                / "chatbot/scenarios/local/hr-tool-dlp/instructions.txt"
            ).read_text(encoding="utf-8"),
            "tuned HR prompt\n",
        )
        state = json.loads(
            (destination_root / user_profile.SCENARIO_STATE_PATH).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [entry["scenario_id"] for entry in state["installed_scenarios"]],
            ["hr-tool-dlp"],
        )

    def test_import_merges_new_scenarios_and_requires_overwrite_confirmation(self) -> None:
        self.install_scenario(self.source_root, "hr-tool-dlp", "archive prompt\n")
        archive_path = self.export_source(["hr-tool-dlp"])

        destination_root = self.test_root / "destination"
        self.prepare_config(destination_root, "destination")
        self.install_scenario(destination_root, "resume-tool-injection", "resume local\n")
        self.write_state(destination_root, ["resume-tool-injection"])
        user_profile.REPO_ROOT = destination_root
        with mock.patch.object(user_profile, "prompt_yes_no", return_value=False):
            user_profile.import_profile(archive_path, yes=False)
        state = json.loads(
            (destination_root / user_profile.SCENARIO_STATE_PATH).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [entry["scenario_id"] for entry in state["installed_scenarios"]],
            ["hr-tool-dlp", "resume-tool-injection"],
        )

        with mock.patch.object(user_profile, "prompt_yes_no", return_value=False):
            user_profile.import_profile(archive_path, yes=False)
        self.assertEqual(
            (
                destination_root / "chatbot/scenarios/local/hr-tool-dlp/instructions.txt"
            ).read_text(encoding="utf-8"),
            "archive prompt\n",
        )

        self.install_scenario(destination_root, "hr-tool-dlp", "destination tuning\n")
        with mock.patch.object(user_profile, "prompt_yes_no", return_value=False):
            user_profile.import_profile(archive_path, yes=False)
        self.assertEqual(
            (
                destination_root / "chatbot/scenarios/local/hr-tool-dlp/instructions.txt"
            ).read_text(encoding="utf-8"),
            "destination tuning\n",
        )
        user_profile.import_profile(archive_path, yes=True)
        self.assertEqual(
            (
                destination_root / "chatbot/scenarios/local/hr-tool-dlp/instructions.txt"
            ).read_text(encoding="utf-8"),
            "archive prompt\n",
        )

    def malicious_archive(
        self,
        member_name: str,
        *,
        link_target: str = "",
    ) -> Path:
        archive_path = self.test_root / f"malicious-{len(list(self.test_root.glob('malicious-*')))}.tgz"
        manifest = {
            "profile_version": 1,
            "created_at": 100,
            "files": [member_name],
            "installed_scenarios": [],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        with tarfile.open(archive_path, "w:gz") as archive:
            manifest_info = tarfile.TarInfo(user_profile.MANIFEST_PATH)
            manifest_info.size = len(manifest_bytes)
            archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
            member = tarfile.TarInfo(member_name)
            if link_target:
                member.type = tarfile.SYMTYPE
                member.linkname = link_target
                archive.addfile(member)
            else:
                content = b"unexpected\n"
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        return archive_path

    def test_import_rejects_traversal_unexpected_paths_and_links(self) -> None:
        cases = [
            self.malicious_archive("../outside.txt"),
            self.malicious_archive("/absolute.txt"),
            self.malicious_archive("chatbot/scenarios/local/_backups/x/file.txt"),
            self.malicious_archive(
                "chatbot/scenarios/local/unsafe-link/profile.json",
                link_target="../../outside.txt",
            ),
        ]
        for archive_path in cases:
            with self.subTest(archive=archive_path.name):
                with self.assertRaises(SystemExit):
                    user_profile.import_profile(archive_path, yes=True)

    def test_export_rejects_symlinks_inside_scenario_packages(self) -> None:
        self.install_scenario(self.source_root, "hr-tool-dlp", "prompt\n")
        self.write_state(self.source_root, ["hr-tool-dlp"])
        package = self.source_root / "chatbot/scenarios/local/hr-tool-dlp"
        (package / "linked.txt").symlink_to(package / "instructions.txt")
        with self.assertRaises(SystemExit):
            user_profile.export_profile(self.test_root / "unsafe.tgz")


if __name__ == "__main__":
    unittest.main()
