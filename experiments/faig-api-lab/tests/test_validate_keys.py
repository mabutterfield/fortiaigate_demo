from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import validate_keys as vk  # noqa: E402


class ValidateKeysTests(unittest.TestCase):
    def test_every_scenario_action_has_an_attack_fixture(self):
        for scenario, actions in (('fortistore-injection', ('alert', 'deny')),
                                  ('hr-tool-dlp', ('alert', 'redact', 'deny')),
                                  ('resume-tool-injection', ('alert', 'deny'))):
            for action in actions:
                self.assertIn('messages', vk.attack_request(scenario, action))

    def test_hr_fixture_exposes_synthetic_dob_and_ssn(self):
        values = vk.sensitive_values(vk.attack_request('hr-tool-dlp', 'redact'))
        self.assertEqual(len(values), 2)

    def test_table_with_cards_includes_every_row(self):
        request = vk.table_with_cards_request()
        values = vk.sensitive_values(request)
        self.assertEqual(len(values), 15)
        counts = vk.leaked_by_kind('none here', request)
        self.assertEqual(counts['credit_card_number'], (5, 0))
        self.assertEqual(request['model'], 'hr-tool-dlp')

    def test_judge(self):
        values = ['1981-01-02', '489-36-8350']
        self.assertEqual(vk.judge('deny', 'Block', 'blocked', values), (True, ''))
        self.assertFalse(vk.judge('deny', 'Alert', '', values)[0])
        self.assertTrue(vk.judge('redact', 'Redact', 'DOB [REDACTED_DATE_OF_BIRTH_1]', values)[0])
        self.assertEqual(vk.judge('redact', 'Redact', 'SSN 489-36-8350', values),
                         (False, 'sensitive value reached client'))
        self.assertTrue(vk.judge('alert', 'Alert', 'SSN 489-36-8350', values)[0])
        self.assertFalse(vk.judge('alert', 'Log', '', [])[0])


if __name__ == '__main__':
    unittest.main()
