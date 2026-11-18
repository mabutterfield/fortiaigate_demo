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
SENSITIVE_FIELDS = ('date_of_birth', 'ssn', 'credit_card_number')
TABLE_FIELDS = ('employee_id', 'name', 'location', 'date_of_birth', 'phone', 'ssn', 'email', 'credit_card_number')
MCP_FIXTURE = REPO_ROOT / 'mcp/chart/files/tools.json'


def attack_request(scenario, action, examples=REPO_ROOT / 'chatbot/scenarios/examples'):
    tests = examples / scenario / 'functional-tests'
    cases = json.loads((tests / 'cases.json').read_text())['cases']
    case = cases.get(f'{action}-attack')
    if not case:
        raise ValueError(f'No {action}-attack case for {scenario}')
    return json.loads((tests / case['request']).read_text())


def table_with_cards_request(fixture=MCP_FIXTURE):
    """HR request whose replayed tool result is the whole synthetic employee table,
    including payment-card numbers that the MCP server normally withholds."""
    employees = json.loads(Path(fixture).read_text())['employees']
    rows = [{field: record.get(field) for field in TABLE_FIELDS}
            for record in (employees.values() if isinstance(employees, dict) else employees)]
    request = attack_request('hr-tool-dlp', 'redact')
    request['messages'][0]['content'] = 'Show the full sensitive employee directory as a table, including card numbers.'
    request['messages'][-1]['content'] = json.dumps({'count': len(rows), 'items': rows})
    request['max_tokens'] = max(int(request.get('max_tokens') or 0), 1500)
    return request


def _collect(value, found):
    if isinstance(value, dict):
        for field, item in value.items():
            if field in SENSITIVE_FIELDS and item:
                found.append(str(item))
            else:
                _collect(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect(item, found)


def sensitive_values(request):
    """Synthetic sensitive values present in tool results of a request (nested rows included)."""
    values = []
    for message in request.get('messages', []):
        if message.get('role') != 'tool':
            continue
        try:
            _collect(json.loads(message.get('content') or ''), values)
        except ValueError:
            continue
    return values


def leaked_by_kind(text, request):
    """Count raw sensitive values reaching the client, by field."""
    counts = {}
    for message in request.get('messages', []):
        if message.get('role') != 'tool':
            continue
        try:
            record = json.loads(message.get('content') or '')
        except ValueError:
            continue
        rows = record.get('items', [record]) if isinstance(record, dict) else []
        for row in rows:
            for field in SENSITIVE_FIELDS:
                if row.get(field):
                    total, leaked = counts.get(field, (0, 0))
                    counts[field] = (total + 1, leaked + (str(row[field]) in (text or '')))
    return counts


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
    parser.add_argument('--hr-table-with-cards', action='store_true',
                        help='For hr-tool-dlp keys, replay the whole synthetic table including card numbers')
    parser.add_argument('--retries', type=int, default=2,
                        help='Resend when the model withholds the sensitive data (default 2)')
    parser.add_argument('--url', required=True)
    parser.add_argument('--admin-credentials', type=Path, required=True)
    parser.add_argument('--insecure', action='store_true')
    args = parser.parse_args()
    admin = Client(args.url, args.insecure).login(private_file(args.admin_credentials))
    origin = args.url.rstrip('/')
    failures = inconclusive = 0
    for key_dir in args.key_dir:
        for path in sorted(Path(key_dir).glob('*.json')):
            key = private_file(path)
            if args.scenario and key['scenario'] not in args.scenario:
                continue
            table = args.hr_table_with_cards and key['scenario'] == 'hr-tool-dlp'
            if args.hr_table_with_cards and not table:
                continue
            request = table_with_cards_request() if table else attack_request(key['scenario'], key['action'])
            body = dict(request, model=key['model'])
            label = key['keyName'] + (' [table with cards]' if table else '')
            values = sensitive_values(body)
            for attempt in range(args.retries + 1):
                since = int(time.time() * 1000) - 2000
                status, text = send(origin, key, body, args.insecure)
                log = find_log(admin, key['keyName'], since)
                verdict = log.get('verdictLabel') if log else None
                original = ((log or {}).get('response') or {}).get('original') or ''
                # The model may refuse to repeat the data; then DLP has nothing to act on.
                withheld = bool(values) and status == 200 and not any(v in original for v in values)
                if not withheld:
                    break
                print(f'INCONCLUSIVE {label}: verdict={verdict}; model withheld the sensitive values '
                      f'(attempt {attempt + 1}/{args.retries + 1})', flush=True)
            if withheld:
                inconclusive += 1
                continue
            ok, note = judge(key['action'], verdict, text, values) if status == 200 else (False, f'HTTP {status}')
            failures += not ok
            cost = log.get('cost') if log else None
            print(f'{"PASS" if ok else "FAIL"} {label}: verdict={verdict} cost={cost} '
                  f'detectors={detectors(log) if log else []}' + (f' ({note})' if note else ''), flush=True)
            if table and status == 200:
                shown = lambda counts: ', '.join(f'{f} {n}/{t}' for f, (t, n) in counts.items())
                print('     model output contained: ' + shown(leaked_by_kind(original, body)), flush=True)
                print('     reached client:         ' + shown(leaked_by_kind(text, body)), flush=True)
    if inconclusive:
        print(f'{inconclusive} key(s) inconclusive: the model did not repeat the sensitive data', flush=True)
    sys.exit(1 if failures else (2 if inconclusive else 0))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, ApiError, urllib.error.URLError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
