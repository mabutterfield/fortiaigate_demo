"""One-time implicit -> explicit local backend upgrade (Change 2026-11-23, fresh-build finding)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import state_storage  # noqa: E402

TERRAFORM = shutil.which("terraform")
MODULE = 'resource "terraform_data" "marker" {\n  input = terraform.workspace\n}\n'


def tf(cwd, *args, workspace=None):
    env = {k: v for k, v in os.environ.items() if k not in ("TF_WORKSPACE", "TF_DATA_DIR")}
    if workspace:
        env["TF_WORKSPACE"] = workspace
    return subprocess.run([TERRAFORM, f"-chdir={cwd}", *args, "-no-color"], env=env, text=True,
                          capture_output=True, check=False)


@unittest.skipUnless(TERRAFORM, "terraform is not installed")
class LocalBackendUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.module = Path(self.tmp.name) / "aws-ecr"
        self.module.mkdir()
        (self.module / "main.tf").write_text(MODULE)
        (self.module / "versions.tf").write_text("terraform {\n}\n")
        for args, ws in ((("init", "-input=false"), None), (("apply", "-auto-approve", "-input=false"), None),
                         (("workspace", "new", "ohio-802"), None),
                         (("apply", "-auto-approve", "-input=false"), "ohio-802")):
            result = tf(self.module, *args, workspace=ws)
            self.assertEqual(result.returncode, 0, result.stderr)
        # The release adds an empty explicit local backend to an already-initialized module.
        (self.module / "versions.tf").write_text('terraform {\n  backend "local" {}\n}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_upgrade_keeps_every_workspace_and_is_idempotent(self):
        before = state_storage._local_state_identities(self.module)
        self.assertEqual(set(before), {"default", "ohio-802"})
        self.assertNotEqual(tf(self.module, "output", workspace="ohio-802").returncode, 0)
        self.assertNotEqual(tf(self.module, "init", "-input=false").returncode, 0)

        backups = Path(self.tmp.name) / 'backups'
        self.assertTrue(state_storage.upgrade_implicit_local_backend(self.module, TERRAFORM, backup_root=backups))
        saved = list(backups.iterdir())
        self.assertEqual(len(saved), 1)
        for workspace, identity in before.items():
            snapshot = saved[0] / workspace / 'terraform.tfstate'
            self.assertEqual(state_storage.checked_state_identity(snapshot), identity)
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
        self.assertEqual(state_storage._local_state_identities(self.module), before)
        for ws in (None, "ohio-802"):
            plan = tf(self.module, "plan", "-detailed-exitcode", "-input=false", workspace=ws)
            self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        self.assertEqual(tf(self.module, "init", "-input=false").returncode, 0)
        self.assertFalse(state_storage.upgrade_implicit_local_backend(self.module, TERRAFORM))

    def test_moved_state_sentinel_stops(self):
        (self.module / "terraform.tfstate").write_text(state_storage.MOVED_SENTINEL)
        with self.assertRaises(ValueError):
            state_storage.upgrade_implicit_local_backend(self.module, TERRAFORM)

    def test_failed_upgrade_keeps_verified_private_backups(self):
        before = state_storage._local_state_identities(self.module)
        backups = Path(self.tmp.name) / 'backups'
        with mock.patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(ValueError, 'Pre-upgrade backup'):
                state_storage.upgrade_implicit_local_backend(self.module, TERRAFORM, backup_root=backups)
        saved = list(backups.iterdir())
        self.assertEqual(len(saved), 1)
        for workspace, identity in before.items():
            self.assertEqual(state_storage.checked_state_identity(saved[0] / workspace / 'terraform.tfstate'), identity)

    def test_module_without_empty_local_backend_is_left_alone(self):
        (self.module / "versions.tf").write_text("terraform {\n}\n")
        self.assertFalse(state_storage.upgrade_implicit_local_backend(self.module, TERRAFORM))


if __name__ == "__main__":
    unittest.main()
