"""Instructor student password file (Change 2026-11-23, owner decision)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY = REPO_ROOT / "chatbot" / "https-gateway" / "chart" / "files"
sys.path.insert(0, str(GATEWAY))
import lab_broker  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParseTests(unittest.TestCase):
    def test_three_formats_with_comments(self):
        self.assertEqual(lab_broker.parse_student_password_file("# class of Nov\n\nshared:  Lab_Pass_2026 \n"),
                         {"kind": "shared", "value": "Lab_Pass_2026"})
        self.assertEqual(lab_broker.parse_student_password_file("BASE: Lab_2026_"), {"kind": "base", "value": "Lab_2026_"})
        listed = lab_broker.parse_student_password_file("student01: One_Pass_11\nstudent12: Twelve:Pass_12\n")
        self.assertEqual(listed, {"kind": "list", "passwords": {"student01": "One_Pass_11", "student12": "Twelve:Pass_12"}})

    def test_values_resolve_per_student(self):
        self.assertEqual(lab_broker.password_from_file({"kind": "shared", "value": "S"}, 7), "S")
        self.assertEqual(lab_broker.password_from_file({"kind": "base", "value": "Lab_"}, 7), "Lab_07")
        listed = {"kind": "list", "passwords": {"student03": "Three"}}
        self.assertEqual(lab_broker.password_from_file(listed, 3), "Three")
        self.assertIsNone(lab_broker.password_from_file(listed, 4))

    def test_rejects_bad_files_without_echoing_values(self):
        cases = {
            "shared: A_Secret_1\nbase: B_Secret_": "exactly one of",
            "shared: A_Secret_1\nshared: A_Secret_2": "exactly one of",
            "student01: A_Secret_1\nstudent01: A_Secret_2": "more than once",
            "password A_Secret_1": "expected 'key: value'",
            "shared:": "expected 'key: value'",
            "teacher: A_Secret_1": "unknown key",
            "student00: A_Secret_1": "unknown key",
            "student100: A_Secret_1": "unknown key",
            "shared: " + "x" * 129: "longer than 128",
            "": "exactly one of",
        }
        for text, message in cases.items():
            with self.subTest(text=text[:20]):
                with self.assertRaises(ValueError) as ctx:
                    lab_broker.parse_student_password_file(text)
                self.assertIn(message, str(ctx.exception))
                self.assertNotIn("A_Secret", str(ctx.exception))

    def test_student_password_must_differ_from_static_admin(self):
        for text in ("shared: Admin_Pass_99", "base: Admin_Pass_", "student99: Admin_Pass_99"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as ctx:
                    lab_broker.parse_student_password_file(text, admin_password="Admin_Pass_99")
                self.assertNotIn("Admin_Pass", str(ctx.exception))
        lab_broker.parse_student_password_file("shared: Other_Pass_1", admin_password="Admin_Pass_99")

    def test_summary_has_no_values(self):
        self.assertEqual(lab_broker.student_password_summary({}), {"configured": False})
        listed = {"kind": "list", "passwords": {"student02": "Two", "student01": "One"}}
        self.assertEqual(lab_broker.student_password_summary(listed), {"configured": True, "kind": "list", "students": [1, 2]})
        self.assertNotIn("Lab_", json.dumps(lab_broker.student_password_summary({"kind": "base", "value": "Lab_"})))


class CliTests(unittest.TestCase):
    def run_cli(self, text, admin=None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "students.txt"
            path.write_text(text)
            argv = [sys.executable, str(GATEWAY / "lab_broker.py"), "parse-student-passwords", str(path)]
            if admin is not None:
                (Path(d) / "admin").write_text(admin + "\n")
                argv.append(str(Path(d) / "admin"))
            return subprocess.run(argv, capture_output=True, text=True, cwd=d)

    def test_ok_and_rejected(self):
        ok = self.run_cli("base: Lab_2026_")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["summary"], {"configured": True, "kind": "base"})
        bad = self.run_cli("shared: Same_Pass_1", admin="Same_Pass_1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("must differ", bad.stderr)
        self.assertNotIn("Same_Pass_1", bad.stderr + bad.stdout)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.auth = load("lab_auth_student_file", GATEWAY / "lab_auth.py")

    def resolve(self, policy, request):
        self.auth.load_student_password_policy = lambda: policy
        return self.auth.resolve_file_password(request)

    def test_other_modes_pass_through(self):
        request = {"number": 1, "password": {"mode": "generated"}}
        self.assertEqual(self.resolve({}, request), (request, []))

    def test_file_mode_becomes_an_explicit_password(self):
        out, notes = self.resolve({"kind": "base", "value": "Lab_"}, {"number": 4, "password": {"mode": "file"}})
        self.assertEqual((out["password"], notes), ({"mode": "shared", "value": "Lab_04"}, []))

    def test_unlisted_student_gets_generated_with_a_note(self):
        out, notes = self.resolve({"kind": "list", "passwords": {"student01": "One"}},
                                  {"number": 2, "password": {"mode": "file"}})
        self.assertEqual(out["password"], {"mode": "generated"})
        self.assertIn("student02 has no line", notes[0])

    def test_not_configured_and_bad_number(self):
        with self.assertRaises(LookupError):
            self.resolve({}, {"number": 1, "password": {"mode": "file"}})
        with self.assertRaises(ValueError):
            self.resolve({"kind": "shared", "value": "S"}, {"number": 0, "password": {"mode": "file"}})


class LabManagementTests(unittest.TestCase):
    def setUp(self):
        self.lm = load("lab_management_student_file",
                       REPO_ROOT / "chatbot" / "lab-management" / "chart" / "files" / "lab_management.py")
        self.dir = tempfile.TemporaryDirectory()
        self.db = self.lm.connect(self.dir.name + "/t.sqlite3")
        self.lm.select(self.db, ["hr-tool-dlp"], {"hr-tool-dlp"})

    def tearDown(self):
        self.db.close()
        self.dir.cleanup()

    def test_file_mode_jobs_are_accepted_and_send_no_value(self):
        self.lm.create_job(self.db, "students", "a", {"count": 1, "start_index": 1, "prepopulate": False,
                                                     "password_mode": "file"})
        self.lm.create_job(self.db, "password", "a", {"number": 1, "password_mode": "file"})
        sent = []
        original = self.lm.catalog_providers
        self.lm.catalog_providers = lambda view, scenarios: ["litellm-direct"]
        try:
            self.lm.run_students_job(lambda body: sent.append(body) or {"verified": True, "projects": {}}, {},
                                     {"scenarios": ["hr-tool-dlp"], "password_mode": "file", "start_index": 1, "count": 2},
                                     "ignored-typed-value", lambda line: None)
        finally:
            self.lm.catalog_providers = original
        self.assertEqual([b["password"] for b in sent], [{"mode": "file"}, {"mode": "file"}])


if __name__ == "__main__":
    unittest.main()
