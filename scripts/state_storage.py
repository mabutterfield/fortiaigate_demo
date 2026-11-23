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
