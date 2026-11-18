#!/usr/bin/env python3
"""Per-student FAIG scenario keys: one virtual key per scenario action.

Two workflows share this module:

  prepopulate   Admin-run. Uses each student's saved credentials to create that
                student's workspace detectors, guardrails, policies and one key
                per scenario action, approving each layer as the org admin.
  auto-approve  Admin-run. Approves workspace submissions from student
                workspaces only, in dependency order, so students can build
                their own objects in the GUI or API.

Both default to a preview; pass --apply to make changes. Observed GUI APIs
for FAIG 8.0.2; not a supported vendor interface.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from credentials import write_new_private_json
from student_lab import Client as BaseClient, REPO_ROOT, SCRIPT_DIR, expand_template, private_file

DEFAULT_CATALOG = SCRIPT_DIR / 'scenario-catalog.json'
DEFAULT_TEMPLATE = SCRIPT_DIR / 'student-template.json'
APPROVAL_ORDER = {'detector': 0, 'guardrail': 1, 'policy': 2}
ADMIN_APPROVE = {'detector': '/api/v1/admin/detectors/{}/approve',
                 'guardrail': '/api/v1/admin/guardrails/{}/approve',
                 'policy': '/api/v1/admin/policies/{}/approve'}
NAME_RE = re.compile(r'[a-z0-9][a-z0-9_-]*')


class ApiError(RuntimeError):
    def __init__(self, method, path, status, detail):
        super().__init__(f'{method} {path}: HTTP {status}' + (f'; {detail}' if detail else ''))
        self.status = status


class Client(BaseClient):
    """Client that reports FAIG validation messages but never request bodies."""

    def call(self, method, path, payload=None):
        headers = {'Origin': self.origin, 'Referer': self.origin + '/'}
        if self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode()
        request = urllib.request.Request(self.origin + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise ApiError(method, path, exc.code, error_detail(exc.read())) from None

    def login(self, credentials):
        self.csrf = self.call('POST', '/api/v1/login', {'username': credentials['username'],
                                                        'password': credentials['password']})['csrf_token']
        return self


def error_detail(raw):
    """Return only FAIG's `error`/`field` validation text from an error body."""
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        return ''
    if not isinstance(body, dict):
        return ''
    error = body.get('error')
    if isinstance(error, dict):
        error = error.get('message')
    parts = [str(error)] if error else []
    if body.get('field'):
        parts.append('field=' + str(body['field']))
    return ' '.join(parts)[:300]


def items(response):
    if isinstance(response, dict):
        for key in ('items', 'providers', 'data'):
            if isinstance(response.get(key), list):
                return response[key]
    return response if isinstance(response, list) else []


def object_id(obj):
    return obj.get('uuid') or obj.get('id')


def review_status(obj):
    """Guardrails and policies report `status`; workspace detectors report `approvalStatus`."""
    status = obj.get('status') or obj.get('approvalStatus')
    return 'active' if status == 'approved' else status


# ---------------------------------------------------------------- catalog

def load_catalog(path=DEFAULT_CATALOG, repo_root=REPO_ROOT):
    catalog = json.loads(Path(path).read_text())
    entries = []
    for scenario, spec in catalog['scenarios'].items():
        profile = json.loads((Path(repo_root) / spec['profile']).read_text())
        if profile.get('id') != scenario:
            raise ValueError(f'Profile id does not match catalog scenario: {scenario}')
        for point in profile['matrix']['entry_points']:
            template = point['guard_template']
            if template not in catalog['guard_templates']:
                raise ValueError(f'No guard template mapping for {scenario}/{point["action"]}: {template}')
            entries.append({'scenario': scenario, 'action': point['action'], 'guard_template': template,
                            'model': spec['model'], 'display_name': point.get('display_name', point['action'])})
    for name, template in catalog['guard_templates'].items():
        for detector in template.get('detectors', []):
            if detector not in catalog['detectors']:
                raise ValueError(f'Guard template {name} references unknown detector {detector}')
        if template.get('direction') not in ('input', 'output', 'both'):
            raise ValueError(f'Guard template {name} needs direction input, output or both')
    catalog['entries'] = entries
    return catalog


