#!/usr/bin/env python3
"""Preview or apply code-defined lab prices to existing FAIG provider models.

Reads model-pricing.json, compares each provider model's custom costs, and
with --apply saves the provider with a full update that keeps its endpoint,
models and stored credentials (credentials are referenced by ID only; no
secret is sent). Observed FAIG 8.0.2 GUI API; not a supported interface.
"""
import argparse
from pathlib import Path
import sys
import urllib.error
import urllib.parse

from pricing import DEFAULT_PRICING, apply_costs, cost_changes, load_pricing
from scenario_lab import ApiError, Client
from student_lab import private_file

MODEL_FIELDS = ('uuid', 'modelId', 'publicName', 'enabled', 'isCustom', 'description', 'customizedCost',
                'customInputCost', 'customOutputCost', 'customCacheReadCost', 'customCacheWriteCost')


def provider_update(provider, pricing):
    """Full provider PUT body as the GUI sends it, with prices applied."""
    return {'providerId': provider['providerId'], 'platform': provider['platform'], 'name': provider['name'],
            'endpoint': provider['endpoint'], 'description': provider.get('description'),
            'autoSyncNewModels': provider.get('autoSyncNewModels', False),
            'apiKeys': [{'id': k['id'], 'name': k['name'], 'description': k.get('description'),
                         'enabled': k.get('enabled', True), 'weight': k.get('weight', 1)}
                        for k in provider.get('apiKeys', [])],
            'models': [apply_costs({f: m.get(f) for f in MODEL_FIELDS}, pricing) for m in provider.get('models', [])],
            'updatedAt': provider['updatedAt']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pricing', type=Path, default=DEFAULT_PRICING)
    parser.add_argument('--provider', action='append', help='Limit to a provider (repeatable)')
    parser.add_argument('--url', required=True)
    parser.add_argument('--admin-credentials', type=Path, required=True)
    parser.add_argument('--insecure', action='store_true', help='Skip TLS verification (isolated lab only)')
    parser.add_argument('--apply', action='store_true', help='Save changes; default is preview')
    args = parser.parse_args()
    pricing = load_pricing(args.pricing)
    admin = Client(args.url, args.insecure).login(private_file(args.admin_credentials))
    for provider_id in args.provider or pricing['providers']:
        path = '/api/v1/admin/ai-providers/' + urllib.parse.quote(provider_id, safe='')
        provider = admin.call('GET', path)
        changed = False
        for model in provider.get('models', []):
            diff = cost_changes(model, pricing)
            if diff:
                changed = True
                shown = ', '.join(f'{f}: {old} -> {new}' for f, (old, new) in diff.items())
                print(f'{provider_id} {model["modelId"]}: {shown}')
        if not provider.get('models'):
            print(f'{provider_id}: no models')
        elif not changed:
            print(f'{provider_id}: prices already match')
        if changed and args.apply:
            saved = admin.call('PUT', path, provider_update(provider, pricing))
            if [m['modelId'] for m in saved.get('models', [])] != [m['modelId'] for m in provider['models']] or \
                    [k['id'] for k in saved.get('apiKeys', [])] != [k['id'] for k in provider.get('apiKeys', [])]:
                raise RuntimeError(f'{provider_id}: saved provider models or credentials differ from the original')
            remaining = [m['modelId'] for m in saved['models'] if cost_changes(m, pricing)]
            if remaining:
                raise RuntimeError(f'{provider_id}: prices not applied for {", ".join(remaining)}')
            print(f'{provider_id}: saved and verified')
    if not args.apply:
        print('Preview only; pass --apply to save.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, ApiError, urllib.error.URLError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
