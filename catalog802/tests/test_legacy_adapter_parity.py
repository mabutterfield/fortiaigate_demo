"""Keep transitional scenario-pack inputs aligned until the chatbot switches."""
import json
from pathlib import Path
import unittest

from catalog802.loader import load

ROOT = Path(__file__).resolve().parents[2]


class LegacyAdapterParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, errors = load(ROOT)
        if errors:
            raise AssertionError(errors)

    def test_active_legacy_profiles_match_catalog(self):
        for sid, scenario in self.catalog['scenarios'].items():
            with self.subTest(scenario=sid):
                path = ROOT / 'chatbot/scenarios/examples' / sid / 'profile.json'
                legacy = json.loads(path.read_text())
                self.assertEqual(legacy['display_name'], scenario['display_name'])
                self.assertEqual(legacy['mcp']['required_tools'], scenario['tools'])
                self.assertEqual(legacy['mcp']['extended_tool_sets'], scenario['extended_tool_sets'])
                for group in ('clean', 'attack'):
                    self.assertEqual(legacy[group + '_prompts'], [p['text'] for p in scenario['prompts'][group]])
                expected = {a['id']: a['guard_template_ref'] for a in scenario['actions']}
                actual = {a['action']: a['guard_template'] for a in legacy['matrix']['entry_points']}
                self.assertEqual(actual, expected)
                model = self.catalog['models'][sid]
                self.assertEqual(model['instruction_file'], str(path.parent.relative_to(ROOT) / legacy['instruction_file']))
                catalog_tests = {t['id']: t for t in scenario['tests']}
                for case in legacy['validation']['cases']:
                    item = catalog_tests[case['id']]
                    self.assertEqual(item['action'], case['action'])
                    self.assertEqual(item['required_tools'], case['required_tools'])
                    self.assertEqual(item['forbidden_tools'], case['forbidden_tools'])
                    prompt = scenario['prompts'][case['prompt_kind']][case['prompt_index']]
                    self.assertEqual(item['prompt_ref'], prompt['id'])
    def test_legacy_faig_guard_templates_match_catalog_behavior(self):
        legacy = json.loads((ROOT / 'experiments/faig-api-lab/scenario-catalog.json').read_text())
        shared = self.catalog['platform']
        for name in ('inject_alert', 'inject_block', 'output_dlp_alert', 'output_dlp_redact', 'output_dlp_block'):
            with self.subTest(guard=name):
                old = legacy['guard_templates'][name]
                new = shared['guard_templates'][name]
                self.assertEqual(old.get('direction'), new.get('direction'))
                self.assertEqual(old.get('deny_suspicious_characters'), new.get('deny_suspicious_characters'))
                self.assertEqual(old.get('builtin_detectors', []), new.get('builtin_detectors', []))
                def categories(template, definitions):
                    return {(d['disposition'], category) for ref in template.get('detectors', [])
                            for d in [definitions[ref]] if d.get('kind') == 'dlp'
                            for category in d['categories']}
                self.assertEqual(categories(old, legacy['detectors']), categories(new, shared['detectors']))
                def ai_detectors(template, definitions):
                    return {(d.get('source'), d.get('action')) for ref in template.get('detectors', [])
                            for d in [definitions[ref]] if d.get('kind') == 'ai_copy'}
                self.assertEqual(ai_detectors(old, legacy['detectors']), ai_detectors(new, shared['detectors']))



if __name__ == '__main__':
    unittest.main()
