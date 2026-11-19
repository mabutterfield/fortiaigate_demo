"""Private local credential helpers for the experimental FAIG lab tools."""
import json
import os
from pathlib import Path
import secrets
import string


def student_email(number, domain='fortiai.lab'):
    if number < 1:
        raise ValueError('Student number must be positive')
    if not domain or '@' in domain or any(c.isspace() for c in domain):
        raise ValueError('Invalid student email domain')
    return f'student{number:02d}@{domain}'


def select_password(path=None):
    if path is None:
        # Underscore meets FAIG's special-character rule and stays in a
        # double-click word selection in common terminals and browsers.
        pools = (string.ascii_uppercase, string.ascii_lowercase, string.digits, '_')
        chars = [secrets.choice(pool) for pool in pools]
        chars.extend(secrets.choice(''.join(pools)) for _ in range(20))
        secrets.SystemRandom().shuffle(chars)
        return ''.join(chars)
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise ValueError('Password file must be owner-only (chmod 600)')
    password = path.read_text().removesuffix('\n').removesuffix('\r')
    if not password or '\n' in password or '\r' in password:
        raise ValueError('Password file must contain one non-empty line')
    return password


def write_new_private_json(path, value):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.write('\n')
    except Exception:
        path.unlink(missing_ok=True)
        raise
