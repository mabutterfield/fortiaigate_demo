#!/usr/bin/env python3
"""Generate FAIG provider resources from this checkout's installed scenario matrix."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from pricing import DEFAULT_PRICING, cost_fields, load_pricing

ROOT = Path(__file__).resolve().parents[2]


def matrix_groups():
    """LiteLLM aliases from this checkout's installed scenarios, by FAIG provider."""
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_scenario_matrix.py')], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    models = json.loads(result.stdout)['litellm_models']
    return {
        'litellm-direct': [m['name'] for m in models if m['llm_target'] != 'faig-chain-reentry'],
        'litellm-faig-chain': [m['name'] for m in models if m['llm_target'] == 'faig-chain-reentry'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New JSON resource file')
    parser.add_argument('--litellm-url', default='http://litellm.litellm.svc.cluster.local:4000/v1')
    parser.add_argument('--pricing', type=Path, default=DEFAULT_PRICING, help='Lab model prices (USD per 1M tokens)')
    args = parser.parse_args()
    pricing = load_pricing(args.pricing)
    groups = matrix_groups()
    if 'pass-model' not in groups['litellm-direct']:
        raise ValueError('Matrix does not contain the direct pass-model')
    resources = []
    for name, aliases in groups.items():
        entries = [{'modelId': alias, 'publicName': alias, 'enabled': True, 'isCustom': True,
                    'description': '', **cost_fields(pricing, alias)} for alias in aliases]
        resources.append({
            'name': name, 'kind': 'provider', 'operation': 'create', 'lookup': name,
            'body': {'providerId': name, 'platform': 'custom', 'name': name,
                     'endpoint': {'kind': 'customUrl', 'baseUrl': args.litellm_url, 'apiFormat': 'openai'},
                     'description': 'LiteLLM FAIG re-entry aliases' if name.endswith('chain') else 'LiteLLM direct aliases',
                     'autoSyncNewModels': False,
                     'apiKeys': [{'name': 'litellm-key', 'credential': {'kind': 'apiKey', 'apiKey': {'$secret': 'LiteLLM master key'}}, 'enabled': True, 'weight': 1}],
                     'models': entries},
            'checks': [{'field': 'providerId', 'equals': name}] + [
                {'field': 'models', 'contains': {'modelId': alias}} for alias in aliases],
        })
    # Generated file has placeholders, never the credential itself.
    with args.output.open('x', encoding='utf-8') as output:
        json.dump({'resources': resources}, output, indent=2)
        output.write('\n')
    print('Generated', args.output)
    for name, aliases in groups.items():
        print(name + ': ' + (', '.join(aliases) if aliases else '(no enabled aliases)'))
    if not groups['litellm-faig-chain']:
        print('Re-entry provider has no models; empty-provider API creation is not yet verified.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
