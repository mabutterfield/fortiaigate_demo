"""Code-defined lab prices for FAIG provider model entries (USD per 1M tokens)."""
import json
from pathlib import Path

DEFAULT_PRICING = Path(__file__).resolve().parent / 'model-pricing.json'
FIELDS = {'input': 'customInputCost', 'output': 'customOutputCost',
          'cache_read': 'customCacheReadCost', 'cache_write': 'customCacheWriteCost'}


def _price(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f'{label} must be a non-negative number or null')
    return float(value)


def load_pricing(path=DEFAULT_PRICING):
    pricing = json.loads(Path(path).read_text())
    if pricing.get('unit') != 'per_1m_tokens' or pricing.get('currency') != 'USD':
        raise ValueError('Pricing file must use USD per_1m_tokens, matching FAIG')
    for name, spec in [('default', pricing.get('default'))] + list(pricing.get('models', {}).items()):
        if spec is None:
            continue
        unknown = set(spec) - set(FIELDS)
        if unknown:
            raise ValueError(f'Unknown price fields for {name}: {", ".join(sorted(unknown))}')
        for key in FIELDS:
            _price(spec.get(key), f'{name}.{key}')
    return pricing


def model_price(pricing, alias):
    """Return the alias's prices; model entries override the default per field."""
    merged = dict(pricing.get('default') or {})
    merged.update(pricing.get('models', {}).get(alias, {}))
    return {key: _price(merged.get(key), f'{alias}.{key}') for key in FIELDS}


def cost_fields(pricing, alias):
    """FAIG provider model fields for an alias; unpriced aliases stay uncustomized."""
    price = model_price(pricing, alias)
    fields = {FIELDS[key]: value for key, value in price.items()}
    fields['customizedCost'] = any(value is not None for value in price.values())
    return fields


def apply_costs(model, pricing):
    """Return a copy of a provider model entry with code-defined costs applied."""
    updated = dict(model)
    updated.update(cost_fields(pricing, model['modelId']))
    return updated


def cost_changes(model, pricing):
    desired = cost_fields(pricing, model['modelId'])
    return {field: (model.get(field), value) for field, value in desired.items() if model.get(field) != value}
