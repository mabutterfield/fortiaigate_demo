from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automated_quickstart as quickstart


class Quickstart802Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user = self.root / "ansible/group_vars/user.yml"
        self.user.parent.mkdir(parents=True)
        self.user.write_text("---\nprivate_value: secret-do-not-print\n")
        self.root_patch = mock.patch.object(quickstart, "REPO_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_explicit_override_does_not_change_saved_choice(self):
        self.user.write_text("quickstart_experimental_faig_init: true\n")
        self.assertFalse(quickstart.select_experimental_init(False, noninteractive=True))
        self.assertIn("true", self.user.read_text())
        self.assertTrue(quickstart.select_experimental_init(None, noninteractive=True))

    def test_interactive_choice_is_saved_and_reused(self):
        with mock.patch.object(quickstart, "prompt_yes_no", return_value=True):
            self.assertTrue(quickstart.select_experimental_init(None, noninteractive=False))
        with mock.patch.object(quickstart, "prompt_yes_no", side_effect=AssertionError("prompted")):
            self.assertTrue(quickstart.select_experimental_init(None, noninteractive=True))
        self.assertIn("private_value: secret-do-not-print", self.user.read_text())

    def test_missing_or_invalid_choice_fails_without_leaking_values(self):
        for value in (None, "maybe"):
            if value:
                self.user.write_text(f"private_value: secret-do-not-print\nquickstart_experimental_faig_init: {value}\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as error:
                quickstart.select_experimental_init(None, noninteractive=True)
            self.assertNotIn("secret-do-not-print", output.getvalue() + str(error.exception))

    def test_yolo_requires_aws_values_without_printing_content(self):
        with self.assertRaises(SystemExit) as error:
            quickstart.validate_yolo_aws_profile('aws_profile = "secret-do-not-print"\n')
        self.assertIn("aws_region", str(error.exception))
        self.assertNotIn("secret-do-not-print", str(error.exception))
        quickstart.validate_yolo_aws_profile('\n'.join(f'{key} = "value"' for key in
            ("aws_profile", "aws_region", "ssh_key_name", "ssh_private_key_file")))

    def test_failed_login_does_not_prompt_in_yolo(self):
        with mock.patch.object(quickstart, "run_command", return_value=mock.Mock(returncode=1)), \
             mock.patch.object(quickstart, "choose_aws_login_method", side_effect=AssertionError("prompted")):
            with self.assertRaisesRegex(SystemExit, "refresh the SSO session"):
                quickstart.ensure_aws_login("test", noninteractive=True)

    def test_guard_stops_both_choices_before_platform_or_experimental_calls(self):
        for choice in (True, False):
            args = Namespace(target="local", auto_approve=False, yolo=True,
                             skip_ansible=False, experimental_faig_init=choice,
                             include_appliances=False, include_fortigate=False,
                             include_fortiweb=False, no_appliances=False,
                             no_fortigate=False, no_fortiweb=False)
            with mock.patch.object(quickstart, "parse_args", return_value=args), \
                 mock.patch.object(quickstart, "check_repo_root"), \
                 mock.patch.object(quickstart, "check_requirements"), \
                 mock.patch.object(quickstart, "ensure_user_profile", return_value="existing"), \
                 mock.patch.object(quickstart, "run_ansible_flow", side_effect=AssertionError("deployed")):
                with self.assertRaisesRegex(SystemExit, "no application calls were made"):
                    quickstart.main()


if __name__ == "__main__":
    unittest.main()
