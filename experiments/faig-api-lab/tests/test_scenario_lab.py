import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('scenario_lab', ROOT / 'scenario_lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
CATALOG = lab.load_catalog()
TEMPLATE = json.loads((ROOT / 'student-template.json').read_text())
PROVIDER = {'providerId': 'litellm-direct', 'platform': 'custom', 'name': 'litellm-direct'}
MODEL = {'uuid': 'm-1', 'modelId': 'fortistore-injection', 'publicName': 'fortistore-injection'}


class CatalogTests(unittest.TestCase):
    def test_actions_come_from_scenario_profiles(self):
        pairs = {(e['scenario'], e['action']) for e in CATALOG['entries']}
        self.assertEqual(pairs, {('fortistore-injection', 'alert'), ('fortistore-injection', 'deny'),
                                 ('hr-tool-dlp', 'alert'), ('hr-tool-dlp', 'redact'), ('hr-tool-dlp', 'deny'),
                                 ('resume-tool-injection', 'alert'), ('resume-tool-injection', 'deny')})

    def test_partial_selection_and_unknown_values(self):
        chosen = lab.select_entries(CATALOG['entries'], ['fortistore-injection'], ['deny'])
        self.assertEqual([(e['scenario'], e['action']) for e in chosen], [('fortistore-injection', 'deny')])
        with self.assertRaises(ValueError):
            lab.select_entries(CATALOG['entries'], ['missing'], None)

    def test_shared_detectors_are_deduplicated(self):
        entries = lab.select_entries(CATALOG['entries'], None, ['alert'])
        self.assertEqual(lab.needed_detectors(CATALOG, entries),
                         ['owasp-agentic-alert', 'owasp-llm-alert', 'hr-dlp-alert'])
        deny = lab.select_entries(CATALOG['entries'], ['fortistore-injection'], ['deny'])
        self.assertEqual(lab.needed_detectors(CATALOG, deny), [])

    def test_names_are_one_policy_per_key(self):
        entry = {'scenario': 'hr-tool-dlp', 'action': 'redact'}
        self.assertEqual(lab.object_names('student02', entry),
                         {'guardrail': 'student02-hr-tool-dlp-redact-guardrail',
                          'policy': 'student02-hr-tool-dlp-redact-policy', 'key': 'student02-hr-tool-dlp-redact',
                          'project': 'student02_hr-tool-dlp'})


class BodyTests(unittest.TestCase):
    def test_ai_copy_preserves_rules_and_sets_action(self):
        builtin = {'rules': [{'name': 'R', 'description': 'd', 'enabled': True, 'violateIf': ['a', 'b'],
                              'exemptIf': ['x']}]}
        body = lab.ai_copy_body(builtin, 'n', 'desc', 'alert')
        self.assertEqual(body['action'], 'alert')
        self.assertEqual(body['detectorType'], 'ai')
        self.assertEqual([c['description'] for c in body['aiRules'][0]['conditions']], ['a', 'b'])
        self.assertEqual(len(body['rules']), 2)

    def test_dlp_dispositions_and_replacements(self):
        redact = lab.dlp_body('n', 'd', 'redact', ['Date of birth', 'SSN'])
        self.assertEqual([r['replacement'] for r in redact['rules']], ['[REDACTED_DATE_OF_BIRTH]', '[REDACTED_SSN]'])
        block = lab.dlp_body('n', 'd', 'block', ['SSN'])
        self.assertNotIn('replacement', block['rules'][0])
        self.assertEqual(block['managedEngine'], 'dlp')

    def test_policy_direction(self):
        out = lab.policy_body('p', '', 'g', 'output', PROVIDER, MODEL)
        self.assertEqual((out['inputGuardrailIds'], out['outputGuardrailIds']), ([], ['g']))
        inp = lab.policy_body('p', '', 'g', 'input', PROVIDER, MODEL)
        self.assertEqual((inp['inputGuardrailIds'], inp['outputGuardrailIds']), (['g'], []))
        self.assertFalse(inp['providerAccess'][0]['allModels'])
        self.assertNotIn('allKeys', inp['providerAccess'][0])

    def test_key_is_limited_to_one_model_and_policy(self):
        body = lab.key_body('k', 'w', 'p', 'pol', PROVIDER, MODEL)
        self.assertEqual(body['policyIds'], ['pol'])
        self.assertEqual([m['modelId'] for m in body['providerAccess'][0]['models']], ['fortistore-injection'])
        self.assertTrue(body['providerAccess'][0]['allKeys'])
        self.assertIsNone(body['expiresAt'])
        self.assertEqual(set(body['budgetWindows'].values()), {None})

    def test_detector_drift(self):
        desired = lab.dlp_body('n', 'd', 'redact', ['Date of birth', 'SSN', 'Credit/debit card'])
        old = lab.dlp_body('n', 'd', 'redact', ['Date of birth', 'SSN'])
        self.assertIn('Credit/debit card:redact', lab.detector_drift(old, desired))
        self.assertEqual(lab.detector_drift(desired, desired), '')
        ai = {'detectorType': 'ai', 'action': 'alert'}
        self.assertEqual(lab.detector_drift({'action': 'alert'}, ai), '')
        self.assertTrue(lab.detector_drift({'action': 'block'}, ai))

    def test_error_detail_keeps_only_validation_text(self):
        raw = json.dumps({'error': 'bad', 'field': 'x[0]', 'echo': 'secret'}).encode()
        self.assertEqual(lab.error_detail(raw), 'bad field=x[0]')
        self.assertEqual(lab.error_detail(b'<html>'), '')


class FakeClient:
    """Records calls and simulates FAIG draft/pending/active transitions."""

    def __init__(self, store, queue):
        self.store, self.queue, self.calls = store, queue, []

    def call(self, method, path, payload=None):
        self.calls.append((method, path))
        parts = path.split('/')
        if method == 'GET' and path == '/api/v1/me/workspaces':
            return [{'id': 'w', 'workspaceName': 'student02_workspace'}]
        if method == 'GET' and path.endswith('/grantable-providers'):
            return {'providers': [{**PROVIDER, 'models': [MODEL]}]}
        if method == 'GET' and path.endswith('/projects'):
            return [{'id': 'proj', 'name': 'student02_fortistore-injection'}]
        if method == 'GET' and path.endswith('/built-in-detectors'):
            return [{'id': 'owasp-agentic-top-10', 'rules': []}, {'id': 'owasp-llm-top-10-2025', 'rules': []}]
        if method == 'GET' and path == '/api/v1/admin/review-queue':
            return {'items': list(self.queue.values())}
        if method == 'GET' and path == '/api/v1/me/virtual-keys':
            return []
        if method == 'POST' and path == '/api/v1/me/virtual-keys':
            return {'id': 'key-id', 'secretKey': 'faig_test_secret'}
        if method == 'POST' and parts[-1] == 'approve':
            oid = parts[-2]
            self.queue.pop(oid)
            for obj in self.store.values():
                if obj['id'] == oid:
                    obj['status'] = 'active'
            return {}
        if method == 'POST' and parts[-1] == 'submit':
            obj = next(o for o in self.store.values() if o['id'] == parts[-2])
            obj['status'] = 'pending'
            self.queue[obj['id']] = {'id': obj['id'], 'type': obj['kind']}
            return obj
        kind = {'detectors': 'detector', 'guardrails': 'guardrail', 'policies': 'policy'}.get(parts[-1])
        if kind and method == 'GET':
            return [o for o in self.store.values() if o['kind'] == kind]
        if kind and method == 'POST':
            obj = {'id': f'{kind}-{len(self.store)}', 'name': payload['name'], 'status': 'draft', 'kind': kind,
                   'payload': payload}
            self.store[obj['id']] = obj
            return obj
        raise AssertionError(f'unexpected call {method} {path}')


class PrepopulateTests(unittest.TestCase):
    def run_lab(self, entries, store=None):
        store = {} if store is None else store
        queue = {}
        client = FakeClient(store, queue)
        student = {'student': 'student02', 'workspace': 'student02_workspace'}
        with tempfile.TemporaryDirectory() as tmp:
            created = lab.Prepopulate(client, client, student, CATALOG, entries, Path(tmp), out=lambda m: None).run()
            files = sorted(p.name for p in Path(tmp).iterdir())
            secret = json.loads((Path(tmp) / files[0]).read_text()) if files else None
        return created, client, store, files, secret

    def test_alert_and_deny_build_layers_in_order(self):
        entries = lab.select_entries(CATALOG['entries'], ['fortistore-injection'], None)
        created, client, store, files, secret = self.run_lab(entries)
        self.assertEqual(created, ['student02-fortistore-injection-alert', 'student02-fortistore-injection-deny'])
        self.assertTrue(all(o['status'] == 'active' for o in store.values()))
        kinds = [o['kind'] for o in store.values()]
        self.assertEqual(kinds.count('detector'), 2)
        approvals = [p for m, p in client.calls if p.endswith('/approve')]
        self.assertTrue(approvals[0].startswith('/api/v1/admin/detectors/'))
        self.assertTrue(approvals[-1].startswith('/api/v1/admin/policies/'))
        deny_guard = next(o for o in store.values() if o['name'].endswith('-deny-guardrail'))
        self.assertEqual(deny_guard['payload']['detectorIds'], ['owasp-agentic-top-10', 'owasp-llm-top-10-2025'])
        self.assertEqual(secret['basePath'], '/ai/openai/v1')
        self.assertEqual(files, ['student02-fortistore-injection-alert.json', 'student02-fortistore-injection-deny.json'])

    def test_rerun_skips_active_objects(self):
        entries = lab.select_entries(CATALOG['entries'], ['fortistore-injection'], ['deny'])
        store = {}
        self.run_lab(entries, store)
        before = len(store)
        _, client, _, _, _ = self.run_lab(entries, store)
        self.assertEqual(len(store), before)
        self.assertFalse([p for m, p in client.calls if m == 'POST' and p.endswith(('/submit', '/approve'))])

    def test_missing_model_is_skipped(self):
        entries = lab.select_entries(CATALOG['entries'], ['hr-tool-dlp'], None)
        created, client, store, files, _ = self.run_lab(entries)
        self.assertEqual((created, store, files), ([], {}, []))


class AutoApproveTests(unittest.TestCase):
    def test_filters_student_workspaces_and_orders_dependencies(self):
        pattern = lab.student_workspace_pattern(TEMPLATE)
        self.assertTrue(pattern.match('student02_workspace'))
        self.assertTrue(pattern.match('student100_workspace'))
        self.assertFalse(pattern.match('finance_workspace'))
        queue = [{'id': 'p', 'type': 'policy', 'ownerWorkspaceId': 'w'},
                 {'id': 'g', 'type': 'guardrail', 'ownerWorkspaceId': 'w'},
                 {'id': 'o', 'type': 'guardrail', 'ownerWorkspaceId': 'other'},
                 {'id': 'd', 'type': 'detector', 'ownerWorkspaceId': 'w'},
                 {'id': 'x', 'type': 'policy', 'ownerWorkspaceId': 'w', 'changeKind': 'delete'}]
        chosen = lab.approvable(queue, {'w': 'student02_workspace'}, {'detector', 'guardrail', 'policy'})
        self.assertEqual([i['id'] for i in chosen], ['d', 'g', 'p'])
        with_deletes = lab.approvable(queue, {'w': 'x'}, {'policy'}, include_deletes=True)
        self.assertEqual([i['id'] for i in with_deletes], ['p', 'x'])


if __name__ == '__main__':
    unittest.main()
