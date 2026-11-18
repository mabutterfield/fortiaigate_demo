#!/usr/bin/env python3
"""One-time local lab invitation and account registration; no email is sent by this client."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', required=True)
    ap.add_argument('--admin-credentials', required=True, type=Path)
    ap.add_argument('--email', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--insecure', action='store_true')
    args = ap.parse_args()
    origin = args.url.rstrip('/')
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        ap.error('--url must be an HTTPS origin')
    if args.output.exists() or not args.output.parent.is_dir():
        ap.error('Output must be a new file in an existing directory')
    if args.admin_credentials.stat().st_mode & 0o077:
        ap.error('Admin credential file must be owner-only (chmod 600)')
    credentials = json.loads(args.admin_credentials.read_text())
    context = ssl._create_unverified_context() if args.insecure else ssl.create_default_context()

    def client():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=context))

    def call(opener, method, path, body=None, csrf=None):
        headers = {'Origin': origin, 'Referer': origin + '/'}
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body).encode()
        if csrf:
            headers['X-CSRF-Token'] = csrf
        request = urllib.request.Request(origin + path, data=data, headers=headers, method=method)
        try:
            with opener.open(request, timeout=30) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            # Do not expose the invitation path or response body.
            raise RuntimeError(f'{method} {path.split("/invitations/")[0]}: HTTP {exc.code}') from None

    administrator = client()
    _, login = call(administrator, 'POST', '/api/v1/login', credentials)
    _, invite = call(administrator, 'POST', '/api/v1/admin/user-invitations', {'orgRole': 'org_member', 'emails': [args.email]}, login['csrf_token'])
    invitation_id = invite['id']
    print('Invitation created for', args.email, flush=True)

    # Independent browser-equivalent session: no administrator cookies or token.
    new_user = client()
    invitation_path = '/api/v1/invitations/' + urllib.parse.quote(invitation_id, safe='')
    call(new_user, 'GET', invitation_path)
    try:
        call(new_user, 'GET', '/api/v1/csrf-token')
        print('Anonymous CSRF endpoint responded successfully.', flush=True)
    except RuntimeError as exc:
        if 'HTTP 401' not in str(exc):
            raise
        print('Anonymous CSRF returned 401; continuing without a token.', flush=True)
    _, identity = call(new_user, 'POST', invitation_path + '/identify', {'email': args.email})
    if identity.get('outcome') != 'needs-registration':
        raise RuntimeError('Unexpected invitation identify outcome; invitation remains pending')
    password = 'Aa1!' + secrets.token_urlsafe(27)
    _, strength = call(new_user, 'POST', invitation_path + '/password/strength', {'password': password})
    if not strength.get('isStrong'):
        raise RuntimeError('Generated password did not satisfy strength policy; invitation remains pending')
    _, result = call(new_user, 'POST', invitation_path + '/accept', {'email': args.email, 'displayName': args.name, 'password': password})
    if result.get('createdAccount') is not True:
        raise RuntimeError('Acceptance did not report a newly created account; inspect FAIG')
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump({'username': args.email, 'password': password}, output)
    except OSError:
        raise RuntimeError('Account was created but credentials could not be saved; reset its password') from None
    print('Account created; credentials saved to', args.output, flush=True)
    independent_login = client()
    _, auth = call(independent_login, 'POST', '/api/v1/login', {'username': args.email, 'password': password})
    print('Independent login succeeded; role:', auth.get('role'), flush=True)
    _, workspaces = call(independent_login, 'GET', '/api/v1/me/workspaces')
    print('Workspace memberships:', len(workspaces), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
