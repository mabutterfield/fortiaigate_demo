#!/usr/bin/env python3
"""Small interactive FAIG JSON resource runner for an isolated lab."""
import argparse
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

KINDS = {
    'provider': ('/api/v1/admin/ai-providers', 'providerId', 'providerId'),
    'detector': ('/api/v1/admin/detectors', 'uuid', 'name'),
    'guardrail': ('/api/v1/admin/guardrails', 'id', 'name'),
    'policy': ('/api/v1/admin/policies', 'id', 'name'),
    'key': ('/api/v1/admin/virtual-keys', 'id', 'keyName'),
    'workspace': ('/api/v1/admin/workspaces', 'id', 'workspaceName'),
}
SENSITIVE = {'password', 'apikey', 'secretkey', 'csrf_token', 'authorization', 'token'}


def private_write(path, value):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(value)


def hidden(value):
    if isinstance(value, dict):
        return {k: '<hidden>' if k.lower() in SENSITIVE else hidden(v) for k, v in value.items()}
    if isinstance(value, list):
        return [hidden(v) for v in value]
    return value


def field(value, path):
    for part in path.split('.'):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def resolve(value, objects, variables, secrets):
    if isinstance(value, list):
        return [resolve(x, objects, variables, secrets) for x in value]
    if isinstance(value, dict):
        if set(value) == {'$ref'}:
            resource, path = value['$ref'].split('.', 1)
            return field(objects[resource], path)
        if set(value) == {'$var'}:
            return variables[value['$var']]
        if set(value) == {'$secret'}:
            name = value['$secret']
            if name not in secrets:
                secrets[name] = getpass.getpass(name + ' (hidden): ')
            return secrets[name]
        return {k: resolve(v, objects, variables, secrets) for k, v in value.items()}
    return value


