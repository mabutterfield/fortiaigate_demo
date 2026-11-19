import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('credentials', ROOT / 'credentials.py')
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


class CredentialTests(unittest.TestCase):
    def test_generated_password_is_selectable_and_meets_character_requirements(self):
        for _ in range(50):
            password = credentials.select_password()
            self.assertEqual(len(password), 24)
            self.assertRegex(password, r'^[A-Za-z0-9_]+$')
            for pattern in (r'[A-Z]', r'[a-z]', r'[0-9]', r'_'):
                self.assertRegex(password, pattern)

    def test_student_numbering(self):
        self.assertEqual(credentials.student_email(1), 'student01@fortiai.lab')
        self.assertEqual(credentials.student_email(100), 'student100@fortiai.lab')
        self.assertEqual(credentials.student_email(2, 'example.test'), 'student02@example.test')
        with self.assertRaises(ValueError):
            credentials.student_email(0)

    def test_defined_password_requires_private_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'password'
            path.write_text('Example1!\n')
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'owner-only'):
                credentials.select_password(path)
            path.chmod(0o600)
            self.assertEqual(credentials.select_password(path), 'Example1!')

    def test_admin_outputs_are_private_and_not_overwritten(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            setup, login = Path(tmp) / 'setup', Path(tmp) / 'login'
            command = [sys.executable, str(ROOT / 'prepare_admin.py'), '--setup-output', str(setup), '--login-output', str(login)]
            subprocess.run(command, check=True, capture_output=True)
            first, second = json.loads(setup.read_text()), json.loads(login.read_text())
            self.assertEqual(first['email'], 'admin@fortiai.lab')
            self.assertEqual(second['username'], first['email'])
            self.assertEqual(second['password'], first['password'])
            self.assertEqual(os.stat(setup).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(login).st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(login.read_text()), second)


if __name__ == '__main__':
    unittest.main()
