#!/usr/bin/env python3
"""Experimental FAIG 8.0.2 initialization over GUI-observed APIs.

This workflow writes one-shot setup, license and provider objects. Its private
journal prevents blind retries after an uncertain response. It does not create
student resources or claim a governed inference test has completed.
"""
from __future__ import annotations
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


def select_license(directory: Path, pattern: str):
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f'invalid FAIG license filename regex: {exc}') from exc
    matches = sorted(p for p in directory.iterdir() if p.is_file() and rx.fullmatch(p.name))
    if not matches:
        raise ValueError('no license files match the FAIG license filename regex')
    marker = directory / '.last-used'
    if marker.exists():
        previous = marker.read_text(encoding='utf-8').strip()
        names = [p.name for p in matches]
        if previous not in names:
            raise ValueError('last-used license is not among matching files; reconcile marker')
        selected = matches[(names.index(previous) + 1) % len(matches)]
    else:
        selected = matches[0]
    if not selected.stat().st_size:
        raise ValueError('selected license file is empty')
    return selected, marker


def private_json(path):
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f'private file must exist with mode 600: {path}')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'expected a JSON object: {path}')
    return value


def atomic_private_write(path, data):
    tmp = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, origin, insecure=False):
        parsed = urllib.parse.urlsplit(origin)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('FAIG URL must be an HTTPS origin')
        self.origin = origin.rstrip('/')
        context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                                 urllib.request.HTTPSHandler(context=context))
        # Inference must authenticate solely with the virtual key, never admin cookies.
        self.inference_opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
        self.csrf = None

    def call(self, method, path, payload=None, *, raw=None, content_type=None):
        headers = {'Origin': self.origin, 'Referer': self.origin + '/'}
        if self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode()
        else:
            data = raw
            if content_type:
                headers['Content-Type'] = content_type
        request = urllib.request.Request(self.origin + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path}: HTTP {exc.code}; response withheld') from None


    def inference(self, key, payload):
        request = urllib.request.Request(self.origin + '/ai/openai/v1/chat/completions',
            data=json.dumps(payload).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with self.inference_opener.open(request, timeout=120) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'governed inference returned HTTP {exc.code}; response withheld') from None


def is_active(status):
    licenses = status.get('licenses') if isinstance(status, dict) else None
    return isinstance(licenses, list) and any(isinstance(x, dict) and x.get('status') == 'Active' for x in licenses)


def provider_body(secret, model):
    price = model['prices']
    cost = lambda name: float(price[name]) if price[name] is not None else None
    return {'providerId': 'litellm-direct', 'platform': 'custom', 'name': 'litellm-direct',
            'endpoint': {'kind': 'customUrl', 'baseUrl': 'http://litellm.litellm.svc.cluster.local:4000/v1', 'apiFormat': 'openai'},
            'description': 'LiteLLM direct aliases', 'autoSyncNewModels': False,
            'apiKeys': [{'name': 'litellm-key', 'credential': {'kind': 'apiKey', 'apiKey': secret}, 'enabled': True, 'weight': 1}],
            'models': [{'modelId': 'pass-model', 'publicName': 'pass-model', 'enabled': True, 'isCustom': True,
                        'description': '', 'customizedCost': any(v is not None for v in price.values()), 'customInputCost': cost('input'), 'customOutputCost': cost('output'),
                        'customCacheReadCost': cost('cache_read'), 'customCacheWriteCost': cost('cache_write')}]}


