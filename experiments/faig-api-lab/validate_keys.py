#!/usr/bin/env python3
"""Send each scenario's functional-test attack request through FAIG with each
per-action student key and check the Traffic Log verdict.

Key files come from `scenario_lab.py prepopulate` (studentNN-keys/*.json).
Requests are the tracked scenario fixtures named by each profile's
functional-tests/cases.json (`<action>-attack`). Secrets are read from the
private key files and never printed. Observed FAIG 8.0.2 behavior.
"""
import argparse
import json
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request

from scenario_lab import REPO_ROOT, ApiError, Client, items
from student_lab import private_file

EXPECTED_VERDICT = {'alert': 'Alert', 'deny': 'Block', 'redact': 'Redact'}
SENSITIVE_FIELDS = ('date_of_birth', 'ssn')


def attack_request(scenario, action, examples=REPO_ROOT / 'chatbot/scenarios/examples'):
    tests = examples / scenario / 'functional-tests'
    cases = json.loads((tests / 'cases.json').read_text())['cases']
    case = cases.get(f'{action}-attack')
    if not case:
        raise ValueError(f'No {action}-attack case for {scenario}')
    return json.loads((tests / case['request']).read_text())


def sensitive_values(request):
    """Synthetic sensitive values present in tool results of a request fixture."""
    values = []
    for message in request.get('messages', []):
        if message.get('role') != 'tool':
            continue
        try:
            record = json.loads(message.get('content') or '')
        except ValueError:
            continue
        for field in SENSITIVE_FIELDS:
            if isinstance(record, dict) and record.get(field):
                values.append(str(record[field]))
    return values


def judge(action, verdict, text, values):
    """Return (ok, note) for one key's observed result."""
    leaked = [v for v in values if v in (text or '')]
    expected = EXPECTED_VERDICT.get(action)
    if verdict != expected:
        return False, f'expected {expected}'
    if action == 'redact' and leaked:
        return False, 'sensitive value reached client'
    if action == 'alert' and values and not leaked:
        return True, 'alert logged; model did not repeat sensitive values'
    if action == 'alert' and leaked:
        return True, 'alert logged; original values passed through'
    return True, ''


def send(origin, key, body, insecure):
    ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    request = urllib.request.Request(origin + key['basePath'] + '/chat/completions', method='POST',
                                     data=json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer ' + key['secretKey'],
                                              'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, context=ctx, timeout=180) as response:
            data = json.loads(response.read())
            return response.status, (data.get('choices') or [{}])[0].get('message', {}).get('content') or ''
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300].decode(errors='replace')


def find_log(admin, key_name, since_ms, attempts=10):
    for _ in range(attempts):
        for row in items(admin.call('GET', '/api/v1/admin/traffic-logs?limit=50&offset=0')):
            if row.get('keyAlias') == key_name and row.get('timeStamp', 0) >= since_ms:
                return admin.call('GET', '/api/v1/admin/traffic-logs/' + row['uuid'])
        time.sleep(2)
    return None


def detectors(log):
    names = []
    for side in ('input', 'output'):
        for item in (log.get('violation') or {}).get(side) or []:
            names.append(f'{side}:{item.get("detectorName") or item.get("detectorId")}')
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--key-dir', type=Path, required=True, action='append',
                        help='Owner-only studentNN-keys directory (repeatable)')
    parser.add_argument('--scenario', action='append', help='Limit to a scenario (repeatable)')
    parser.add_argument('--url', required=True)
    parser.add_argument('--admin-credentials', type=Path, required=True)
    parser.add_argument('--insecure', action='store_true')
    args = parser.parse_args()
    admin = Client(args.url, args.insecure).login(private_file(args.admin_credentials))
    origin = args.url.rstrip('/')
    failures = 0
    for key_dir in args.key_dir:
        for path in sorted(Path(key_dir).glob('*.json')):
            key = private_file(path)
            if args.scenario and key['scenario'] not in args.scenario:
                continue
            body = dict(attack_request(key['scenario'], key['action']), model=key['model'])
            since = int(time.time() * 1000) - 2000
            status, text = send(origin, key, body, args.insecure)
            log = find_log(admin, key['keyName'], since)
            verdict = log.get('verdictLabel') if log else None
            ok, note = judge(key['action'], verdict, text, sensitive_values(body)) if status == 200 \
                else (False, f'HTTP {status}')
            failures += not ok
            cost = log.get('cost') if log else None
            print(f'{"PASS" if ok else "FAIL"} {key["keyName"]}: verdict={verdict} cost={cost} '
                  f'detectors={detectors(log) if log else []}' + (f' ({note})' if note else ''), flush=True)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, ApiError, urllib.error.URLError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
