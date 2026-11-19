import ast
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from catalog802 import loader
from catalog802.mcp_compile import compile_registry
from catalog802.litellm import build_litellm_matrix
from catalog802.vocabulary import ACTIONS, EXECUTIONS, VERDICTS, EVIDENCE, OUTCOMES

ROOT = Path(__file__).resolve().parents[2]


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'catalog802/data', self.root / 'catalog802/data')
        for name in ('chatbot/scenarios/examples/hr-tool-dlp/instructions.txt',
                     'mcp/chart/files/server.py', 'mcp/chart/files/tools.json',
                     'chatbot/scenarios/examples/fortistore-injection/instructions.txt',
                     'chatbot/scenarios/examples/fortistore-injection/frontend-injection.instructions.txt',
                     'chatbot/scenarios/examples/resume-tool-injection/instructions.txt',
                     'mcp/chart/files/documents/documents.json',
                     'mcp/chart/files/documents/resume_alex_morgan.txt',
                     'mcp/chart/files/documents/resume_jordan_lee.txt',
                     'mcp/chart/files/documents/resume_casey_jordan_poisoned.txt'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def tearDown(self):
        self.temp.cleanup()

    def scenario(self):
        return self.root / 'catalog802/data/scenarios/hr-tool-dlp.json'

    def update_scenario(self, mutate):
        path = self.scenario(); data = json.loads(path.read_text()); mutate(data)
        path.write_text(json.dumps(data))

    def test_valid_hr_views_and_hash_exclude_metadata(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        first = loader.build_views(catalog, source_commit='one', generated_at='one')
        later = loader.build_views(catalog, source_commit='two', generated_at='two')
        student = next(x for x in first['student']['items'] if x['id'] == 'hr-tool-dlp')
        self.assertEqual([a['id'] for a in student['actions']], ['alert', 'redact', 'block'])
        self.assertEqual(student['content_hash'], next(x for x in later['student']['items'] if x['id'] == 'hr-tool-dlp')['content_hash'])
        self.assertNotIn('instruction', student['models'][0])
        self.assertEqual(next(x for x in first['faig']['items'] if x['id'] == 'hr-tool-dlp')['content_hash'], student['content_hash'])
        self.assertEqual(len(first['mcp']['items']), 10)
        self.assertEqual(first['models']['items'][0]['id'], 'fortistore-injection')
        for view in ('student', 'faig'):
            platform = first[view]['platform']
            self.assertEqual(platform['hello_world']['expect']['verdict'], 'log')
            self.assertEqual(platform['passthrough_model']['id'], 'pass-model')
            self.assertEqual(platform['passthrough_direct_policy_count'], 0)
            self.assertEqual(platform['actions_vocabulary'], ACTIONS)
            self.assertEqual(platform['execution_vocabulary'], EXECUTIONS)
            self.assertEqual(platform['evidence_vocabulary'], EVIDENCE)
            self.assertEqual(platform['outcomes_vocabulary'], OUTCOMES)
            self.assertEqual(platform['verdicts_vocabulary'], VERDICTS)
            self.assertEqual((platform['currency'], platform['unit']), ('USD', 'per_1m_tokens'))
            self.assertEqual(platform['naming']['policy'], '{student}_{scenario}_{action}_policy')
            self.assertEqual(platform['content_hash'], later[view]['platform']['content_hash'])
            self.assertNotIn('instruction', platform['passthrough_model'])

    def test_instruction_and_tool_fixture_change_affect_hash(self):
        cat, _ = loader.load(self.root)
        before = next(x for x in loader.build_views(cat)['student']['items'] if x['id'] == 'hr-tool-dlp')['content_hash']
        path = self.root / 'chatbot/scenarios/examples/hr-tool-dlp/instructions.txt'
        path.write_text(path.read_text() + '\nchanged')
        changed = next(x for x in loader.build_views(cat)['student']['items'] if x['id'] == 'hr-tool-dlp')['content_hash']
        self.assertNotEqual(before, changed)
        path = self.root / 'mcp/chart/files/tools.json'
        path.write_text(path.read_text() + ' ')
        self.assertNotEqual(changed, next(x for x in loader.build_views(cat)['student']['items'] if x['id'] == 'hr-tool-dlp')['content_hash'])

    def test_invalid_references_and_deny_are_rejected(self):
        self.update_scenario(lambda d: d['actions'][0].update(id='deny'))
        _, errors = loader.load(self.root)
        self.assertIn('renamed to block', errors[0])
        self.update_scenario(lambda d: d['actions'][0].update(id='alert', model_ref='missing'))
        self.assertIn('unknown action model', loader.load(self.root)[1][0])
        self.update_scenario(lambda d: d['tools'].append('missing-tool'))
        self.assertIn('unknown tool', loader.load(self.root)[1][0])

    def test_known_failure_requires_all_evidence_and_scope(self):
        issue = {'scope': {'faig_version': ['8.0.2'], 'scenario_version': '1.x'},
                 'when': {'verdict': 'block',
                          'tools_called_include': ['document_upload_simulation'],
                          'missing_required_tools_include': ['document_read']}}
        observed = {'verdict': 'block',
                    'tools_called': ['document_upload_simulation'], 'missing_required_tools': ['document_read']}
        self.assertTrue(loader.known_failure_matches(issue, observed, faig_version='8.0.2', scenario_version='1.0.0', failed=True))
        self.assertFalse(loader.known_failure_matches(issue, observed, faig_version='8.0.2', scenario_version='1.0.0', failed=False))
        self.assertFalse(loader.known_failure_matches(issue, dict(observed, tools_called=[]), faig_version='8.0.2', scenario_version='1.0.0', failed=True))
        self.assertFalse(loader.known_failure_matches(issue, observed, faig_version='8.0.3', scenario_version='1.0.0', failed=True))

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / 'catalog802/data/models.json'
        path.write_text('{"schema_version":1,"schema_version":1,"models":{}}')
        self.assertIn('duplicate JSON key', loader.load(self.root)[1][0])

    def test_duplicate_test_and_tool_ids_are_rejected(self):
        self.update_scenario(lambda d: d['tests'].append(dict(d['tests'][0])))
        self.assertIn('duplicate test ID', loader.load(self.root)[1][0])
        self.update_scenario(lambda d: d['tests'].pop())
        self.update_scenario(lambda d: d['tools'].append(d['tools'][0]))
        self.assertIn('duplicate tool ID', loader.load(self.root)[1][0])

    def test_litellm_uses_all_active_aliases_and_instruction_paths(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        matrix = build_litellm_matrix(catalog)
        self.assertEqual({m['name'] for m in matrix['litellm_models']},
                         {'pass-model', 'fortistore-injection', 'hr-tool-dlp', 'resume-tool-injection'})
        self.assertEqual(matrix['litellm_model_instruction_profiles']['pass-model'], 'passthrough')
        profiles = {p['name']: p for p in matrix['litellm_instruction_profiles']}
        self.assertFalse(profiles['passthrough']['enabled'])
        self.assertTrue(profiles['fortistore-injection']['source_path'].endswith('/instructions.txt'))
        self.assertTrue(profiles['resume-tool-injection']['enabled'])

    def test_litellm_rejects_alias_with_different_targets(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        catalog['models']['another'] = dict(catalog['models']['hr-tool-dlp'], target='different-target')
        with self.assertRaisesRegex(ValueError, 'conflicting target'):
            build_litellm_matrix(catalog)

    def test_mcp_compiler_matches_existing_contracts(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        tree = ast.parse((self.root / 'mcp/chart/files/server.py').read_text())
        legacy = next(ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TOOLS' for t in node.targets))
        existing = {tool['function']['name']: tool for tool in legacy}
        compiled = compile_registry(catalog)
        self.assertEqual(len(compiled), 10)
        for tool in compiled:
            self.assertEqual(tool, existing[tool['function']['name']])
        compiled[0]['function']['description'] = 'changed'
        self.assertNotEqual(compiled[0]['function']['description'], catalog['tools'][compiled[0]['function']['name']]['description'])

    def test_resume_known_issue_and_fixture_hash(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        views = loader.build_views(catalog)
        resume = next(x for x in views['student']['items'] if x['id'] == 'resume-tool-injection')
        block = next(x for x in resume['tests'] if x['action'] == 'block')
        observed = {'verdict': 'block', 'tools_called': ['document_upload_simulation'], 'missing_required_tools': ['document_read']}
        self.assertTrue(loader.known_failure_matches(block['known_issue'], observed, faig_version='8.0.2', scenario_version='1.0.0', failed=True))
        fixture = self.root / 'mcp/chart/files/documents/resume_casey_jordan_poisoned.txt'
        fixture.write_text(fixture.read_text() + '\nchanged')
        later = next(x for x in loader.build_views(catalog)['student']['items'] if x['id'] == resume['id'])
        self.assertNotEqual(resume['content_hash'], later['content_hash'])

    def test_frontend_selection_needs_a_fixture(self):
        self.update_scenario(lambda d: d['tests'][0].update(frontend_instruction='compromised'))
        self.assertIn('invalid or unavailable frontend', loader.load(self.root)[1][0])

    def test_frontend_fixture_is_in_student_view_and_hash(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        first = next(x for x in loader.build_views(catalog)['student']['items'] if x['id'] == 'fortistore-injection')
        self.assertIn('frontend_instruction', first)
        self.assertEqual(first['frontend_instruction_label'], 'Simulate compromised frontend')
        self.assertTrue(all(t.get('frontend_instruction', 'none') == 'none' for t in first['tests']))
        fixture = self.root / 'chatbot/scenarios/examples/fortistore-injection/frontend-injection.instructions.txt'
        fixture.write_text(fixture.read_text() + '\nchanged')
        later = next(x for x in loader.build_views(catalog)['student']['items'] if x['id'] == first['id'])
        self.assertNotEqual(first['content_hash'], later['content_hash'])

    def test_prompt_ids_must_be_unique_and_references_valid(self):
        self.update_scenario(lambda d: d['prompts']['clean'].append(dict(d['prompts']['attack'][0])))
        self.assertIn('IDs unique', loader.load(self.root)[1][0])
        self.update_scenario(lambda d: d['prompts']['clean'].pop())
        self.update_scenario(lambda d: d['tests'][0].update(prompt_ref='attack:0'))
        self.assertIn('invalid prompt reference', loader.load(self.root)[1][0])

    def test_guardrails_compose_reusable_detectors(self):
        catalog, errors = loader.load(self.root)
        self.assertEqual(errors, [])
        guard = next(x for x in loader.build_views(catalog)['faig']['items'] if x['id'] == 'hr-tool-dlp')['actions'][0]['guard']
        self.assertEqual(len(guard['resolved_detectors']), 3)

    def test_retired_evidence_and_expectations_are_rejected(self):
        self.update_scenario(lambda d: d['tests'][0]['expect']['evidence_present'].append('sensitive-tool-result'))
        self.assertIn('renamed to sensitive-data-in-tool-result', loader.load(self.root)[1][0])
        self.update_scenario(lambda d: d['tests'][0]['expect']['evidence_present'].pop())
        self.update_scenario(lambda d: d['tests'][0].update(expected_result='old'))
        self.assertIn('expected_result was renamed to expect', loader.load(self.root)[1][0])

    def test_attack_evidence_requires_declared_attack_tools(self):
        self.update_scenario(lambda d: d['tests'][0]['expect']['evidence_present'].append('attack-tool-called'))
        self.assertIn('requires attack_tools', loader.load(self.root)[1][0])

    def test_unknown_fields_and_unsafe_path_are_rejected(self):
        self.update_scenario(lambda d: d.update(unexpected=True))
        self.assertIn('unknown fields', loader.load(self.root)[1][0])
        index = self.root / 'catalog802/data/index.json'
        index.write_text(json.dumps({'schema_version': 1, 'scenarios': ['../../../../etc/passwd']}))
        self.assertIn('outside catalog root', loader.load(self.root)[1][0])

    def test_conflicting_instructions_for_same_backend_alias_are_rejected(self):
        path = self.root / 'catalog802/data/models.json'
        data = json.loads(path.read_text())
        data['models']['duplicate'] = dict(data['models']['pass-model'], backend_alias='hr-tool-dlp')
        path.write_text(json.dumps(data))
        self.assertIn('conflicting instruction source', loader.load(self.root)[1][0])

    def test_unrecognized_known_issue_predicates_are_rejected(self):
        issue = {'id': 'example', 'summary': 'test', 'scope': {'faig_version': ['8.0.2'], 'scenario_version': '1.x'},
                 'when': {'arbitrary_code': ['not allowed']}}
        self.update_scenario(lambda data: data['tests'][0].update(known_issue=issue))
        self.assertIn('invalid known-issue predicate', loader.load(self.root)[1][0])


if __name__ == '__main__':
    unittest.main()
