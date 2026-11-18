#!/usr/bin/env python3
"""Prepare private setup and login files for a fresh FAIG lab."""
import argparse
from pathlib import Path
import sys
from credentials import select_password, write_new_private_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--email', default='admin@fortiai.lab')
    p.add_argument('--display-name', default='Lab Administrator')
    p.add_argument('--organization', default='FortiAI Lab')
    p.add_argument('--password-file', type=Path, help='Owner-only one-line password; omitted generates a random password')
    p.add_argument('--setup-output', type=Path, required=True)
    p.add_argument('--login-output', type=Path, required=True)
    a = p.parse_args()
    if not a.email or '@' not in a.email or not a.display_name or not a.organization:
        p.error('A valid email, display name and organization are required')
    if a.setup_output == a.login_output or any(x.exists() or not x.parent.is_dir() for x in (a.setup_output, a.login_output)):
        p.error('Both output files must be new, distinct files in existing directories')
    password = select_password(a.password_file)
    setup = {'email': a.email, 'username': a.display_name, 'password': password, 'organization_name': a.organization}
    login = {'username': a.email, 'password': password}
    write_new_private_json(a.setup_output, setup)
    try:
        write_new_private_json(a.login_output, login)
    except Exception:
        a.setup_output.unlink(missing_ok=True)
        raise
    print('Prepared private administrator setup and login files for', a.email)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as exc:
        print('Stopped:', exc, file=sys.stderr)
        sys.exit(1)
