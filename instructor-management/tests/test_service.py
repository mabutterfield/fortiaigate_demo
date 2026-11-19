import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('instructor_service', Path(__file__).resolve().parents[1] / 'service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'journal.sqlite')
        self.db = service.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_catalog_uses_profiles_and_instructions(self):
        entries = service.catalog()
        self.assertEqual({e['id'] for e in entries}, {'fortistore-injection', 'hr-tool-dlp', 'resume-tool-injection'})
        resume = next(e for e in entries if e['id'] == 'resume-tool-injection')
        self.assertTrue(resume['instruction'])
        self.assertTrue(resume['sample_prompts']['attack'])
        self.assertTrue(resume['tests'])
        self.assertIn('document_read', resume['tools'])

    def test_selection_is_transactional_and_survives_restart(self):
        service.select(self.db, ['hr-tool-dlp'], {'hr-tool-dlp'})
        with self.assertRaises(ValueError):
            service.select(self.db, ['bad'], {'hr-tool-dlp'})
        self.db.close()
        self.db = service.connect(self.path)
        self.assertEqual(self.db.execute('SELECT id FROM selection').fetchall(), [('hr-tool-dlp',)])

    def test_jobs_blocked_and_no_arbitrary_secret_fields(self):
        service.select(self.db, ['hr-tool-dlp'], {'hr-tool-dlp'})
        job = service.create_job(self.db, 'students', 'teacher@example.org', {'count': 2, 'start_index': 1, 'prepopulate': True})
        status, request = self.db.execute('SELECT status, request FROM jobs WHERE id=?', (job,)).fetchone()
        self.assertEqual(status, 'blocked')
        self.assertEqual(json.loads(request)['scenarios'], ['hr-tool-dlp'])
        with self.assertRaises(ValueError):
            service.create_job(self.db, 'students', 'teacher@example.org', {'count': 2, 'start_index': 1, 'prepopulate': True, 'password': 'secret'})
        self.assertNotIn('secret', str(self.db.execute('SELECT * FROM jobs').fetchall()))

    def test_student_and_missing_identity_denied_without_gateway(self):
        with patch.object(service, 'AUTH_URL', 'http://gateway'):
            self.assertFalse(service.authorize({'X-Lab-Role': 'student'}))
            self.assertFalse(service.authorize({'X-Lab-Role': 'admin'}))

    def test_live_gateway_failure_denies_admin(self):
        headers = {'X-Lab-Role':'admin', 'X-Lab-User':'a', 'X-Lab-Ts':'1', 'X-Lab-Signature':'fake'}
        with patch.object(service, 'AUTH_URL', 'http://gateway'), patch('urllib.request.build_opener', side_effect=OSError('offline')):
            self.assertFalse(service.authorize(headers))


if __name__ == '__main__':
    unittest.main()
