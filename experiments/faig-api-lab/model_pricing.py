#!/usr/bin/env python3
"""Preview or apply code-defined lab prices to existing FAIG provider models.

Reads model-pricing.json, compares each provider model's custom costs, and
optionally (--sync-matrix) adds installed-scenario LiteLLM aliases missing
from the provider and (--set-credential-file) replaces the provider's stored
LiteLLM credential, for example with the shared non-admin virtual key. With --apply it saves the provider with a full update that keeps its endpoint,
models and stored credentials (credentials are referenced by ID only; no
secret is sent). Observed FAIG 8.0.2 GUI API; not a supported interface.
"""
import argparse
import re
import subprocess
from pathlib import Path
import sys
import urllib.error
import urllib.parse

from build_providers import matrix_groups
from pricing import DEFAULT_PRICING, apply_costs, cost_changes, cost_fields, load_pricing
from scenario_lab import ApiError, Client
from student_lab import private_file

MODEL_FIELDS = ('uuid', 'modelId', 'publicName', 'enabled', 'isCustom', 'description', 'customizedCost',
                'customInputCost', 'customOutputCost', 'customCacheReadCost', 'customCacheWriteCost')


def new_model(alias, pricing):
    """A custom provider model entry for a LiteLLM alias (no uuid until saved)."""
    return {'modelId': alias, 'publicName': alias, 'enabled': True, 'isCustom': True, 'description': '',
            **cost_fields(pricing, alias)}


def missing_models(provider, aliases):
    present = {m['modelId'] for m in provider.get('models', [])}
    return [alias for alias in aliases if alias not in present]


def masked_matches(masked, key):
    """True when FAIG's masked credential (e.g. 'sk-******abcd') fits the given key."""
    parts = [p for p in re.split(r'[*.\u2022\u2026]+', masked or '') if p]
    return bool(parts) and key.startswith(parts[0]) and key.endswith(parts[-1])


def load_credential(path):
    """Read an owner-only JSON file holding the replacement key as `api_key`."""
    data = private_file(path)
    key = data.get('api_key') or data.get('apiKey') or data.get('secretKey')
    if not isinstance(key, str) or not key:
        raise ValueError(f'No api_key in credential file: {path}')
    return key


def provider_update(provider, pricing, add=(), credential=None):
    """Full provider PUT body as the GUI sends it, with prices applied and new aliases appended.

    With `credential`, every stored key of the provider is replaced by that value
    (the GUI sends `credential: {kind, apiKey}` only for edited keys)."""
    return {'providerId': provider['providerId'], 'platform': provider['platform'], 'name': provider['name'],
            'endpoint': provider['endpoint'], 'description': provider.get('description'),
            'autoSyncNewModels': provider.get('autoSyncNewModels', False),
            'apiKeys': [{'id': k['id'], 'name': k['name'], 'description': k.get('description'),
                         'enabled': k.get('enabled', True), 'weight': k.get('weight', 1),
                         **({'credential': {'kind': 'apiKey', 'apiKey': credential}} if credential else {})}
                        for k in provider.get('apiKeys', [])],
            'models': [apply_costs({f: m.get(f) for f in MODEL_FIELDS}, pricing) for m in provider.get('models', [])]
            + [new_model(alias, pricing) for alias in add],
            'updatedAt': provider['updatedAt']}


