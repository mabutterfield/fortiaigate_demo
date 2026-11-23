"""Terraform launcher for coordinated external state; no state values are printed."""
from __future__ import annotations

import os
from pathlib import Path
import sys

try:
    import state_storage
except ModuleNotFoundError:
    from scripts import state_storage

REPO_ROOT = Path(__file__).resolve().parents[1]


def module_from_args(argv: list[str], cwd: Path, repo_root: Path) -> str:
    selected = cwd
    for arg in argv:
        if arg.startswith('-chdir='):
            selected = Path(arg.split('=', 1)[1])
            if not selected.is_absolute():
                selected = cwd / selected
            break
    target = selected.resolve()
    for module in state_storage.MODULES:
        if target == (repo_root / 'terraform' / module).resolve():
            return module
    raise ValueError('Terraform launcher only supports configured FAIG AWS modules')


def proxy_environment(argv: list[str], cwd: Path, environ: dict[str, str], repo_root: Path) -> tuple[str, dict[str, str]]:
    profile = environ.get('FAIG_STORAGE_PROFILE', '')
    binary = environ.get('FAIG_REAL_TERRAFORM', '')
    if not profile or not binary or not Path(binary).is_absolute():
        raise ValueError('Terraform launcher is missing its storage profile or real binary')
    settings = state_storage.read_storage_settings(Path(profile))
    if settings is None or settings.state is None:
        raise ValueError('Terraform launcher requires an external state profile')
    requested = environ.get('TF_WORKSPACE', '')
    if requested and requested != settings.workspace:
        raise ValueError('TF_WORKSPACE conflicts with the saved storage profile')
    state_storage.verify_state_manifest(settings.state)
    if (settings.state.root / '.migration-in-progress.json').exists():
        raise ValueError('state migration is incomplete')
    module = module_from_args(argv, cwd, repo_root)
    data = state_storage.terraform_data_dir(settings.state, repo_root, module)
    if not (data / 'terraform.tfstate').is_file():
        raise ValueError(f'external backend for {module} is not initialized; run the FAIG quickstart')
    env = dict(environ, TF_DATA_DIR=str(data), TF_WORKSPACE=settings.workspace)
    return binary, env


def main() -> int:
    try:
        binary, env = proxy_environment(sys.argv[1:], Path.cwd(), dict(os.environ), REPO_ROOT)
    except (OSError, ValueError) as exc:
        print(f'Terraform launcher stopped: {exc}', file=sys.stderr)
        return 2
    os.execve(binary, [binary, *sys.argv[1:]], env)
    return 127


if __name__ == '__main__':
    raise SystemExit(main())