def select_entries(entries, scenarios=None, actions=None):
    known_scenarios = {e['scenario'] for e in entries}
    known_actions = {e['action'] for e in entries}
    for value, known, label in ((scenarios, known_scenarios, 'scenario'), (actions, known_actions, 'action')):
        unknown = set(value or []) - known
        if unknown:
            raise ValueError(f'Unknown {label}: {", ".join(sorted(unknown))}')
    return [e for e in entries if (not scenarios or e['scenario'] in scenarios)
            and (not actions or e['action'] in actions)]


def object_names(student, entry):
    base = f'{student}-{entry["scenario"]}-{entry["action"]}'
    return {'guardrail': base + '-guardrail', 'policy': base + '-policy', 'key': base,
            'project': f'{student}_{entry["scenario"]}'}


def detector_name(student, detector_key):
    return f'{student}-{detector_key}'


def needed_detectors(catalog, entries):
    keys = []
    for entry in entries:
        for key in catalog['guard_templates'][entry['guard_template']].get('detectors', []):
            if key not in keys:
                keys.append(key)
    return keys


# ---------------------------------------------------------------- bodies

def _rid():
    return 'policy-' + secrets.token_hex(5)


def ai_copy_body(builtin, name, description, action):
    """Copy a built-in AI detector's rules, as the GUI's duplicate flow does."""
    ai_rules, flat = [], []
    for rule in builtin['rules']:
        conditions = [{'id': _rid(), 'description': text} for text in rule.get('violateIf', [])]
        flat.extend({'id': _rid(), 'description': c['description']} for c in conditions)
        ai_rules.append({'id': _rid(), 'name': rule['name'], 'description': rule.get('description', ''),
                         'enabled': rule.get('enabled', True), 'violateIf': list(rule.get('violateIf', [])),
                         'exemptIf': list(rule.get('exemptIf', [])), 'conditions': conditions})
    return {'name': name, 'description': description, 'inputGuards': ['AI descriptions'],
            'outputGuards': ['AI descriptions'], 'sensitivity': None, 'detectorType': 'ai',
            'managedEngine': None, 'action': action, 'regexRules': None, 'aiRules': ai_rules, 'rules': flat}


def dlp_body(name, description, disposition, categories):
    rules = []
    for number, category in enumerate(categories, 1):
        rule = {'id': f'r{number}', 'disposition': disposition, 'category': category, 'threshold': 0.7}
        if disposition == 'redact':
            rule['replacement'] = '[REDACTED_' + re.sub(r'[^A-Z0-9]+', '_', category.upper()).strip('_') + ']'
        rules.append(rule)
    return {'name': name, 'description': description, 'inputGuards': list(categories),
            'outputGuards': list(categories), 'sensitivity': None, 'detectorType': 'managed',
            'managedEngine': 'dlp', 'action': None, 'rules': rules, 'regexRules': None, 'aiRules': None}


def guardrail_body(name, description, detector_ids, deny_suspicious):
    return {'name': name, 'description': description, 'detectorIds': list(detector_ids),
            'denySuspiciousCharacters': bool(deny_suspicious)}


def model_access(provider, model, with_keys):
    access = {'providerId': provider['providerId'], 'platform': provider['platform'], 'name': provider['name'],
              'allModels': False, 'blockedModelUuids': [],
              'models': [{'uuid': model['uuid'], 'modelId': model['modelId'],
                          'publicName': model.get('publicName', model['modelId']), 'enabled': True}]}
    if with_keys:
        access.update({'allKeys': True, 'keys': [], 'excludedKeyIds': []})
    return access


def policy_body(name, description, guardrail_id, direction, provider, model):
    return {'name': name, 'description': description,
            'inputGuardrailIds': [guardrail_id] if direction in ('input', 'both') else [],
            'outputGuardrailIds': [guardrail_id] if direction in ('output', 'both') else [],
            'responseScanMode': 'post_stream', 'providerAccess': [model_access(provider, model, False)]}


def key_body(name, workspace_id, project_id, policy_id, provider, model):
    # Unlimited budget, no tpm/rpm limit and no expiry; see README.
    return {'keyName': name, 'keyType': 'user', 'scope': 'workspace', 'workspaceId': workspace_id,
            'projectId': project_id, 'policyIds': [policy_id],
            'providerAccess': [model_access(provider, model, True)], 'modelGroups': [],
            'budgetWindows': {'hourly': None, 'daily': None, 'weekly': None, 'monthly': None},
            'tpm': None, 'rpm': None, 'expiresAt': None}


# ---------------------------------------------------------------- workflow 1

