"""Evaluate a catalog case against collected observations (no live requests)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from catalog802 import loader
from catalog802.result_contract import evaluate


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--test', required=True)
    parser.add_argument('--observations', required=True, type=Path,
                        help='JSON with execution, verdict_rows, requests_sent, evidence and tools_called')
    parser.add_argument('--faig-version', required=True)
    args = parser.parse_args(argv)
    catalog, errors = loader.load(Path(__file__).resolve().parents[1])
    if errors:
        print('; '.join(errors), file=sys.stderr)
        return 2
    scenario = catalog['scenarios'].get(args.scenario)
    case = next((t for t in scenario['tests'] if t['id'] == args.test), None) if scenario else None
    if case is None:
        print('unknown scenario or test ID', file=sys.stderr)
        return 2
    try:
        obs = json.loads(args.observations.read_text(encoding='utf-8'))
        required = {'execution', 'verdict_rows', 'requests_sent', 'evidence', 'tools_called'}
        if not isinstance(obs, dict) or set(obs) != required:
            raise ValueError('observations must contain exactly: ' + ', '.join(sorted(required)))
        if any(not isinstance(obs[key], list) for key in ('verdict_rows', 'evidence', 'tools_called')):
            raise ValueError('verdict_rows, evidence, and tools_called must be lists')
        if any(not isinstance(item, str) for key in ('evidence', 'tools_called') for item in obs[key]):
            raise ValueError('evidence and tools_called entries must be strings')
        result = evaluate(**obs, test=case, faig_version=args.faig_version,
                          scenario_version=scenario['scenario_version'])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'invalid observations: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({'scenario': args.scenario, 'test': args.test, **result}, indent=2))
    return 0 if result['outcome'] == 'pass' else 1
