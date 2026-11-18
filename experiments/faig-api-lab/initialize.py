#!/usr/bin/env python3
"""Initialize a fresh FAIG 8.0.2 lab and upload one rotating license."""
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


def choose_license(directory):
    licenses = sorted(p for p in directory.glob('FAIG*.lic') if p.is_file())
    if not licenses:
        raise ValueError('No FAIG*.lic files found in license directory')
    marker = directory / '.last-used'
    if not marker.exists():
        return licenses[0], marker
    previous = marker.read_text().strip()
    names = [p.name for p in licenses]
    if previous not in names:
        raise ValueError('Last-used license is missing; resolve the .last-used record before continuing')
    return licenses[(names.index(previous) + 1) % len(licenses)], marker


def record_license(marker, name):
    temp = marker.with_name(marker.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(name + '\n')
        os.replace(temp, marker)
    finally:
        temp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', required=True, help='FAIG HTTPS origin, also used as externalUrl')
    ap.add_argument('--setup-file', type=Path, required=True, help='Owner-only JSON: email, username, password, organization_name')
    ap.add_argument('--licenses', type=Path, required=True, help='Directory containing FAIG*.lic')
    ap.add_argument('--license-only', action='store_true', help='Recover a failed upload using the existing administrator account')
    ap.add_argument('--insecure', action='store_true', help='Accept the isolated lab self-signed certificate')
    args = ap.parse_args()
    origin = args.url.rstrip('/')
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        ap.error('--url must be an HTTPS origin')
    if args.setup_file.stat().st_mode & 0o077:
        ap.error('Setup file must be owner-only (chmod 600)')
    setup = json.loads(args.setup_file.read_text())
    fields = ('email', 'username', 'password', 'organization_name')
    if any(not isinstance(setup.get(k), str) or not setup[k] for k in fields):
        ap.error('Setup file needs non-empty email, username, password, organization_name')
    license_file, marker = choose_license(args.licenses)
    data = license_file.read_bytes()
    if not data:
        raise ValueError('Selected license is empty')
    context = ssl._create_unverified_context() if args.insecure else ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=context))

    def call(method, path, body=None, content_type=None, csrf=None):
        headers = {'Origin': origin, 'Referer': origin + '/'}
        if content_type:
            headers['Content-Type'] = content_type
        if csrf:
            headers['X-CSRF-Token'] = csrf
        req = urllib.request.Request(origin + path, data=body, headers=headers, method=method)
        try:
            with opener.open(req, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path}: HTTP {exc.code}; response withheld') from None

    status = call('GET', '/api/v1/setup-status')
    if args.license_only:
        if status.get('needs_setup') is not False:
            raise RuntimeError('FAIG setup is not complete; no changes made')
        payload = {'username': setup['email'], 'password': setup['password']}
        result = call('POST', '/api/v1/login', json.dumps(payload).encode(), 'application/json')
    else:
        if status.get('needs_setup') is not True:
            raise RuntimeError('FAIG is not awaiting initial setup; no changes made')
        payload = {k: setup[k] for k in fields}
        payload['externalUrl'] = origin
        result = call('POST', '/api/v1/setup', json.dumps(payload).encode(), 'application/json')
    csrf = result.get('csrf_token')
    if not csrf:
        raise RuntimeError('Setup returned no CSRF token; inspect FAIG before retrying')
    print('Administrator authenticated.' if args.license_only else 'Initial administrator and organization created.', flush=True)
    boundary = 'faig-' + secrets.token_hex(16)
    # The license filename is fixed on the wire; no local path or file content is logged.
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="license.lic"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + data + f'\r\n--{boundary}--\r\n'.encode())
    try:
        response = call('POST', '/api/v1/admin/licenses', body, 'multipart/form-data; boundary=' + boundary, csrf)
    except Exception:
        raise RuntimeError('License upload failed or its result is unknown; inspect FAIG before retrying. Rotation record unchanged.') from None
    if not isinstance(response, list) or not response:
        raise RuntimeError('Unexpected license response; inspect FAIG. Rotation record unchanged.')
    try:
        record_license(marker, license_file.name)
    except OSError:
        raise RuntimeError('License uploaded but rotation record could not be written; reconcile .last-used manually.') from None
    print('License upload accepted; rotation record updated. Verify license and scanning status in FAIG.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