class Prepopulate:
    def __init__(self, admin, student_client, student, catalog, entries, key_dir, out=print):
        self.admin, self.user, self.student = admin, student_client, student
        self.catalog, self.entries, self.key_dir, self.out = catalog, entries, key_dir, out

    def run(self):
        s = self.student
        workspace = next((w for w in items(self.user.call('GET', '/api/v1/me/workspaces'))
                          if w.get('workspaceName') == s['workspace']), None)
        if not workspace:
            raise RuntimeError(f'{s["student"]} is not a member of {s["workspace"]}')
        self.wid = workspace['id']
        self.base = f'/api/v1/workspaces/{self.wid}'
        provider_id = self.catalog['provider']
        provider = next((p for p in items(self.user.call('GET', self.base + '/grantable-providers'))
                         if p.get('providerId') == provider_id), None)
        if not provider:
            raise RuntimeError(f'{s["workspace"]} has no access to provider {provider_id}')
        models = {m['modelId']: m for m in provider.get('models', [])
                  if m.get('effectiveEnabled', m.get('enabled', True)) is not False}
        entries = []
        for entry in self.entries:
            if entry['model'] in models:
                entries.append(entry)
            else:
                self.out(f'  skip {entry["scenario"]}/{entry["action"]}: model {entry["model"]} is not available '
                         f'from {provider_id} (deploy the LiteLLM alias and add it to the provider)')
        if not entries:
            return []
        projects = self.ensure_projects(entries, provider_id)
        detectors = self.ensure_layer('detector', self.detector_specs(entries))
        guardrails = self.ensure_layer('guardrail', self.guardrail_specs(entries, detectors))
        policies = self.ensure_layer('policy', self.policy_specs(entries, guardrails, provider, models))
        return self.ensure_keys(entries, projects, policies, provider, models)

    # Projects belong to the admin workflow; create only those missing.
    def ensure_projects(self, entries, provider_id):
        existing = {p['name']: p for p in items(self.user.call('GET', self.base + '/projects'))}
        result = {}
        for name in dict.fromkeys(object_names(self.student['student'], e)['project'] for e in entries):
            if name not in existing:
                p = self.admin.call('GET', '/api/v1/admin/ai-providers/' + urllib.parse.quote(provider_id, safe=''))
                body = {'name': name, 'description': 'Student scenario project', 'workspaceId': self.wid,
                        'providerAccess': [{'providerId': p['providerId'], 'platform': p['platform'], 'name': p['name'],
                                            'allModels': True, 'models': [], 'blockedModelUuids': []}],
                        'modelGroups': [], 'budget': None, 'policyIds': []}
                existing[name] = self.admin.call('POST', '/api/v1/admin/projects', body)
                self.out(f'  created project {name}')
            result[name] = existing[name]['id']
        return result

    def detector_specs(self, entries):
        builtins = None
        specs = []
        for key in needed_detectors(self.catalog, entries):
            spec = self.catalog['detectors'][key]
            name = detector_name(self.student['student'], key)
            if spec['kind'] == 'ai_copy':
                if builtins is None:
                    builtins = {b['id']: b for b in items(self.user.call('GET', self.base + '/built-in-detectors'))}
                if spec['source'] not in builtins:
                    raise RuntimeError('Built-in detector not found: ' + spec['source'])
                body = ai_copy_body(builtins[spec['source']], name, spec['description'], spec['action'])
            elif spec['kind'] == 'dlp':
                body = dlp_body(name, spec['description'], spec['disposition'], spec['categories'])
            else:
                raise ValueError('Unsupported detector kind: ' + spec['kind'])
            specs.append((key, name, body))
        return specs

    def guardrail_specs(self, entries, detectors):
        specs = []
        for entry in entries:
            template = self.catalog['guard_templates'][entry['guard_template']]
            ids = [detectors[k] for k in template.get('detectors', [])] + list(template.get('builtin_detectors', []))
            name = object_names(self.student['student'], entry)['guardrail']
            body = guardrail_body(name, f'{entry["scenario"]} {entry["action"]} ({entry["guard_template"]})', ids,
                                  template.get('deny_suspicious_characters', False))
            specs.append((name, name, body))
        return specs

    def policy_specs(self, entries, guardrails, provider, models):
        specs = []
        for entry in entries:
            names = object_names(self.student['student'], entry)
            template = self.catalog['guard_templates'][entry['guard_template']]
            body = policy_body(names['policy'], f'{entry["scenario"]} {entry["action"]}', guardrails[names['guardrail']],
                               template['direction'], provider, models[entry['model']])
            specs.append((names['policy'], names['policy'], body))
        return specs

    def ensure_layer(self, kind, specs):
        """Create/submit each object as the student, then approve pending ones as admin."""
        if not specs:
            return {}
        collection = self.base + {'detector': '/detectors', 'guardrail': '/guardrails', 'policy': '/policies'}[kind]
        existing = {o.get('name'): o for o in items(self.user.call('GET', collection))}
        result, pending = {}, {}
        for key, name, body in specs:
            obj = existing.get(name)
            if obj is None:
                obj = self.user.call('POST', collection, body)
                self.out(f'  created {kind} {name}')
            status = review_status(obj)
            if status == 'rejected':
                raise RuntimeError(f'{kind} {name} was rejected: {obj.get("rejectionReason")}')
            if status == 'draft':
                obj = self.user.call('POST', f'{collection}/{object_id(obj)}/submit')
                self.out(f'  submitted {kind} {name}')
                status = review_status(obj)
            if status == 'pending' or obj.get('hasPendingChange'):
                pending[object_id(obj)] = name
            elif status != 'active':
                raise RuntimeError(f'{kind} {name} has unexpected status {status}')
            result[key] = object_id(obj)
        if pending:
            queue = {i['id'] for i in items(self.admin.call('GET', '/api/v1/admin/review-queue')) if i.get('type') == kind}
            for oid, name in pending.items():
                if oid not in queue:
                    raise RuntimeError(f'{kind} {name} is pending but not in the admin review queue')
                self.admin.call('POST', ADMIN_APPROVE[kind].format(oid))
                self.out(f'  approved {kind} {name}')
        return result

    def ensure_keys(self, entries, projects, policies, provider, models):
        existing = {k.get('keyName') for k in items(self.user.call('GET', '/api/v1/me/virtual-keys'))}
        created = []
        for entry in entries:
            names = object_names(self.student['student'], entry)
            path = self.key_dir / (names['key'] + '.json')
            if names['key'] in existing:
                note = '' if path.exists() else ' (no local secret file; rotate or delete it to obtain a new secret)'
                self.out(f'  key {names["key"]} exists{note}')
                continue
            if path.exists():
                raise RuntimeError(f'Secret file exists for a key FAIG does not list: {path}')
            body = key_body(names['key'], self.wid, projects[names['project']], policies[names['policy']],
                            provider, models[entry['model']])
            response = self.user.call('POST', '/api/v1/me/virtual-keys', body)
            secret = response.get('secretKey')
            if not secret:
                raise RuntimeError(f'FAIG did not return a secret for {names["key"]}')
            write_new_private_json(path, {
                'student': self.student['student'], 'workspace': self.student['workspace'],
                'scenario': entry['scenario'], 'action': entry['action'], 'model': entry['model'],
                'keyName': names['key'], 'keyId': response.get('id'), 'policy': names['policy'],
                'project': names['project'], 'basePath': self.catalog['gateway_base_path'], 'secretKey': secret})
            self.out(f'  created key {names["key"]} -> {path}')
            created.append(names['key'])
        return created


