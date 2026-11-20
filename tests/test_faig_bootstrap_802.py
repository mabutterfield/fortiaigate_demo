import json
from pathlib import Path
import tempfile
import unittest

from scripts import faig_bootstrap_802 as bootstrap

MODEL = {'prices': {'input': '3000', 'output': '8000', 'cache_read': None, 'cache_write': None}}
SETUP = {'email':'admin@fortiai.lab', 'username':'Admin', 'password':'secret', 'organization_name':'Lab'}
KEY = 'sk-demo-123456'


class FakeClient:
    origin = 'https://lab.example'
    csrf = None
    def __init__(self):
        self.calls = []
        self.setup_needed = True
        self.licensed = False
        self.provider = None
        self.fail_upload = False
        self.smoke = None
        self.marker = ''
    def call(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path))
        if path == '/api/v1/setup-status': return {'needs_setup': self.setup_needed}
        if path == '/api/v1/setup': self.setup_needed = False; return {'csrf_token': 'token'}
        if path == '/api/v1/login': return {'csrf_token': 'token'}
        if path == '/api/v1/licenses': return {'licenses': [{'status':'Active'}] if self.licensed else [], 'scanningEnabled': self.licensed}
        if path == '/api/v1/admin/licenses':
            if self.fail_upload: raise OSError('connection lost')
            self.licensed = True
            return [{'status':'Active'}]
        if path == '/api/v1/admin/ai-providers' and method == 'GET': return {'items': [self.provider] if self.provider else []}
        if path == '/api/v1/admin/ai-providers' and method == 'POST':
            self.provider = dict(payload)
            self.provider['models'][0]['uuid'] = 'model-id'
            self.provider['apiKeys'] = [{'id':'one', 'name':'litellm-key', 'enabled':True, 'apiKeyMasked':'sk-******3456'}]
            return self.provider
        if path == '/api/v1/admin/ai-providers/litellm-direct': return self.provider
        if path.endswith('/connectivity-tests'):
            if payload.get('url') != 'http://litellm.litellm.svc.cluster.local:4000/v1': raise AssertionError('missing connectivity URL')
            return {'reachable':True, 'credentialsVerified':True}
        if path == '/api/v1/admin/virtual-keys' and method == 'GET': return [self.smoke] if self.smoke else []
        if path == '/api/v1/admin/virtual-keys' and method == 'POST':
            self.smoke = {'id':'key-id','keyName':payload['keyName'],'secretKey':'test-smoke-key'}
            return self.smoke
        if path.startswith('/api/v1/admin/traffic-logs?'):
            return {'items':[{'uuid':'row-id','keyAlias':'quickstart_pass-model_smoke','timeStamp':9999999999999,'trafficType':'Governed'}]}
        if path == '/api/v1/admin/traffic-logs/row-id':
            return {'uuid':'row-id','keyAlias':'quickstart_pass-model_smoke','prompt':{'original':self.marker},'verdictLabel':'Log'}
        raise AssertionError((method, path))
    def inference(self, key, payload):
        self.marker = payload['messages'][0]['content']
        return {'choices':[{'message':{'content':'Hello'}}]}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root / 'FAIG001.lic').write_text('synthetic')
        self.journal = self.root / 'journal.json'; self.client = FakeClient()
    def run_init(self):
        return bootstrap.initialize(self.client, SETUP, self.root, r'FAIG\d+\.lic', KEY, self.journal, MODEL,
                                    attempts=1, sleep=lambda _: None)
    def test_initialization_and_safe_rerun(self):
        self.assertTrue(self.run_init()['scanning_enabled'])
        self.assertEqual((self.root / '.last-used').read_text(), 'FAIG001.lic\n')
        self.run_init()
        self.assertEqual(self.client.calls.count(('POST','/api/v1/setup')), 1)
        self.assertEqual(self.client.calls.count(('POST','/api/v1/admin/licenses')), 1)
        self.assertEqual(self.client.calls.count(('POST','/api/v1/admin/ai-providers')), 1)

    def test_license_readiness_retries_transient_gateway_errors(self):
        original = self.client.call
        failures = [503, 503]
        def call(method, path, *args, **kwargs):
            if path == '/api/v1/licenses' and failures:
                raise bootstrap.ApiError(method, path, failures.pop())
            return original(method, path, *args, **kwargs)
        self.client.call = call
        result = bootstrap.initialize(self.client, SETUP, self.root, r'FAIG\d+\.lic', KEY,
                                      self.journal, MODEL, attempts=3, sleep=lambda _: None)
        self.assertTrue(result['scanning_enabled'])
        self.assertFalse(failures)
    def test_governed_smoke_key_is_saved_and_reused(self):
        path = self.root / 'smoke.json'
        result = bootstrap.initialize(self.client, SETUP, self.root, r'FAIG\d+\.lic', KEY, self.journal, MODEL,
                                      smoke_key_path=path, attempts=1, sleep=lambda _: None)
        self.assertTrue(result['governed_verified'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        bootstrap.initialize(self.client, SETUP, self.root, r'FAIG\d+\.lic', KEY, self.journal, MODEL,
                             smoke_key_path=path, attempts=1, sleep=lambda _: None)
        self.assertEqual(self.client.calls.count(('POST','/api/v1/admin/virtual-keys')), 1)

    def test_missing_log_is_not_success(self):
        path = self.root / 'smoke.json'
        original = self.client.call
        def call(method, path, *args, **kwargs):
            if path.startswith('/api/v1/admin/traffic-logs?'): return {'items': []}
            return original(method, path, *args, **kwargs)
        self.client.call = call
        with self.assertRaisesRegex(RuntimeError, 'could not be matched'):
            bootstrap.initialize(self.client, SETUP, self.root, r'FAIG\d+\.lic', KEY, self.journal, MODEL,
                                 smoke_key_path=path, attempts=1, sleep=lambda _: None)

    def test_unknown_upload_never_retried(self):
        self.client.fail_upload = True
        with self.assertRaises(OSError): self.run_init()
        self.client.fail_upload = False
        with self.assertRaisesRegex(RuntimeError, 'previous license upload result is unknown'): self.run_init()
        self.assertEqual(self.client.calls.count(('POST','/api/v1/admin/licenses')), 1)
    def test_missing_scanning_fails_closed(self):
        self.client.licensed = True; self.client.setup_needed = False
        original = self.client.call
        def call(method,path,*args,**kwargs):
            if path == '/api/v1/licenses': return {'licenses':[{'status':'Active'}], 'scanningEnabled':False}
            return original(method,path,*args,**kwargs)
        self.client.call = call
        with self.assertRaisesRegex(RuntimeError, 'scanning readiness'): self.run_init()
    def test_unknown_setup_is_not_repeated(self):
        bootstrap.atomic_private_write(self.journal, json.dumps({'setup':'pending'}))
        with self.assertRaisesRegex(RuntimeError, 'setup result previously unknown'): self.run_init()
        self.assertNotIn(('POST','/api/v1/setup'), self.client.calls)
    def test_unknown_provider_creation_is_not_repeated(self):
        self.client.setup_needed = False
        self.client.licensed = True
        bootstrap.atomic_private_write(self.journal, json.dumps({'provider':'pending'}))
        with self.assertRaisesRegex(RuntimeError, 'provider creation result previously unknown'):
            self.run_init()
        self.assertNotIn(('POST','/api/v1/admin/ai-providers'), self.client.calls)

    def test_mismatched_existing_provider_credential_fails_closed(self):
        self.run_init()
        self.client.provider['apiKeys'][0]['apiKeyMasked'] = 'sk-******WRONG'
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            self.run_init()
        self.assertEqual(self.client.calls.count(('POST','/api/v1/admin/ai-providers')), 1)

    def test_unknown_license_status_never_uploads(self):
        original = self.client.call
        def call(method, path, *args, **kwargs):
            if path == '/api/v1/licenses': return {'unexpected': True}
            return original(method, path, *args, **kwargs)
        self.client.call = call
        with self.assertRaisesRegex(RuntimeError, 'license status is unavailable'):
            self.run_init()
        self.assertNotIn(('POST','/api/v1/admin/licenses'), self.client.calls)

    def test_license_pattern_and_marker(self):
        (self.root / 'FGVM002.lic').write_text('synthetic')
        self.assertEqual(bootstrap.select_license(self.root, r'FGVM\d+\.lic')[0].name, 'FGVM002.lic')
        with self.assertRaisesRegex(ValueError, 'invalid FAIG license'): bootstrap.select_license(self.root, '[')


if __name__ == '__main__': unittest.main()