def initialize(client, setup, license_dir, license_regex, key, journal_path, model, *, smoke_key_path=None, attempts=30, delay=10, sleep=time.sleep):
    journal = private_json(journal_path) if journal_path.exists() else {}
    def mark(step, value):
        journal[step] = value
        atomic_private_write(journal_path, json.dumps(journal, sort_keys=True) + '\n')
    status = client.call('GET', '/api/v1/setup-status')
    if status.get('needs_setup') is True:
        if journal.get('setup') == 'pending':
            raise RuntimeError('setup result previously unknown; inspect FAIG before retrying')
        mark('setup', 'pending')
        payload = {k: setup[k] for k in ('email', 'username', 'password', 'organization_name')}
        payload['externalUrl'] = client.origin
        auth = client.call('POST', '/api/v1/setup', payload)
        if not auth.get('csrf_token'):
            raise RuntimeError('setup returned no CSRF token; inspect FAIG before retrying')
        client.csrf = auth['csrf_token']
        mark('setup', 'complete')
    elif status.get('needs_setup') is False:
        auth = client.call('POST', '/api/v1/login', {'username': setup['email'], 'password': setup['password']})
        if not auth.get('csrf_token'):
            raise RuntimeError('administrator login returned no CSRF token')
        client.csrf = auth['csrf_token']
        if journal.get('setup') == 'pending':
            mark('setup', 'complete')
    else:
        raise RuntimeError('setup status is unavailable or unrecognized')
    licenses = client.call('GET', '/api/v1/licenses')
    if not isinstance(licenses, dict) or not isinstance(licenses.get('licenses'), list):
        raise RuntimeError('license status is unavailable or unrecognized')
    if is_active(licenses) and journal.get('license') == 'pending':
        raise RuntimeError('license upload may have succeeded without recording rotation; reconcile journal and marker')
    if not is_active(licenses):
        if journal.get('license') == 'pending':
            raise RuntimeError('previous license upload result is unknown; inspect FAIG before retrying')
        selected, marker = select_license(license_dir, license_regex)
        contents = selected.read_bytes()
        boundary = 'faig-' + secrets.token_hex(16)
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="license.lic"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + contents + f'\r\n--{boundary}--\r\n'.encode())
        mark('license', 'pending')
        result = client.call('POST', '/api/v1/admin/licenses', raw=body, content_type='multipart/form-data; boundary=' + boundary)
        if not isinstance(result, list) or not any(isinstance(x, dict) and x.get('status') == 'Active' for x in result):
            raise RuntimeError('license upload not confirmed Active; inspect FAIG before retrying')
        atomic_private_write(marker, selected.name + '\n')
        mark('license', 'complete')
    for i in range(max(1, attempts)):
        licenses = client.call('GET', '/api/v1/licenses')
        if is_active(licenses) and licenses.get('scanningEnabled') is True:
            break
        if i + 1 < attempts:
            sleep(delay)
    else:
        raise RuntimeError('license/scanning readiness was not confirmed; inspect FAIG before continuing')
    response = client.call('GET', '/api/v1/admin/ai-providers')
    providers = response if isinstance(response, list) else next((response[k] for k in ('items', 'providers', 'data') if isinstance(response.get(k), list)), None) if isinstance(response, dict) else None
    if providers is None:
        raise RuntimeError('provider list is unavailable or unrecognized')
    provider = next((p for p in providers if p.get('providerId') == 'litellm-direct'), None)
    if provider is None:
        if journal.get('provider') == 'pending':
            raise RuntimeError('provider creation result previously unknown; inspect FAIG before retrying')
        mark('provider', 'pending')
        client.call('POST', '/api/v1/admin/ai-providers', provider_body(key, model))
    saved = client.call('GET', '/api/v1/admin/ai-providers/litellm-direct')
    existing_model = next((m for m in saved.get('models', []) if m.get('modelId') == 'pass-model'), None)
    if not existing_model:
        raise RuntimeError('existing LiteLLM provider is missing pass-model; reconcile manually')
    expected_model = provider_body(key, model)['models'][0]
    for field in ('customizedCost', 'customInputCost', 'customOutputCost', 'customCacheReadCost', 'customCacheWriteCost'):
        if existing_model.get(field) != expected_model[field]:
            raise RuntimeError(f'pass-model catalog pricing differs at {field}; reconcile manually')
    keys = [k for k in saved.get('apiKeys', []) if k.get('enabled', True) and k.get('id')]
    if len(keys) != 1:
        raise RuntimeError('expected one enabled LiteLLM provider credential; reconcile manually')
    endpoint = saved.get('endpoint') or {}
    if endpoint.get('baseUrl') != 'http://litellm.litellm.svc.cluster.local:4000/v1':
        raise RuntimeError('existing LiteLLM provider endpoint differs; reconcile manually')
    credential = keys[0]
    masked = credential.get('apiKeyMasked')
    parts = [p for p in re.split(r'[*•.…]+', masked or '') if p]
    if not parts or not key.startswith(parts[0]) or not key.endswith(parts[-1]):
        raise RuntimeError('existing LiteLLM credential does not match the private key; reconcile manually')
    result = client.call('POST', '/api/v1/admin/ai-providers/connectivity-tests', {
        'platform': saved['platform'], 'model': 'pass-model', 'providerId': saved['providerId'],
        'endpoint': endpoint, 'draftCredentials': [{'ref': credential['id'], 'credentialId': credential['id'],
                                                    'name': credential['name'], 'enabled': True}]})
    if not (result.get('reachable') and result.get('credentialsVerified')):
        raise RuntimeError('LiteLLM pass-model connectivity/credential verification failed')
    mark('provider', 'complete')
    if smoke_key_path is not None:
        verify_governed(client, saved, existing_model, smoke_key_path, journal, mark,
                        attempts=attempts, delay=delay, sleep=sleep)
    return {'license_active': True, 'scanning_enabled': True, 'provider_verified': True,
            'governed_verified': smoke_key_path is not None}


