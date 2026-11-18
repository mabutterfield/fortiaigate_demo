import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pricing  # noqa: E402
import model_pricing  # noqa: E402

PRICING = pricing.load_pricing()


class PricingTests(unittest.TestCase):
    def test_sample_prices_cost_dollars_per_request(self):
        # A typical scenario request is about 650 input and 90 output tokens.
        for alias in PRICING['models']:
            price = pricing.model_price(PRICING, alias)
            per_request = (650 * price['input'] + 90 * price['output']) / 1_000_000
            self.assertTrue(2 <= per_request <= 10, (alias, per_request))

    def test_model_entries_override_default_per_field(self):
        self.assertEqual(pricing.model_price(PRICING, 'fortistore-injection')['output'], 9000.0)
        unknown = pricing.model_price(PRICING, 'fortistore-injection-faig-chain')
        self.assertEqual((unknown['input'], unknown['output']), (3000.0, 6000.0))
        self.assertIsNone(unknown['cache_read'])

    def test_cost_fields_match_faig_model_entry(self):
        fields = pricing.cost_fields(PRICING, 'hr-tool-dlp')
        self.assertEqual(fields, {'customInputCost': 5000.0, 'customOutputCost': 10000.0, 'customCacheReadCost': None,
                                  'customCacheWriteCost': None, 'customizedCost': True})
        unpriced = pricing.cost_fields({'default': None, 'models': {}}, 'x')
        self.assertFalse(unpriced['customizedCost'])

    def test_invalid_pricing_is_rejected(self):
        bad = {'currency': 'USD', 'unit': 'per_1m_tokens', 'default': {'input': -1}, 'models': {}}
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(bad, f)
        with self.assertRaises(ValueError):
            pricing.load_pricing(f.name)
        Path(f.name).unlink()

    def test_changes_and_provider_update_preserve_credentials(self):
        provider = {'providerId': 'litellm-direct', 'platform': 'custom', 'name': 'litellm-direct',
                    'endpoint': {'kind': 'customUrl'}, 'description': 'd', 'autoSyncNewModels': False,
                    'updatedAt': 't',
                    'apiKeys': [{'id': 'k1', 'name': 'litellm-key', 'enabled': True, 'weight': 1,
                                 'apiKeyMasked': 'sk-***abcd', 'credential': {'kind': 'apiKey'}}],
                    'models': [{'uuid': 'u1', 'modelId': 'pass-model', 'publicName': 'pass-model', 'enabled': True,
                                'isCustom': True, 'customizedCost': False, 'customInputCost': None,
                                'customOutputCost': None, 'healthStatus': 'healthy'}]}
        diff = pricing.cost_changes(provider['models'][0], PRICING)
        self.assertEqual(diff['customInputCost'], (None, 3000.0))
        body = model_pricing.provider_update(provider, PRICING)
        self.assertEqual(body['apiKeys'], [{'id': 'k1', 'name': 'litellm-key', 'description': None,
                                            'enabled': True, 'weight': 1}])
        self.assertNotIn('healthStatus', body['models'][0])
        self.assertEqual((body['models'][0]['uuid'], body['models'][0]['customOutputCost']), ('u1', 8000.0))
        self.assertEqual(body['updatedAt'], 't')


if __name__ == '__main__':
    unittest.main()
