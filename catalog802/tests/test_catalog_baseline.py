import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from functional_test.catalog_baseline import evidence_from_turn, main, request_count, unavailable_evidence


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

    def test_unavailable_tool_result_cannot_prove_absence(self):
        raw = {'tool_events': [{'tool': 'example', 'result': None}]}
        test = {'expect': {'evidence_present': [], 'evidence_absent': ['sensitive-data-in-tool-result']}}
        self.assertEqual(unavailable_evidence(raw, test, []), ['sensitive-data-in-tool-result'])
        test['expect'] = {'evidence_present': ['sensitive-data-in-tool-result'], 'evidence_absent': []}
        self.assertEqual(unavailable_evidence(raw, test, ['sensitive-data-in-tool-result']), [])

    def test_request_count_for_http_errors_and_unknown_execution(self):
        self.assertEqual(request_count({'error': 'http_error', 'rounds': 0}), 1)
        self.assertEqual(request_count({'rounds': 2}), 3)
        self.assertIsNone(request_count({'error': 'agent_exec_failed'}))
        self.assertIsNone(request_count({'rounds': True}))

    def test_block_message_uses_exact_configured_match(self):
        test = {'attack_tools': []}
        evidence, _ = evidence_from_turn({'reply': 'Request blocked.', 'tool_events': []}, test, block_message='Request blocked.')
        self.assertIn('block-message-in-reply', evidence)
        evidence, _ = evidence_from_turn({'reply': 'I said blocked.', 'tool_events': []}, test, block_message='Request blocked.')
        self.assertNotIn('block-message-in-reply', evidence)

    def test_revoked_key_is_incomplete_with_http_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = root / 'key.json'; key.write_text(json.dumps({'scenario': 'hr-tool-dlp', 'action': 'redact',
                'model': 'hr-tool-dlp', 'secretKey': 'test', 'keyName': 'test-key'})); key.chmod(0o600)
            creds = root / 'admin.json'; creds.write_text(json.dumps({'username': 'test', 'password': 'test'})); creds.chmod(0o600)
            args = ['--scenario', 'hr-tool-dlp', '--action', 'redact', '--key-file', str(key),
                    '--admin-credentials', str(creds), '--inventory', str(root / 'inventory'),
                    '--faig-url', 'https://faig.invalid']
            with patch('functional_test.catalog_baseline.validation.parse_inventory', return_value={}), \
                 patch('functional_test.catalog_baseline.baseline.FaigAdmin') as admin, \
                 patch('functional_test.catalog_baseline.baseline.kubectl_exec') as execute, \
                 patch('functional_test.catalog_baseline.baseline.run_case', return_value={'error': 'http_error', 'http_status': 401, 'rounds': 0}), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                execute.return_value.returncode = 0
                self.assertEqual(main(args), 1)
                result = json.loads(output.getvalue())
                self.assertEqual((result['outcome'], result['http_status'], result['requests_sent']), ('incomplete', 401, 1))
                admin.return_value.get.assert_not_called()

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