def verify_governed(client, provider, model, key_path, journal, mark, *, attempts, delay, sleep):
    """Use a dedicated global key with only pass-model; preserve it privately."""
    from functional_test.catalog_logs import match_rows
    key_name = 'quickstart_pass-model_smoke'
    response = client.call('GET', '/api/v1/admin/virtual-keys')
    keys = response if isinstance(response, list) else next((response[k] for k in ('items', 'data') if isinstance(response.get(k), list)), None) if isinstance(response, dict) else None
    if keys is None:
        raise RuntimeError('FAIG key listing is unavailable or unrecognized')
    existing = [item for item in keys if item.get('keyName') == key_name and not item.get('revokedAt')]
    if key_path.exists():
        secret = private_json(key_path)
        if len(existing) != 1 or existing[0].get('id') != secret.get('id') or not secret.get('secretKey'):
            raise RuntimeError('smoke-key file and FAIG key do not match; reconcile manually')
    else:
        if existing or journal.get('smoke_key') == 'pending':
            raise RuntimeError('smoke-key creation may have occurred without a saved secret; reconcile manually')
        if not model.get('uuid'):
            raise RuntimeError('pass-model UUID is unavailable; cannot create smoke key')
        access = {'providerId': provider['providerId'], 'platform': provider['platform'], 'name': provider['name'],
                  'allModels': False, 'blockedModelUuids': [], 'allKeys': True, 'keys': [], 'excludedKeyIds': [],
                  'models': [{'uuid': model['uuid'], 'modelId': model['modelId'],
                              'publicName': model.get('publicName', model['modelId']), 'enabled': True}]}
        body = {'keyName': key_name, 'keyType': 'service', 'scope': 'global', 'assignedUserId': None,
                'workspaceId': None, 'projectId': None, 'policyIds': [], 'providerAccess': [access], 'modelGroups': [],
                'budgetWindows': {'hourly': None, 'daily': None, 'weekly': None, 'monthly': None},
                'tpm': None, 'rpm': None, 'expiresAt': None}
        mark('smoke_key', 'pending')
        created = client.call('POST', '/api/v1/admin/virtual-keys', body)
        if not created.get('id') or not created.get('secretKey'):
            raise RuntimeError('FAIG did not return a smoke-key secret; reconcile manually')
        secret = {'id': created['id'], 'secretKey': created['secretKey'], 'keyName': key_name}
        atomic_private_write(key_path, json.dumps(secret) + '\n')
        mark('smoke_key', 'complete')
    marker = '[faig-test-' + secrets.token_hex(16) + ']'
    since = int(time.time() * 1000) - 2000
    result = client.inference(secret['secretKey'], {'model': 'pass-model', 'messages': [
        {'role': 'user', 'content': 'Reply with one short greeting. ' + marker}], 'max_tokens': 2048})
    choices = result.get('choices') if isinstance(result, dict) else None
    if not isinstance(choices, list) or not choices or not (choices[0].get('message') or {}).get('content'):
        raise RuntimeError('governed inference returned no response text')
    for i in range(max(1, attempts)):
        response = client.call('GET', '/api/v1/admin/traffic-logs?limit=100&offset=0')
        summaries = response if isinstance(response, list) else response.get('items', []) if isinstance(response, dict) else []
        rows = match_rows(summaries, key_name=key_name, since_ms=since, marker=marker,
                          fetch_detail=lambda uid: client.call('GET', '/api/v1/admin/traffic-logs/' + uid))
        if len(rows) == 1:
            summary = next((r for r in summaries if r.get('uuid') == rows[0]['uuid']), {})
            if rows[0]['verdict'] == 'log' and summary.get('trafficType') == 'Governed':
                return
            raise RuntimeError('smoke request was not logged as governed with a Log verdict')
        if i + 1 < attempts:
            sleep(delay)
    raise RuntimeError('governed smoke request could not be matched to exactly one Traffic Log row')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', required=True)
    ap.add_argument('--setup-file', type=Path, required=True)
    ap.add_argument('--license-dir', type=Path, required=True)
    ap.add_argument('--license-regex', default=r'FAIG.*\.lic')
    ap.add_argument('--litellm-key-file', type=Path, required=True)
    ap.add_argument('--journal', type=Path, required=True)
    ap.add_argument('--smoke-key-file', type=Path, required=True)
    ap.add_argument('--insecure', action='store_true')
    args = ap.parse_args()
    setup = private_json(args.setup_file); key = private_json(args.litellm_key_file).get('api_key')
    if not key or any(not isinstance(setup.get(k), str) or not setup[k] for k in ('email', 'username', 'password', 'organization_name')):
        raise ValueError('setup or LiteLLM key file is incomplete')
    select_license(args.license_dir, args.license_regex)
    from catalog802.loader import load
    catalog, errors = load(Path(__file__).resolve().parents[1])
    if errors:
        raise ValueError('catalog validation failed: ' + '; '.join(errors))
    initialize(Client(args.url, args.insecure), setup, args.license_dir, args.license_regex, key, args.journal, catalog['models']['pass-model'], smoke_key_path=args.smoke_key_file)
    print('FAIG license active, scanning enabled, and LiteLLM pass-model connectivity verified.')
    print('Governed inference and Traffic Log verification passed.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError) as exc:
        raise SystemExit('FAIG initialization stopped: ' + str(exc)) from None
