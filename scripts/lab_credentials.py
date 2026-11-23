"""Read per-instance bootstrap credentials without printing secret values."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re


def private_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'private file must be a regular non-symlink file: {path}')
    stat = path.stat()
    if stat.st_mode & 0o077 or stat.st_uid != os.getuid():
        raise ValueError(f'private file must be owner-only and owned by the current user: {path}')


def read_static_password(path: Path, repo_root: Path) -> str:
    if not path.is_absolute():
        raise ValueError('static admin password path must be absolute')
    private_regular_file(path)
    resolved, repo = path.resolve(), repo_root.resolve()
    if resolved == repo or repo in resolved.parents:
        raise ValueError('static admin password file must be outside the repository')
    password = path.read_text(encoding='utf-8').removesuffix('\n').removesuffix('\r')
    if ('\n' in password or '\r' in password or len(password) < 8
            or not re.search(r'[A-Z]', password) or not re.search(r'[a-z]', password)
            or not re.search(r'[0-9]', password) or not re.search(r'[^A-Za-z0-9]', password)):
        raise ValueError('static admin password must be one line and meet FAIG password requirements')
    return password


def load_bootstrap(path: Path, *, instance: str, workspace: str, repo_root: Path,
                   email: str, display_name: str, organization: str) -> tuple[dict, dict, dict]:
    """Return setup/login/LiteLLM payloads in memory; never log them."""
    private_regular_file(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['instance_id'] != instance or data['workspace'] != workspace:
            raise ValueError('bootstrap file belongs to a different instance or workspace')
        admin, litellm = data['faig_admin'], data['litellm']
        static = admin.get('static_password_file')
        generated = admin.get('password')
        if bool(static) == bool(generated):
            raise ValueError('bootstrap file must specify exactly one administrator password source')
        password = read_static_password(Path(static), repo_root) if static else generated
        if not isinstance(password, str) or not password:
            raise ValueError('bootstrap administrator password is missing')
        if not all(isinstance(litellm.get(k), str) and litellm[k] for k in ('master_key', 'ui_password', 'postgres_password')):
            raise ValueError('bootstrap LiteLLM credentials are incomplete')
        if not all(isinstance(v, str) and v for v in (email, display_name, organization)):
            raise ValueError('administrator identity is incomplete')
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('bootstrap credentials have an invalid format') from exc
    setup = {'email': email, 'username': display_name, 'password': password, 'organization_name': organization}
    login = {'username': email, 'password': password}
    return setup, login, {'litellm_master_key': litellm['master_key'],
                          'litellm_ui_password': litellm['ui_password'],
                          'litellm_postgres_password': litellm['postgres_password']}


def validate_instance_directory(path: Path, *, root: Path, workspace: str, instance: str) -> Path:
    """Verify the exact, private instance directory and record a non-secret marker."""
    import stat
    expected = root / workspace / instance
    if not root.is_absolute() or not re.fullmatch(r'[A-Za-z0-9_-]+', workspace):
        raise ValueError('invalid instance secrets root or workspace')
    if not re.fullmatch(r'i-[0-9a-f]+', instance):
        raise ValueError('invalid EC2 instance ID')
    if path != expected:
        raise ValueError('instance secrets directory does not match instance and workspace')
    current = root
    for part in (workspace, instance):
        if current.is_symlink():
            raise ValueError('instance secrets path must not contain symlinks')
        current = current / part
    if current.is_symlink() or not current.is_dir():
        raise ValueError('instance secrets directory must be a regular directory')
    info = current.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('instance secrets directory must be owned by the user and owner-only')
    marker = current / '.lab-instance'
    expected_marker = {'instance_id': instance, 'workspace': workspace}
    if marker.exists() or marker.is_symlink():
        private_regular_file(marker)
        if json.loads(marker.read_text(encoding='utf-8')) != expected_marker:
            raise ValueError('instance secrets marker does not match')
    else:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(expected_marker, stream)
            stream.write('\n')
    return current


def activate_bootstrap(root: Path, workspace: str, instance: str, *, repo_root: Path,
                       email: str, display_name: str = 'Lab Administrator',
                       organization: str = 'FortiAI Lab') -> dict:
    """Validate generated instance credentials and return non-persistent runtime inputs."""
    directory = validate_instance_directory(root / workspace / instance, root=root,
                                            workspace=workspace, instance=instance)
    bootstrap = directory / 'bootstrap-secrets.json'
    setup, _login, _litellm = load_bootstrap(bootstrap, instance=instance, workspace=workspace,
                                             repo_root=repo_root, email=email,
                                             display_name=display_name, organization=organization)
    return {'environment': directory, 'instance_id': instance, 'bootstrap_file': bootstrap, 'setup_data': setup,
            'journal': directory / 'faig-init.json', 'smoke_key': directory / 'quickstart-smoke-key.json',
            'litellm_key': directory / 'litellm-shared-key.json'}


def remove_generated_instance_files(root: Path, workspace: str, instance: str, *, terminated: bool) -> bool:
    """Remove only recognized generated files after the caller confirms termination.

    A stale marker, symlink, unknown file or failed verification stops cleanup.
    AWS status and Terraform state checks are the caller's responsibility.
    """
    if terminated is not True:
        raise ValueError('confirmed instance termination is required')
    directory = root / workspace / instance
    if not directory.exists() and not directory.is_symlink():
        return False
    # Never create a marker during cleanup; only an existing, verified marker qualifies.
    marker = directory / '.lab-instance'
    if not marker.exists() or marker.is_symlink():
        raise ValueError('instance secrets marker is missing or unsafe')
    validate_instance_directory(directory, root=root, workspace=workspace, instance=instance)
    allowed = {'bootstrap-secrets.json', 'litellm-shared-key.json', 'faig-init.json',
               'quickstart-smoke-key.json', '.lab-instance'}
    entries = list(directory.iterdir())
    for entry in entries:
        known = entry.name in allowed or bool(re.fullmatch(r'litellm-shared-key\.json\.stale-[A-Za-z0-9_-]+', entry.name))
        if not known or entry.is_symlink() or not entry.is_file():
            raise ValueError(f'unknown or unsafe file in instance secrets directory: {entry.name}')
    # Remove the marker last so interrupted cleanup can safely be retried.
    for entry in entries:
        if entry != marker:
            entry.unlink()
    marker.unlink()
    directory.rmdir()
    return True
