from pathlib import Path
import unittest
from catalog802.loader import load
from functional_test.catalog_plan import plan_case

ROOT = Path(__file__).resolve().parents[2]


class CatalogPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, errors = load(ROOT)
        if errors:
            raise AssertionError(errors)

    def test_plans_each_active_scenario_and_uses_catalog_prompts(self):
        for scenario, action in [('fortistore-injection', 'block'), ('hr-tool-dlp', 'redact'),
                                 ('resume-tool-injection', 'alert')]:
            with self.subTest(scenario=scenario):
                case = plan_case(self.catalog, scenario, action)
                self.assertEqual(case['model'], scenario)
                self.assertTrue(case['prompt'])
                self.assertEqual(case['test']['action'], action)
        resume = plan_case(self.catalog, 'resume-tool-injection', 'alert')
        self.assertIn('cloud_bucket_list_demo', resume['tools'])
        self.assertEqual(plan_case(self.catalog, 'fortistore-injection', 'block')['system_prompt'], '')
        self.assertNotIn('employee_directory_sensitive', plan_case(self.catalog, 'hr-tool-dlp', 'redact')['tools'])

    def test_missing_action_fails(self):
        with self.assertRaises(ValueError):
            plan_case(self.catalog, 'fortistore-injection', 'redact')


if __name__ == '__main__':
    unittest.main()