def private_dir(path, create=False):
    path = Path(path).resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise ValueError('Credentials and key directories must be outside the Git repository')
    if create and not path.exists():
        os.mkdir(path, 0o700)
    if not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError(f'Directory must exist and be owner-only (chmod 700): {path}')
    return path


def cmd_prepopulate(args):
    catalog = load_catalog(args.catalog)
    entries = select_entries(catalog['entries'], args.scenario, args.action)
    template = json.loads(args.template.read_text())
    students = expand_template(template, args.start, args.count)
    for s in students:
        print(f'{s["student"]} ({s["workspace"]}):')
        for d in needed_detectors(catalog, entries):
            print('  detector ', detector_name(s['student'], d))
        for e in entries:
            n = object_names(s['student'], e)
            print(f'  {e["scenario"]}/{e["action"]}: guardrail {n["guardrail"]}, policy {n["policy"]}, '
                  f'key {n["key"]}, project {n["project"]}, model {e["model"]}')
    if not args.apply:
        print('Preview only; no API requests made.')
        return
    if not (args.url and args.admin_credentials and args.credentials_dir):
        raise ValueError('--apply requires --url, --admin-credentials and --credentials-dir')
    cred_dir = private_dir(args.credentials_dir)
    admin = Client(args.url, args.insecure).login(private_file(args.admin_credentials))
    for s in students:
        print(f'Applying {s["student"]}:', flush=True)
        cred = cred_dir / (s['student'] + '.json')
        if not cred.exists():
            raise ValueError(f'Missing owner-only student credential file: {cred}')
        user = Client(args.url, args.insecure).login(private_file(cred))
        key_dir = private_dir(cred_dir / (s['student'] + '-keys'), create=True)
        Prepopulate(admin, user, s, catalog, entries, key_dir,
                    out=lambda m: print(m, flush=True)).run()


