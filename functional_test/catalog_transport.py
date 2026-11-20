"""8.0.2 catalog-runner transport, independent of legacy scenario state."""
from __future__ import annotations

import argparse
import http.cookiejar
import json
from pathlib import Path
import shlex
import ssl
import subprocess
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = Path(__file__).with_name('baseline_agent.py')
SHARED_AGENT_PATH = ROOT / 'chatbot/agent/faig_agent.py'
REMOTE_DIR = '/tmp/faig-baseline'
REMOTE_AGENT_PATH = REMOTE_DIR + '/baseline_agent.py'


def parse_inventory(path: Path, host_alias: str) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f'Inventory does not exist: {path}')
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith(('[', '#')):
            continue
        parts = shlex.split(line)
        if not parts or parts[0] != host_alias:
            continue
        values = {'alias': host_alias}
        for item in parts[1:]:
            if '=' in item:
                key, value = item.split('=', 1)
                values[key] = value
        values.setdefault('ansible_host', host_alias)
        values.setdefault('ansible_user', 'ubuntu')
        return values
    raise SystemExit(f"Host alias '{host_alias}' not found in {path}")


def ssh_base(host: dict[str, str]) -> list[str]:
    command = ['ssh', '-o', 'StrictHostKeyChecking=accept-new']
    key = host.get('ansible_ssh_private_key_file', '').strip()
    if key:
        command.extend(['-i', str(Path(key).expanduser())])
    command.append(f"{host.get('ansible_user', 'ubuntu')}@{host['ansible_host']}")
    return command


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FaigAdmin:
    """Short-lived admin session used to read matching Traffic Log entries."""
    def __init__(self, origin: str, credentials: dict[str, str], insecure: bool):
        self.origin = origin.rstrip('/')
        context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=context))
        body = json.dumps({'username': credentials['username'], 'password': credentials['password']}).encode()
        headers = {'Content-Type': 'application/json', 'Origin': self.origin, 'Referer': self.origin + '/'}
        with self.opener.open(urllib.request.Request(self.origin + '/api/v1/login', data=body, headers=headers,
                                                     method='POST'), timeout=60) as response:
            self.csrf = json.loads(response.read())['csrf_token']

    def get(self, path: str) -> Any:
        headers = {'X-CSRF-Token': self.csrf, 'Origin': self.origin, 'Referer': self.origin + '/'}
        with self.opener.open(urllib.request.Request(self.origin + path, headers=headers), timeout=60) as response:
            return json.loads(response.read())


def kubectl_exec(args: argparse.Namespace, host: dict[str, str], command: list[str], stdin: str) -> subprocess.CompletedProcess:
    remote = ' '.join(shlex.quote(part) for part in [
        'sudo', 'kubectl', '-n', args.mcp_namespace, 'exec', '-i', f'deployment/{args.mcp_deployment}',
        '-c', args.mcp_container, '--', *command])
    return subprocess.run([*ssh_base(host), remote], input=stdin, text=True, capture_output=True, check=False)


def run_case(args: argparse.Namespace, host: dict[str, str], case: dict[str, Any], key: dict[str, Any]) -> dict[str, Any]:
    spec = {'base_url': args.faig_internal_url, 'api_key': key['secretKey'], 'model': case['model'],
            'prompt': case['prompt'], 'system_prompt': case['system_prompt'], 'mcp_url': args.mcp_url,
            'tools': case['tools'], 'max_rounds': case['max_rounds'], 'max_tokens': args.max_tokens,
            'temperature': args.temperature, 'verify_tls': args.internal_verify_tls}
    result = kubectl_exec(args, host, ['python', REMOTE_AGENT_PATH], json.dumps(spec))
    if result.returncode != 0:
        return {'error': 'agent_exec_failed', 'stderr': result.stderr[-600:], 'reply': '', 'tool_events': []}
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'error': 'agent_output_not_json', 'stdout': result.stdout[-600:], 'reply': '', 'tool_events': []}
