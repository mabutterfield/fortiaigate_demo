"""Quickstart resume fixes: GPU allocation decision and the local LiteLLM key-file sync.

Change 2026-11-20, revised 2026-11-23 after Agent1's review of b04696b.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
GPU_SCRIPT = REPO_ROOT / "ansible/roles/validate_k3s/files/gpu_allocation.py"
SYNC_TASKS = REPO_ROOT / "ansible/roles/litellm/tasks/sync_local_key_file.yml"

spec = importlib.util.spec_from_file_location("gpu_allocation", GPU_SCRIPT)
gpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu)


def node(gpus):
    return {"status": {"allocatable": {"nvidia.com/gpu": str(gpus)}}}


def pod(name, gpus=1, phase="Running", node_name="ip-10-0-0-1", ready=(True,), containers=1):
    spec = {"containers": [{"resources": {"limits": {"nvidia.com/gpu": gpus}}}] + [{}] * (containers - 1)}
    if node_name:
        spec["nodeName"] = node_name
    status = {"phase": phase}
    if ready is not None:
        status["containerStatuses"] = [{"ready": r} for r in ready]
    return {"metadata": {"namespace": "fortiaigate", "name": name}, "spec": spec, "status": status}


class GpuAllocationTests(unittest.TestCase):
    def decide(self, nodes, pods):
        return gpu.summarize({"items": nodes}, {"items": pods})

    def test_free_gpu_runs_the_real_check(self):
        out = self.decide([node(1)], [])
        self.assertEqual((out["decision"], out["used"]), ("run", 0))

    def test_no_gpu_still_runs_so_the_pod_fails_as_before(self):
        self.assertEqual(self.decide([node(0)], [])["decision"], "run")

    def test_occupied_by_ready_running_bound_pod_is_reported_skipped(self):
        out = self.decide([node(1)], [pod("triton")])
        self.assertEqual(out["decision"], "skip")
        self.assertIn("SKIPPED", out["reason"])
        self.assertIn("not a CUDA health check", out["reason"])

    def test_unready_pending_or_unbound_holder_fails(self):
        for holder in (pod("t", ready=(False,)), pod("t", phase="Pending", node_name="", ready=None),
                       pod("t", node_name=""), pod("t", ready=(True,), containers=2), pod("t", ready=())):
            with self.subTest(holder=holder):
                out = self.decide([node(1)], [holder])
                self.assertEqual(out["decision"], "fail")
                self.assertIn("fortiaigate/t", out["reason"])

    def test_finished_pods_do_not_count(self):
        self.assertEqual(self.decide([node(1)], [pod("old", phase="Succeeded")])["decision"], "run")

    def test_requests_only_and_partial_use(self):
        p = pod("t")
        p["spec"]["containers"][0]["resources"] = {"requests": {"nvidia.com/gpu": "1"}}
        self.assertEqual(self.decide([node(2)], [p])["decision"], "run")
        self.assertEqual(self.decide([node(1)], [p])["decision"], "skip")


ANSIBLE = shutil.which("ansible-playbook") or str(Path.home() / ".local/bin/ansible-playbook")


def ansible_available():
    try:
        return subprocess.run([ANSIBLE, '--version'], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
KEY = "sk-unit-test-current-key-1234567890"
ALIAS = "faig-lab-shared"
EXPECTED = json.dumps({"key_alias": ALIAS, "api_key": KEY}, separators=(", ", ": ")) + "\n"


@unittest.skipUnless(ansible_available(), "ansible-playbook missing or its Python interpreter is broken; reinstall Ansible")
class SyncLocalKeyFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        os.chmod(self.dir, 0o700)
        self.file = self.dir / "litellm-shared-key.json"
        self.playbook = self.dir / "play.yml"
        self.playbook.write_text(textwrap.dedent(f"""\
            - hosts: localhost
              connection: local
              gather_facts: false
              vars:
                litellm_shared_virtual_key_local_file: "{self.file}"
                litellm_shared_virtual_key_alias: "{ALIAS}"
                litellm_shared_virtual_key_value: "{KEY}"
              tasks:
                - ansible.builtin.include_tasks: "{SYNC_TASKS}"
                - ansible.builtin.debug:
                    msg: "RESULT={{{{ litellm_shared_key_local_result }}}}"
            """))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_play(self):
        env = dict(os.environ, ANSIBLE_NOCOLOR="1", ANSIBLE_LOCALHOST_WARNING="false",
                   ANSIBLE_INVENTORY_UNPARSED_WARNING="false")
        proc = subprocess.run([ANSIBLE, "-i", "localhost,", str(self.playbook)], capture_output=True, text=True, env=env,
                              cwd=self.dir)  # another test may leave the process in a deleted directory
        self.assertNotIn(KEY, proc.stdout + proc.stderr, "the key must never be printed")
        return proc

    def backups(self):
        return sorted(p.name for p in self.dir.glob("litellm-shared-key.json.stale-*"))

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)

    def test_missing_file_is_written_owner_only(self):
        proc = self.run_play()
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-2000:])
        self.assertEqual(json.loads(self.file.read_text())["api_key"], KEY)
        self.assertEqual(self.mode(self.file), 0o600)
        self.assertIn("RESULT=written (was missing)", proc.stdout)

    def test_matching_file_is_left_alone(self):
        self.run_play()
        proc = self.run_play()
        self.assertIn("RESULT=matches the cluster key", proc.stdout)
        self.assertEqual(self.backups(), [])

    def test_old_key_and_corrupt_json_are_backed_up_then_rewritten(self):
        for old in ('{"key_alias": "faig-lab-shared", "api_key": "sk-old-instance"}\n', '{not json at all'):
            with self.subTest(old=old[:12]):
                for b in self.dir.glob("litellm-shared-key.json.stale-*"):
                    b.unlink()
                self.file.write_text(old)
                os.chmod(self.file, 0o600)
                proc = self.run_play()
                self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-2000:])
                self.assertIn("RESULT=refreshed from the cluster", proc.stdout)
                self.assertEqual(json.loads(self.file.read_text())["api_key"], KEY)
                backups = self.backups()
                self.assertEqual(len(backups), 1)
                self.assertEqual((self.dir / backups[0]).read_text(), old)
                self.assertEqual(self.mode(self.dir / backups[0]), 0o600)

    def test_wrong_mode_is_corrected_without_backup(self):
        self.run_play()
        os.chmod(self.file, 0o644)
        proc = self.run_play()
        self.assertIn("RESULT=mode corrected to 0600", proc.stdout)
        self.assertEqual(self.mode(self.file), 0o600)
        self.assertEqual(self.backups(), [])

    def test_symlink_is_refused_and_target_untouched(self):
        target = self.dir / "elsewhere.json"
        target.write_text("do not touch\n")
        self.file.symlink_to(target)
        proc = self.run_play()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("is a symbolic link", proc.stdout)
        self.assertEqual(target.read_text(), "do not touch\n")
        self.assertTrue(self.file.is_symlink())

    def test_rerun_after_interrupted_write_converges(self):
        # An interrupted run can leave a backup and the old file (the atomic copy never half-writes).
        self.file.write_text('{"api_key": "sk-old"}\n')
        os.chmod(self.file, 0o600)
        (self.dir / "litellm-shared-key.json.stale-20000101T000000Z").write_text('{"api_key": "sk-old"}\n')
        proc = self.run_play()
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-2000:])
        self.assertEqual(json.loads(self.file.read_text())["api_key"], KEY)
        self.assertEqual(len(self.backups()), 2)


if __name__ == "__main__":
    unittest.main()
