#!/usr/bin/env python3
"""Preview or create repeated FAIG student accounts, workspaces and projects."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from credentials import select_password

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]


def expand_template(template, start, count):
    if start < 1 or count < 1:
        raise ValueError('Student start and count must be positive')
    prefix = template['student_prefix']
    domain = template['email_domain']
    suffix = template['workspace_suffix']
    projects = template['projects']
    providers = template['providers']
    if not isinstance(prefix, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', prefix):
        raise ValueError('Invalid student prefix')
    if not isinstance(domain, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*[a-z0-9]', domain):
        raise ValueError('Invalid email domain')
    if not isinstance(suffix, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', suffix):
        raise ValueError('Invalid workspace suffix')
    if not isinstance(projects, list) or not projects or any(not isinstance(p, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', p) for p in projects) or len(projects) != len(set(projects)):
        raise ValueError('Projects must be a nonempty list of unique lowercase suffixes')
    if not isinstance(providers, list) or not providers or any(not isinstance(p, str) or not p for p in providers) or len(providers) != len(set(providers)):
        raise ValueError('Providers must be a nonempty list of unique provider IDs')
    result = []
    for number in range(start, start + count):
        student = f'{prefix}{number:02d}'
        result.append({'number': number, 'student': student, 'email': f'{student}@{domain}',
                       'workspace': f'{student}_{suffix}',
                       'projects': [f'{student}_{project}' for project in projects]})
    return result


class Client:
    def __init__(self, origin, insecure):
        parsed = urllib.parse.urlsplit(origin.rstrip('/'))
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('--url must be an HTTPS origin')
        self.origin = origin.rstrip('/')
        ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=ctx))
        self.csrf = None

    def call(self, method, path, payload=None):
        headers = {'Origin': self.origin, 'Referer': self.origin + '/'}
        if self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode()
        try:
            with self.opener.open(urllib.request.Request(self.origin + path, data=data, headers=headers, method=method), timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path}: HTTP {exc.code}; response withheld') from None


def provider_bindings(providers):
    access, bindings, project_access = [], [], []
    for p in providers:
        keys = p.get('apiKeys', [])
        if not keys or any(not key.get('id') for key in keys):
            raise ValueError('Provider has no saved credential: ' + p['providerId'])
        common = {'providerId': p['providerId'], 'platform': p['platform'], 'name': p['name'],
                  'allModels': True, 'models': [], 'blockedModelUuids': []}
        project_access.append(dict(common))
        access.append({**common, 'allKeys': True, 'keys': [], 'excludedKeyIds': []})
        bindings.append({'providerId': p['providerId'], 'keyIds': [key['id'] for key in keys]})
    return access, bindings, project_access


def private_file(path):
    if path.stat().st_mode & 0o077:
        raise ValueError('Credential file must be owner-only: ' + str(path))
    return json.loads(path.read_text())


def list_users(client):
    users = []
    while True:
        response = client.call('GET', f'/api/v1/admin/users?offset={len(users)}&limit=100')
        page = response['items']
        total = response['total']
        if not isinstance(page, list) or not isinstance(total, int):
            raise ValueError('Unexpected user-list pagination response')
        users.extend(page)
        if len(users) >= total:
            return users
        if not page:
            raise ValueError('User-list pagination ended before all users were returned')


def apply_plan(args, template, plan):
    if not args.url or not args.admin_credentials or not args.credentials_dir:
        raise ValueError('Apply requires --url, --admin-credentials and --credentials-dir')
    directory = args.credentials_dir.resolve()
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError('Credentials directory must already exist and be accessible only to its owner (chmod 700)')
    if directory == REPO_ROOT or REPO_ROOT in directory.parents:
        raise ValueError('Credentials directory must be outside the Git repository')
    admin = private_file(args.admin_credentials)
    if args.password_file:
        select_password(args.password_file)
    client = Client(args.url, args.insecure)
    client.csrf = client.call('POST', '/api/v1/login', admin)['csrf_token']
    users = list_users(client)
    workspaces = client.call('GET', '/api/v1/admin/workspaces')
    projects = client.call('GET', '/api/v1/admin/projects')
    all_workspace_names = {w.get('workspaceName') for w in workspaces}
    all_project_names = {p.get('name') for p in projects}
    providers = [client.call('GET', '/api/v1/admin/ai-providers/' + urllib.parse.quote(p, safe='')) for p in template['providers']]
    access, bindings, project_access = provider_bindings(providers)
    by_email = {}
    for user in users:
        email = user.get('email')
        if email in by_email:
            raise ValueError('Duplicate user email in FAIG: ' + str(email))
        by_email[email] = user
    # Preflight all planned collisions before creating any object.
    for student in plan:
        credential = directory / (student['student'] + '.json')
        if student['workspace'] in all_workspace_names:
            raise ValueError('Workspace already exists: ' + student['workspace'])
        if any(name in all_project_names for name in student['projects']):
            raise ValueError('A planned project name already exists for ' + student['student'])
        if student['email'] in by_email:
            if not credential.exists():
                raise ValueError('Existing user requires matching owner-only credential file: ' + str(credential))
            known = private_file(credential)
            if known.get('username') != student['email'] or not known.get('password'):
                raise ValueError('Existing user requires matching owner-only credential file: ' + str(credential))
            student_client = Client(args.url, args.insecure)
            student_client.call('POST', '/api/v1/login', known)
        elif credential.exists():
            raise ValueError('Credential output already exists for new user: ' + str(credential))
    for student in plan:
        credential = directory / (student['student'] + '.json')
        if student['email'] not in by_email:
            cmd = [sys.executable, str(SCRIPT_DIR / 'onboard_user.py'), '--url', args.url,
                   '--admin-credentials', str(args.admin_credentials), '--email', student['email'],
                   '--name', 'Student ' + str(student['number']).zfill(2), '--output', str(credential)]
            if args.password_file:
                cmd += ['--password-file', str(args.password_file)]
            if args.insecure:
                cmd.append('--insecure')
            subprocess.run(cmd, check=True)
            users = list_users(client)
            matches = [u for u in users if u.get('email') == student['email']]
            if len(matches) != 1:
                raise RuntimeError('Could not uniquely retrieve created student: ' + student['email'])
            by_email[student['email']] = matches[0]
        body = {'workspaceName': student['workspace'], 'admins': [{'id': by_email[student['email']]['id']}],
                'description': template.get('workspace_description', ''), 'budget': None, 'budgetCycle': 'monthly',
                'policyIds': [], 'providerAccess': access, 'modelGroups': [], 'defaultKeyBindings': bindings}
        workspace = client.call('POST', '/api/v1/admin/workspaces', body)
        print('Created workspace:', student['workspace'], flush=True)
        for project in student['projects']:
            body = {'name': project, 'description': template.get('project_description', ''),
                    'workspaceId': workspace['id'], 'providerAccess': project_access, 'modelGroups': [],
                    'budget': None, 'policyIds': []}
            client.call('POST', '/api/v1/admin/projects', body)
            print('Created project:', project, flush=True)
        # Verify using the student's own session rather than assuming assignment succeeded.
        user_client = Client(args.url, args.insecure)
        user_client.csrf = user_client.call('POST', '/api/v1/login', private_file(credential))['csrf_token']
        memberships = user_client.call('GET', '/api/v1/me/workspaces')
        if not any(w.get('id') == workspace['id'] and w.get('membershipRole') == 'admin' for w in memberships):
            raise RuntimeError('Student login did not show an admin membership in the created workspace: ' + student['email'])
        actual_projects = client.call('GET', '/api/v1/admin/projects')
        actual_names = {p.get('name') for p in actual_projects if p.get('workspaceId') == workspace['id']}
        if not set(student['projects']).issubset(actual_names):
            raise RuntimeError('Project read-back did not match workspace: ' + student['workspace'])
        print('Verified student login, workspace admin membership and projects:', student['email'], flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template', type=Path, default=SCRIPT_DIR / 'student-template.json')
    p.add_argument('--count', type=int, required=True)
    p.add_argument('--start', type=int, default=1)
    p.add_argument('--apply', action='store_true', help='Create resources; default is offline preview')
    p.add_argument('--url')
    p.add_argument('--admin-credentials', type=Path,
                   default=Path(os.environ['FAIG_ENV_DIR']) / 'admin-login.json' if os.environ.get('FAIG_ENV_DIR') else None)
    p.add_argument('--credentials-dir', type=Path,
                   default=Path(os.environ['FAIG_ENV_DIR']) / 'students' if os.environ.get('FAIG_ENV_DIR') else None)
    p.add_argument('--password-file', type=Path, help='Optional private one-line password shared by newly created users')
    p.add_argument('--insecure', action='store_true')
    args = p.parse_args()
    template = json.loads(args.template.read_text())
    plan = expand_template(template, args.start, args.count)
    print(json.dumps({'students': plan, 'providers': template['providers'], 'policies': [], 'budgets': None}, indent=2), flush=True)
    if args.apply:
        apply_plan(args, template, plan)
    else:
        print('Preview only; no API requests made.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError, urllib.error.URLError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
