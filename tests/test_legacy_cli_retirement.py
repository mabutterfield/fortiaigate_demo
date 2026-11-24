"""Retired 8.0.1 runners must fail clearly before sending traffic."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RetiredCliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, '-m', *args], cwd=ROOT, text=True, capture_output=True)

    def test_old_chatbot_validator_and_pack_are_retired(self):
        for command in ('validate', 'scenario-pack'):
            with self.subTest(command=command):
                result = self.invoke('functional_test', command)
                self.assertEqual(result.returncode, 2)
                self.assertIn('catalog-baseline', result.stderr)

    # Change 2026-11-23: removed legacy executable.
    # def test_load_runner_stops_before_legacy_traffic(self):
    #     for command in ('validate', 'paths', 'run'):
    #         with self.subTest(command=command):
    #             result = self.invoke('load_test', command, '--yes')
    #             self.assertEqual(result.returncode, 2)
    #             self.assertIn('disabled', result.stderr)

    def test_functional_help_still_shows_supported_catalog_command(self):
        result = self.invoke('functional_test', '--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('catalog-baseline', result.stdout)

    # Change 2026-11-23: removed legacy executable.
    # def test_old_scenario_installer_fails_before_writing(self):
    #     result = subprocess.run([sys.executable, 'scripts/scenario_profiles.py', 'add', 'fortistore-injection'],
    #                             cwd=ROOT, text=True, capture_output=True)
    #     self.assertNotEqual(result.returncode, 0)
    #     self.assertIn('retired', result.stderr)


if __name__ == '__main__':
    unittest.main()
