"""8.0.2 catalog transport does not depend on legacy scenario state."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from functional_test import catalog_transport as transport
from functional_test import catalog_baseline


class CatalogTransportTests(unittest.TestCase):
    def test_tls_exception_only_defaults_for_the_lab_service(self):
        required = ['--scenario', 's', '--action', 'alert', '--key-file', 'key',
                    '--admin-credentials', 'admin', '--inventory', 'inventory', '--faig-url', 'https://example.test']
        self.assertFalse(catalog_baseline.parse_args(required).internal_verify_tls)
        self.assertTrue(catalog_baseline.parse_args(required + ['--internal-verify-tls']).internal_verify_tls)
        self.assertTrue(catalog_baseline.parse_args(required + ['--faig-internal-url', 'https://other.test']).internal_verify_tls)

    def test_reads_inventory_and_constructs_ssh_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inventory'
            path.write_text('[fortiaigate]\nfaig-aws ansible_host=192.0.2.12 ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/lab\n')
            host = transport.parse_inventory(path, 'faig-aws')
            self.assertEqual(host['ansible_host'], '192.0.2.12')
            self.assertEqual(transport.ssh_base(host)[-1], 'ubuntu@192.0.2.12')
            with self.assertRaisesRegex(SystemExit, 'not found'):
                transport.parse_inventory(path, 'missing')

    def test_key_is_supplied_on_stdin_not_remote_command(self):
        args = SimpleNamespace(mcp_namespace='mcp', mcp_deployment='mcp-demo', mcp_container='mcp-standard',
                               faig_internal_url='http://internal/ai/openai/v1', mcp_url='http://mcp/mcp',
                               max_tokens=20, temperature=0, internal_verify_tls=False)
        case = {'model':'pass-model', 'prompt':'hello', 'system_prompt':'', 'tools':[], 'max_rounds':0}
        key = {'secretKey':'synthetic-secret'}
        result = subprocess.CompletedProcess([], 0, '{"reply":"hello"}\n', '')
        with patch('functional_test.catalog_transport.subprocess.run', return_value=result) as run:
            self.assertEqual(transport.run_case(args, {'ansible_host':'host'}, case, key)['reply'], 'hello')
        self.assertNotIn('synthetic-secret', str(run.call_args.args[0]))
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['api_key'], 'synthetic-secret')
        self.assertFalse(json.loads(run.call_args.kwargs['input'])['verify_tls'])

    def test_trusted_internal_certificate_can_be_required(self):
        args = SimpleNamespace(faig_internal_url='https://internal/ai/openai/v1', mcp_url='http://mcp/mcp',
                               max_tokens=20, temperature=0, internal_verify_tls=True)
        case = {'model': 'pass-model', 'prompt': 'hello', 'system_prompt': '', 'tools': [], 'max_rounds': 0}
        with patch.object(transport, 'kubectl_exec', return_value=subprocess.CompletedProcess([], 0, '{"reply":"ok"}', '')) as run:
            transport.run_case(args, {}, case, {'secretKey': 'synthetic'})
        self.assertTrue(json.loads(run.call_args.args[3])['verify_tls'])

    def test_credential_redirects_are_refused(self):
        self.assertIsNone(transport.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))


if __name__ == '__main__':
    unittest.main()
