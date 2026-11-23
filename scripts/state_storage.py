"""Resolve optional external Terraform state paths without changing state.

The state root is a user preference; module state and workspace state remain
separate. Backend initialization/migration is an explicit caller responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

MODULES = ('aws-ecr', 'aws-prep', 'aws-ec2-k3s', 'aws-fortigate', 'aws-fortiweb')
_WORKSPACE = re.compile(r'^[A-Za-z0-9_-]+$')


@dataclass(frozen=True)
class StateLayout:
    root: Path

    def __post_init__(self):
        if not self.root.is_absolute():
            raise ValueError('state root must be an absolute path')
        object.__setattr__(self, 'root', self.root.resolve())

    def module_root(self, module: str) -> Path:
        if module not in MODULES:
            raise ValueError('unknown Terraform module')
        return self.root / module

    def backend_args(self, module: str) -> list[str]:
        path = self.module_root(module)
        return [f'-backend-config=path={path / "terraform.tfstate"}',
                f'-backend-config=workspace_dir={path / "workspaces"}']

    def state_path(self, module: str, workspace: str) -> Path:
        if not _WORKSPACE.fullmatch(workspace):
            raise ValueError('invalid Terraform workspace name')
        path = self.module_root(module)
        return path / 'terraform.tfstate' if workspace == 'default' else path / 'workspaces' / workspace / 'terraform.tfstate'

    def dependency_vars(self, module: str, workspace: str) -> list[str]:
        deps = {'aws-prep': [('aws_ecr_state_path', 'aws-ecr')],
                'aws-ec2-k3s': [('aws_prep_state_path', 'aws-prep')],
                'aws-fortigate': [('aws_prep_state_path', 'aws-prep'), ('aws_ec2_k3s_state_path', 'aws-ec2-k3s')],
                'aws-fortiweb': [('aws_prep_state_path', 'aws-prep'), ('aws_ec2_k3s_state_path', 'aws-ec2-k3s')]}
        return [f'{name}={self.state_path(target, workspace)}' for name, target in deps.get(module, [])]


def resolve_state_root(value: str, workspace_root: Path, repo_root: Path) -> Path:
    """Resolve user choice from a stable workspace location and reject repo storage."""
    if not value.strip():
        raise ValueError('state root cannot be empty')
    selected = Path(value).expanduser()
    if not selected.is_absolute():
        selected = workspace_root / selected
    selected = selected.resolve()
    repo = repo_root.resolve()
    if selected == repo or repo in selected.parents:
        raise ValueError('external state root must be outside the repository')
    return selected


def checked_state_identity(path: Path) -> tuple[str, int, int]:
    """Return non-secret identity/serial/count for a private, existing state."""
    import json
    data = json.loads(path.read_text(encoding='utf-8'))
    lineage, serial, resources = data.get('lineage'), data.get('serial'), data.get('resources')
    if not isinstance(lineage, str) or not lineage or not isinstance(serial, int) or not isinstance(resources, list):
        raise ValueError(f'invalid Terraform state: {path}')
    count = sum(len(item.get('instances', [])) for item in resources if item.get('mode') == 'managed')
    return lineage, serial, count


def read_state_settings(path: Path) -> StateLayout | None:
    """Read a previously chosen user setting; absence leaves external mode off."""
    import json
    if path.is_symlink():
        raise ValueError(f'state settings must be a private regular file: {path}')
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f'state settings must be a private regular file: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('external'), bool):
        raise ValueError('invalid state settings')
    if not data['external']:
        return None
    root = data.get('root')
    if not isinstance(root, str) or not root:
        raise ValueError('external state root is missing')
    return StateLayout(Path(root))


def write_state_settings(path: Path, layout: StateLayout | None) -> None:
    """Write a non-secret profile atomically; reject a pre-existing symlink."""
    import json
    import os
    import tempfile
    if path.is_symlink():
        raise ValueError('state settings may not be a symlink')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {'version': 1, 'external': layout is not None}
    if layout is not None:
        payload['root'] = str(layout.root)
    fd, name = tempfile.mkstemp(prefix='.state-settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def inventory_legacy_states(module_root: Path) -> dict[str, Path]:
    """Find current and named-workspace snapshots without reading secret contents."""
    result = {}
    default = module_root / 'terraform.tfstate'
    if default.exists():
        result['default'] = default
    workspace_root = module_root / 'terraform.tfstate.d'
    if workspace_root.exists():
        for child in workspace_root.iterdir():
            if not child.is_dir() or not _WORKSPACE.fullmatch(child.name):
                raise ValueError(f'unexpected workspace entry: {child}')
            snapshot = child / 'terraform.tfstate'
            if snapshot.exists():
                result[child.name] = snapshot
    return result


def check_migration_source(module_root: Path, layout: StateLayout, module: str) -> dict[str, tuple[str, int, int]]:
    """Fail closed on a target collision; never overwrite another state."""
    source = inventory_legacy_states(module_root)
    identities = {workspace: checked_state_identity(path) for workspace, path in source.items()}
    target_root = layout.module_root(module)
    if target_root.exists() and any(target_root.iterdir()):
        raise ValueError(f'external state target is not empty: {target_root}')
    return identities


def verify_migrated_states(layout: StateLayout, module: str, expected: dict[str, tuple[str, int, int]]) -> None:
    """Validate migration by lineage, serial, and managed instance count."""
    for workspace, identity in expected.items():
        path = layout.state_path(module, workspace)
        if not path.is_file() or checked_state_identity(path) != identity:
            raise ValueError(f'migrated state verification failed for {module}/{workspace}')


def archive_migrated_sources(module_root: Path, layout: StateLayout, module: str,
                             expected: dict[str, tuple[str, int, int]], archive_root: Path) -> None:
    """Archive verified old snapshots privately, leaving no active stale copy.

    Caller must hold the migration lease. This routine never touches cloud
    resources or a target snapshot and refuses changed or symlinked sources.
    """
    import os
    import shutil
    sources = inventory_legacy_states(module_root)
    if set(sources) != set(expected):
        raise ValueError('legacy workspace set changed during migration')
    verify_migrated_states(layout, module, expected)
    for workspace, source in sources.items():
        if source.is_symlink() or checked_state_identity(source) != expected[workspace]:
            raise ValueError(f'legacy state changed or is a symlink: {source}')
    if archive_root.exists() and any(archive_root.iterdir()):
        raise ValueError(f'archive destination is not empty: {archive_root}')
    files = []
    for workspace, source in sources.items():
        for path in (source, source.with_suffix(source.suffix + '.backup')):
            if path.is_symlink():
                raise ValueError(f'legacy state backup is a symlink: {path}')
            if path.exists():
                if not path.is_file():
                    raise ValueError(f'legacy state backup is not a regular file: {path}')
                files.append((workspace, path))
    archive_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(archive_root, 0o700)
    # Copy and verify *every* file before removing any source.
    for workspace, path in files:
        dest = archive_root / workspace
        dest.mkdir(mode=0o700, exist_ok=True)
        target = dest / path.name
        with path.open('rb') as infile, target.open('xb') as outfile:
            os.chmod(target, 0o600)
            shutil.copyfileobj(infile, outfile)
            outfile.flush()
            os.fsync(outfile.fileno())
        if path.read_bytes() != target.read_bytes():
            raise ValueError(f'archive verification failed: {path}')
    verify_migrated_states(layout, module, expected)
    for workspace, source in sources.items():
        if checked_state_identity(source) != expected[workspace]:
            raise ValueError(f'legacy state changed during archive: {source}')
    for _, path in files:
        path.unlink()