# ---------------------------------------------------------------- workflow 2

def student_workspace_pattern(template):
    return re.compile(rf'^{re.escape(template["student_prefix"])}\d{{2,}}_{re.escape(template["workspace_suffix"])}$')


def approvable(queue, workspace_names, types, include_deletes=False):
    """Queue items from student workspaces, in detector -> guardrail -> policy order."""
    chosen = []
    for item in queue:
        if item.get('ownerWorkspaceId') not in workspace_names or item.get('type') not in types:
            continue
        if item.get('changeKind') == 'delete' and not include_deletes:
            continue
        chosen.append(item)
    return sorted(chosen, key=lambda i: (APPROVAL_ORDER.get(i['type'], 9), i.get('submittedAt') or ''))


def cmd_auto_approve(args):
    template = json.loads(args.template.read_text())
    pattern = student_workspace_pattern(template)
    types = set(args.types)
    if not args.url or not args.admin_credentials:
        raise ValueError('auto-approve requires --url and --admin-credentials')
    admin = Client(args.url, args.insecure).login(private_file(args.admin_credentials))
    mode = 'Approving' if args.apply else 'Would approve (preview; pass --apply)'
    while True:
        workspaces = {w['id']: w['workspaceName'] for w in items(admin.call('GET', '/api/v1/admin/workspaces'))
                      if pattern.match(w.get('workspaceName') or '')}
        for item in approvable(items(admin.call('GET', '/api/v1/admin/review-queue')), workspaces, types,
                               args.include_deletes):
            label = (f'{item["type"]} {item.get("name")} [{item.get("changeKind")}] from '
                     f'{workspaces[item["ownerWorkspaceId"]]} by {(item.get("submittedBy") or {}).get("email")}')
            if args.apply:
                try:
                    admin.call('POST', ADMIN_APPROVE[item['type']].format(item['id']))
                    print('Approved', label, flush=True)
                except ApiError as exc:
                    print('Could not approve', label, '-', exc, flush=True)
            else:
                print(mode + ':', label, flush=True)
        if not args.watch:
            return
        time.sleep(args.watch)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, helptext in (('prepopulate', 'Workflow 1: build and approve student scenario objects and keys'),
                           ('auto-approve', 'Workflow 2: approve student workspace submissions')):
        p = sub.add_parser(name, help=helptext)
        p.add_argument('--template', type=Path, default=DEFAULT_TEMPLATE)
        p.add_argument('--url')
        p.add_argument('--admin-credentials', type=Path)
        p.add_argument('--insecure', action='store_true', help='Skip TLS verification (isolated lab only)')
        p.add_argument('--apply', action='store_true', help='Make changes; default is preview')
    pre = sub.choices['prepopulate']
    pre.add_argument('--catalog', type=Path, default=DEFAULT_CATALOG)
    pre.add_argument('--count', type=int, required=True)
    pre.add_argument('--start', type=int, default=1)
    pre.add_argument('--scenario', action='append', help='Limit to a scenario (repeatable); default all')
    pre.add_argument('--action', action='append', help='Limit to an action (repeatable); default all')
    pre.add_argument('--credentials-dir', type=Path,
                     help='Owner-only directory with studentNN.json; keys go to studentNN-keys/')
    auto = sub.choices['auto-approve']
    auto.add_argument('--types', nargs='+', default=['detector', 'guardrail', 'policy'],
                      choices=sorted(APPROVAL_ORDER))
    auto.add_argument('--include-deletes', action='store_true', help='Also approve deletion requests')
    auto.add_argument('--watch', type=int, default=0, metavar='SECONDS', help='Repeat every N seconds')
    args = parser.parse_args()
    if args.command == 'prepopulate':
        cmd_prepopulate(args)
    else:
        cmd_auto_approve(args)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