def verify_credential(admin, saved, credential):
    """Check the stored mask and run FAIG's connectivity test with the stored credential."""
    provider_id = saved['providerId']
    for key in saved.get('apiKeys', []):
        if not masked_matches(key.get('apiKeyMasked'), credential):
            raise RuntimeError(f'{provider_id}: stored credential {key["name"]} does not match the new key')
        model = (saved.get('models') or [{}])[0].get('modelId')
        if not model:
            continue
        result = admin.call('POST', '/api/v1/admin/ai-providers/connectivity-tests', {
            'url': saved['baseUrl'], 'platform': saved['platform'], 'model': model, 'providerId': provider_id,
            'endpoint': saved['endpoint'],
            'draftCredentials': [{'ref': key['id'], 'credentialId': key['id'], 'name': key['name'], 'enabled': True}]})
        if not (result.get('reachable') and result.get('credentialsVerified')):
            raise RuntimeError(f'{provider_id}: connectivity test failed with the stored credential')
        print(f'{provider_id}: credential {key["name"]} verified with {model}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pricing', type=Path, default=DEFAULT_PRICING)
    parser.add_argument('--provider', action='append', help='Limit to a provider (repeatable)')
    parser.add_argument('--url', required=True)
    parser.add_argument('--admin-credentials', type=Path, required=True)
    parser.add_argument('--insecure', action='store_true', help='Skip TLS verification (isolated lab only)')
    parser.add_argument('--sync-matrix', action='store_true',
                        help='Also add installed-scenario LiteLLM aliases missing from each provider')
    parser.add_argument('--set-credential-file', type=Path,
                        help='Owner-only JSON with api_key: replace the provider credential with this key')
    parser.add_argument('--apply', action='store_true', help='Save changes; default is preview')
    args = parser.parse_args()
    pricing = load_pricing(args.pricing)
    credential = load_credential(args.set_credential_file) if args.set_credential_file else None
    if credential and not args.provider:
        parser.error('--set-credential-file requires an explicit --provider')
    groups = matrix_groups() if args.sync_matrix else {}
    admin = Client(args.url, args.insecure).login(private_file(args.admin_credentials))
    for provider_id in args.provider or pricing['providers']:
        path = '/api/v1/admin/ai-providers/' + urllib.parse.quote(provider_id, safe='')
        provider = admin.call('GET', path)
        add = missing_models(provider, groups.get(provider_id, []))
        for alias in add:
            print(f'{provider_id} {alias}: add model (input {cost_fields(pricing, alias)["customInputCost"]}, '
                  f'output {cost_fields(pricing, alias)["customOutputCost"]} USD per 1M tokens)')
        changed = bool(add)
        for model in provider.get('models', []):
            diff = cost_changes(model, pricing)
            if diff:
                changed = True
                shown = ', '.join(f'{f}: {old} -> {new}' for f, (old, new) in diff.items())
                print(f'{provider_id} {model["modelId"]}: {shown}')
        if credential:
            keys = provider.get('apiKeys', [])
            if not keys:
                raise RuntimeError(f'{provider_id}: no stored credential to replace')
            if all(masked_matches(k.get('apiKeyMasked'), credential) for k in keys):
                print(f'{provider_id}: credential already matches the given key')
            else:
                changed = True
                print(f'{provider_id}: replace credential {", ".join(k["name"] for k in keys)} '
                      f'(stored {keys[0].get("apiKeyMasked")})')
        if not provider.get('models') and not add:
            print(f'{provider_id}: no models')
        elif not changed:
            print(f'{provider_id}: prices already match')
        if changed and args.apply:
            saved = admin.call('PUT', path, provider_update(provider, pricing, add, credential))
            expected = [m['modelId'] for m in provider.get('models', [])] + add
            if sorted(m['modelId'] for m in saved.get('models', [])) != sorted(expected) or \
                    [k['id'] for k in saved.get('apiKeys', [])] != [k['id'] for k in provider.get('apiKeys', [])]:
                raise RuntimeError(f'{provider_id}: saved provider models or credentials differ from the original')
            remaining = [m['modelId'] for m in saved['models'] if cost_changes(m, pricing)]
            if remaining:
                raise RuntimeError(f'{provider_id}: prices not applied for {", ".join(remaining)}')
            if credential:
                verify_credential(admin, saved, credential)
            print(f'{provider_id}: saved and verified')
    if not args.apply:
        print('Preview only; pass --apply to save.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, ApiError, urllib.error.URLError,
            subprocess.CalledProcessError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
