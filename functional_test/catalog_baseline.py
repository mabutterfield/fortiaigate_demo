"""Run one catalog scenario using a FAIG key and correlated Traffic Log rows."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import uuid

from catalog802 import loader
from catalog802.result_contract import evaluate
from functional_test import baseline, validation
from functional_test.catalog_logs import match_rows
from functional_test.catalog_plan import plan_case
from functional_test.result_contract import contains_sensitive


def evidence_from_turn(raw, test, *, block_message=None):
    """Classify client-observable evidence without guessing a FAIG verdict."""
    evidence = set()
    reply = str(raw.get('reply') or '')
    events = raw.get('tool_events') or []
    if contains_sensitive(reply):
        evidence.add('sensitive-data-in-reply')
    if any(isinstance(e, dict) and contains_sensitive(e.get('result')) for e in events):
        evidence.add('sensitive-data-in-tool-result')
    if block_message is not None and reply.strip() == block_message.strip():
        evidence.add('block-message-in-reply')
    if '[REDACTED_' in reply.upper():
        evidence.add('redaction-marker-in-reply')
    tools = [str(e.get('tool') or e.get('name')) for e in events if isinstance(e, dict)]
    if set(test['attack_tools']) & set(tools):
        evidence.add('attack-tool-called')
    return sorted(evidence), tools


def request_count(raw):
    """Count attempts when the shared agent returned a reliable round count."""
    rounds = raw.get('rounds')
    count_known = not raw.get('error') or raw.get('error') == 'http_error'
    if count_known and isinstance(rounds, int) and not isinstance(rounds, bool) and rounds >= 0:
        return rounds + 1
    return None


def read_private(path):
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f'credential file must exist and be owner-only: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario', required=True)
    p.add_argument('--action', required=True, choices=('alert', 'block', 'redact'))
    p.add_argument('--test', help='Explicit catalog test ID; defaults to the normal attack test')
    p.add_argument('--key-file', required=True, type=Path)
    p.add_argument('--admin-credentials', required=True, type=Path)
    p.add_argument('--faig-version', default='8.0.2')
    p.add_argument('--inventory', required=True)
    p.add_argument('--host-alias', default='faig-aws')
    p.add_argument('--faig-url', required=True)
    p.add_argument('--insecure', action='store_true')
    p.add_argument('--faig-internal-url', default='http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/ai/openai/v1')
    p.add_argument('--mcp-url', default='http://mcp-demo.mcp.svc.cluster.local:8001/mcp')
    p.add_argument('--mcp-namespace', default='mcp')
    p.add_argument('--mcp-deployment', default='mcp-demo')
    p.add_argument('--mcp-container', default='mcp-standard')
    p.add_argument('--max-tokens', type=int, default=2048)
    p.add_argument('--temperature', type=float, default=0.0)
    p.add_argument('--log-wait', type=int, default=20)
    p.add_argument('--block-message-file', type=Path, help='File containing the exact FAIG block message, required when a case checks it')
    return p.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    if args.log_wait < 0 or args.log_wait > 120:
        raise SystemExit('log wait must be between 0 and 120 seconds')
    catalog, errors = loader.load(validation.REPO_ROOT)
    if errors:
        raise SystemExit('; '.join(errors))
    try:
        case = plan_case(catalog, args.scenario, args.action, test_id=args.test)
        key = read_private(args.key_file)
        credentials = read_private(args.admin_credentials)
        if key.get('scenario') != args.scenario or key.get('action') != args.action or key.get('model') != case['model']:
            raise ValueError('key metadata must match scenario, action and catalog model')
        required_evidence = set(case['test']['expect']['evidence_present'] + case['test']['expect']['evidence_absent'])
        block_message = args.block_message_file.read_text(encoding='utf-8') if args.block_message_file else None
        if 'block-message-in-reply' in required_evidence and (block_message is None or not block_message.strip()):
            raise ValueError('a nonempty exact block-message file is required for this case')
        if not key.get('secretKey') or not key.get('keyName'):
            raise ValueError('key file is missing keyName or secretKey')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(str(exc)) from exc
    host = validation.parse_inventory(Path(args.inventory), args.host_alias)
    admin = baseline.FaigAdmin(args.faig_url, credentials, args.insecure)
    for source, target in ((baseline.SHARED_AGENT_PATH, baseline.REMOTE_DIR + '/faig_agent.py'),
                           (baseline.AGENT_PATH, baseline.REMOTE_AGENT_PATH)):
        copied = baseline.kubectl_exec(args, host, ['sh', '-c', f'mkdir -p {baseline.REMOTE_DIR} && cat > {target}'],
                                      source.read_text(encoding='utf-8'))
        if copied.returncode:
            raise SystemExit(f'could not stage {source.name} in the MCP pod')
    marker = '[faig-test-' + uuid.uuid4().hex + ']'
    case['prompt'] += '\n' + marker
    since = int(time.time() * 1000) - 2000
    raw = baseline.run_case(args, host, case, key)
    execution = 'error' if raw.get('error') else 'completed'
    requests_sent = request_count(raw)
    evidence, tools = evidence_from_turn(raw, case['test'], block_message=block_message)
    rows = []
    deadline = time.monotonic() + args.log_wait
    while execution == 'completed' and requests_sent:
        try:
            response = admin.get('/api/v1/admin/traffic-logs?limit=100&offset=0')
            summaries = response.get('items', []) if isinstance(response, dict) else response
            rows = match_rows(summaries, key_name=key['keyName'], since_ms=since, marker=marker,
                              fetch_detail=lambda uid: admin.get('/api/v1/admin/traffic-logs/' + uid))
        except Exception:
            rows = []  # Unavailable evidence must not become a pass.
        if len(rows) >= requests_sent or time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    result = evaluate(execution=execution, verdict_rows=rows, requests_sent=requests_sent if requests_sent is not None else 0,
                      evidence=evidence, tools_called=tools, test=case['test'],
                      faig_version=args.faig_version, scenario_version=case['scenario_version'])
    report = {'scenario': args.scenario, 'action': args.action, 'test': case['case_id'],
              'requests_sent': requests_sent, 'tools_called': tools, **result}
    if raw.get('error'):
        report['execution_error'] = str(raw['error'])
        report['http_status'] = raw.get('http_status')
    print(json.dumps(report, indent=2))
    return 0 if result['outcome'] == 'pass' else 1
