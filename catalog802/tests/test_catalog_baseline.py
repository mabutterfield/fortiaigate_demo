import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from functional_test.catalog_baseline import evidence_from_turn, main


class CatalogBaselineTests(unittest.TestCase):
    def test_evidence_is_observation_only(self):
        test = {'attack_tools': ['cloud_bucket_list_demo']}
        raw = {'reply': '[REDACTED_EMAIL_1]', 'tool_events': [
            {'tool': 'cloud_bucket_list_demo', 'result': {'email': 'lab.person@example.com'}}]}
        evidence, tools = evidence_from_turn(raw, test)
        self.assertIn('redaction-marker-in-reply', evidence)
        self.assertIn('sensitive-data-in-tool-result', evidence)
        self.assertIn('attack-tool-called', evidence)
        self.assertNotIn('sensitive-data-in-reply', evidence)
        self.assertEqual(tools, ['cloud_bucket_list_demo'])

    def test_missing_logs_are_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = root / 'key.json'; key.write_text(json.dumps({'scenario': 'hr-tool-dlp', 'action': 'redact',
                'model': 'hr-tool-dlp', 'secretKey': 'test', 'keyName': 'test-key'})); key.chmod(0o600)
            creds = root / 'admin.json'; creds.write_text(json.dumps({'username': 'test', 'password': 'test'})); creds.chmod(0o600)
            args = ['--scenario', 'hr-tool-dlp', '--action', 'redact', '--key-file', str(key),
                    '--admin-credentials', str(creds), '--inventory', str(root / 'inventory'),
                    '--faig-url', 'https://faig.invalid', '--log-wait', '0']
            raw = {'reply': '[REDACTED_SSN_1]', 'rounds': 1,
                   'tool_events': [{'tool': 'employee_sensitive_lookup', 'result': {}}]}
            with patch('functional_test.catalog_baseline.validation.parse_inventory', return_value={}), \
                 patch('functional_test.catalog_baseline.baseline.FaigAdmin') as admin, \
                 patch('functional_test.catalog_baseline.baseline.kubectl_exec') as execute, \
                 patch('functional_test.catalog_baseline.baseline.run_case', return_value=raw), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                execute.return_value.returncode = 0
                admin.return_value.get.return_value = {'items': []}
                self.assertEqual(main(args), 1)
                result = json.loads(output.getvalue())
                self.assertEqual(result['outcome'], 'incomplete')
                self.assertEqual(result['verdict'], 'unknown')


if __name__ == '__main__':
    unittest.main()