def pause(message):
    print('\n' + message, flush=True)
    answer = input('Enter to continue; q to stop: ').strip().lower()
    if answer == 'q':
        raise SystemExit('Stopped. Previously created objects remain in FAIG.')
    if answer:
        raise SystemExit('Unexpected input; stopped before this step.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['apply', 'get', 'validate'])
    ap.add_argument('config', type=Path)
    ap.add_argument('--url', required=True, help='HTTPS origin')
    ap.add_argument('--insecure', action='store_true', help='Trust the lab self-signed certificate')
    ap.add_argument('--credentials', type=Path, help='Owner-only JSON file containing username and password')
    ap.add_argument('--yes', action='store_true', help='Skip request confirmation prompts')
    ap.add_argument('--key-dir', type=Path, default=Path.home() / '.faig-api-keys')
    args = ap.parse_args()
    if args.yes:
        global pause
        pause = lambda message: print('\n' + message, flush=True)
    config = json.loads(args.config.read_text())
    origin = args.url.rstrip('/')
    url = urllib.parse.urlsplit(origin)
    if url.scheme != 'https' or not url.netloc or url.path or url.query or url.fragment:
        ap.error('--url must be an HTTPS origin')
    specs = config['resources']
    names = [x['name'] for x in specs]
    if len(set(names)) != len(names) or any(x['kind'] not in KINDS for x in specs):
        ap.error('Duplicate resource names or unsupported kind')
    if args.command == 'apply' and any(x['kind'] == 'key' and x.get('operation') == 'create' for x in specs):
        if not args.key_dir.is_dir():
            ap.error('Create the key directory first; it must already exist')
        for spec in specs:
            if spec['kind'] == 'key' and spec.get('operation') == 'create':
                path = args.key_dir / (spec['name'] + '.key')
                if path.exists():
                    ap.error('Key output already exists: ' + str(path))
    ctx = ssl._create_unverified_context() if args.insecure else ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=ctx))
    csrf = None

    def call(method, path, payload=None):
        headers = {'Origin': origin, 'Referer': origin + '/'}
        if csrf:
            headers['X-CSRF-Token'] = csrf
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode()
        request = urllib.request.Request(origin + path, data=data, headers=headers, method=method)
        try:
            with opener.open(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path} returned HTTP {exc.code}; response body withheld') from None

    pause('Log in to ' + origin + '?')
    if args.credentials:
        if args.credentials.stat().st_mode & 0o077:
            ap.error('Credential file must be accessible only to its owner (chmod 600)')
        credentials = json.loads(args.credentials.read_text())
        username, password = credentials['username'], credentials['password']
    else:
        username = input('FAIG administrator username: ')
        password = getpass.getpass('FAIG administrator password (hidden): ')
    csrf = call('POST', '/api/v1/login', {'username': username, 'password': password})['csrf_token']
    password = None
    objects, secrets, errors = {}, {}, []
    variables = config.get('variables', {})
    for spec in specs:
        name, kind = spec['name'], spec['kind']
        endpoint, id_field, name_field = KINDS[kind]
        operation = spec.get('operation', 'create')
        if operation not in ('create', 'existing', 'add_models'):
            raise ValueError('Unsupported operation: ' + operation)
        if operation == 'add_models' and kind != 'provider':
            raise ValueError('add_models is only supported for providers')
        lookup = resolve(spec['lookup'], objects, variables, secrets)
        pause(f'GET {endpoint}: locate {kind} {lookup!r}?')
        matches = [x for x in call('GET', endpoint) if x.get(name_field) == lookup]
        if len(matches) > 1:
            raise RuntimeError(f'{name}: ambiguous name; stopping')
        if args.command == 'apply' and operation == 'add_models':
            if not matches:
                raise RuntimeError(f'{name}: provider not found')
            detail_path = endpoint + '/' + urllib.parse.quote(matches[0][id_field], safe='')
            pause(f'GET {detail_path}: read current provider before update?')
            current = call('GET', detail_path)
            required = ['providerId', 'platform', 'name', 'endpoint', 'description', 'autoSyncNewModels', 'apiKeys', 'models', 'updatedAt']
            if any(k not in current for k in required):
                raise RuntimeError(f'{name}: provider detail is missing fields required for safe update')
            credential_fields = ('id', 'name', 'enabled', 'weight')
            model_fields = ('uuid', 'modelId', 'publicName', 'enabled', 'isCustom', 'description', 'customizedCost', 'customInputCost', 'customOutputCost', 'customCacheReadCost', 'customCacheWriteCost')
            payload = {k: current[k] for k in required}
            payload['apiKeys'] = [{k: entry[k] for k in credential_fields if k in entry} for entry in current['apiKeys']]
            if any('id' not in entry for entry in payload['apiKeys']):
                raise RuntimeError(f'{name}: an existing credential has no ID; refusing update')
            payload['models'] = [{k: entry[k] for k in model_fields if k in entry} for entry in current['models']]
            added = resolve(spec['models'], objects, variables, secrets)
            for model in added:
                if any(x.get('modelId') == model.get('modelId') or x.get('publicName') == model.get('publicName') for x in payload['models']):
                    raise RuntimeError(f'{name}: model already exists; no update attempted')
                payload['models'].append(model)
            print(json.dumps(hidden(payload), indent=2), flush=True)
            pause(f'PUT {detail_path}: update provider including existing credentials and models?')
            call('PUT', detail_path, payload)
            print('Updated provider:', name, flush=True)
        if args.command == 'apply' and operation == 'create':
            if matches:
                raise RuntimeError(f'{name}: already exists; no update attempted')
            payload = resolve(spec['body'], objects, variables, secrets)
            print(json.dumps(hidden(payload), indent=2), flush=True)
            pause(f'POST {endpoint}: create {name}?')
            created = call('POST', endpoint, payload)
            print('Created', name, '| ID:', created.get(id_field), flush=True)
            if kind == 'key':
                secret = created.pop('secretKey', None)
                if not secret:
                    raise RuntimeError('Key created without secretKey; inspect FAIG')
                output = args.key_dir / (name + '.key')
                try:
                    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'w') as f:
                        f.write(secret)
                except OSError:
                    raise RuntimeError('Key created but could not be saved; revoke or rotate it') from None
                print('Saved key securely to', output, flush=True)
            objects[name] = created
            pause(f'GET {endpoint}: verify {name}?')
            matches = [x for x in call('GET', endpoint) if x.get(id_field) == created.get(id_field)]
        if not matches:
            errors.append(name + ': not found')
            print('NOT FOUND:', name, flush=True)
            continue
        obj = matches[0]
        if kind == 'provider':
            pause(f'GET {endpoint}/{obj[id_field]}: retrieve provider details?')
            obj = call('GET', endpoint + '/' + urllib.parse.quote(obj[id_field], safe=''))
        objects[name] = obj
        print('FOUND', name, '| ID:', obj.get(id_field), flush=True)
        if args.command in ('validate', 'apply'):
            for check in spec.get('checks', []):
                expected = resolve(check.get('equals', check.get('contains')), objects, variables, secrets)
                try:
                    actual = field(obj, check['field'])
                except (KeyError, IndexError, TypeError):
                    actual = '<missing>'
                if check.get('unordered') and isinstance(actual, list) and isinstance(expected, list):
                    good = sorted(actual) == sorted(expected)
                elif 'contains' in check and isinstance(actual, list):
                    good = any(all(item.get(k) == v for k, v in expected.items()) for item in actual if isinstance(item, dict)) if isinstance(expected, dict) else expected in actual
                else:
                    good = actual == expected
                print(('PASS ' if good else 'FAIL ') + name + '.' + check['field'], flush=True)
                if not good:
                    print('  expected:', json.dumps(hidden(expected)), '| actual:', json.dumps(hidden(actual)), flush=True)
                    errors.append(name + '.' + check['field'])
        if args.command == 'get':
            print(json.dumps(hidden(obj), indent=2), flush=True)
    if errors:
        raise RuntimeError('Unresolved checks: ' + ', '.join(errors))
    print('\nFinished:', args.command, flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError, TypeError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
