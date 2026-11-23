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
MOVED_SENTINEL = 'FAIG TERRAFORM STATE MOVED: use the configured external-state quickstart.\n'


def is_moved_sentinel(path: Path) -> bool:
    """Recognize a non-secret marker that makes legacy raw Terraform fail closed."""
    try:
        return path.is_file() and path.stat().st_size == len(MOVED_SENTINEL) and path.read_text(encoding='utf-8') == MOVED_SENTINEL
    except (OSError, UnicodeDecodeError):
        return False


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
    if any((ancestor / '.git').exists() for ancestor in (selected, *selected.parents)):
        raise ValueError('external storage root must be outside every Git worktree')
    return selected


def checked_state_identity(path: Path) -> tuple[str, int, int, str]:
    """Return lineage, serial, count and a digest without exposing state data."""
    import hashlib
    import json
    data = json.loads(path.read_text(encoding='utf-8'))
    lineage, serial, resources = data.get('lineage'), data.get('serial'), data.get('resources')
    if not isinstance(lineage, str) or not lineage or not isinstance(serial, int) or not isinstance(resources, list):
        raise ValueError(f'invalid Terraform state: {path}')
    count = sum(len(item.get('instances', [])) for item in resources if item.get('mode') == 'managed')
    canonical = json.dumps(resources, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return lineage, serial, count, hashlib.sha256(canonical).hexdigest()


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
    if workspace_root.is_symlink():
        raise ValueError(f'legacy workspace directory is a symlink: {workspace_root}')
    if workspace_root.exists():
        for child in workspace_root.iterdir():
            if child.is_symlink() or not child.is_dir() or not _WORKSPACE.fullmatch(child.name):
                raise ValueError(f'unexpected workspace entry: {child}')
            snapshot = child / 'terraform.tfstate'
            if snapshot.exists():
                result[child.name] = snapshot
    return result


def check_migration_source(module_root: Path, layout: StateLayout, module: str) -> dict[str, tuple[str, int, int, str]]:
    """Fail closed on a target collision; never overwrite another state."""
    source = inventory_legacy_states(module_root)
    identities = {workspace: checked_state_identity(path) for workspace, path in source.items()}
    target_root = layout.module_root(module)
    if target_root.exists() and any(target_root.iterdir()):
        raise ValueError(f'external state target is not empty: {target_root}')
    return identities


def verify_migrated_states(layout: StateLayout, module: str, expected: dict[str, tuple[str, int, int, str]]) -> None:
    """Validate migration by lineage, serial, count, and resource digest."""
    for workspace, identity in expected.items():
        path = layout.state_path(module, workspace)
        if not path.is_file() or checked_state_identity(path) != identity:
            raise ValueError(f'migrated state verification failed for {module}/{workspace}')


def archive_migrated_sources(module_root: Path, layout: StateLayout, module: str,
                             expected: dict[str, tuple[str, int, int, str]], archive_root: Path) -> None:
    """Archive verified old snapshots privately, leaving no active stale copy.

    Caller must hold the migration lease. This routine never touches cloud
    resources or a target snapshot and refuses changed or symlinked sources.
    """
    import os
    import shutil
    import tempfile
    sources = inventory_legacy_states(module_root)
    if set(sources) != set(expected):
        raise ValueError('legacy workspace set changed during migration')
    verify_migrated_states(layout, module, expected)
    for workspace, source in sources.items():
        if source.is_symlink() or checked_state_identity(source) != expected[workspace]:
            raise ValueError(f'legacy state changed or is a symlink: {source}')
    if archive_root.is_symlink() or (archive_root.exists() and any(archive_root.iterdir())):
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
        if path.name == 'terraform.tfstate':
            # Keep an intentionally invalid marker at every old active state
            # path: old checkout Terraform must not create a fresh empty state.
            fd, temporary = tempfile.mkstemp(prefix='.faig-state-moved-', dir=path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as marker:
                    os.fchmod(marker.fileno(), 0o600)
                    marker.write(MOVED_SENTINEL)
                    marker.flush()
                    os.fsync(marker.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        else:
            path.unlink()


def migrate_one_module(module_root: Path, layout: StateLayout, module: str, archive_root: Path) -> None:
    """Migrate a module's local workspaces, verify them, then archive old copies.

    This is deliberately not invoked by quickstart yet: callers must coordinate
    all modules, exclusive access, persistent profile and recovery first.
    """
    import os
    import subprocess
    source = module_root.resolve()
    if not (source / '.terraform').is_dir():
        raise ValueError(f'Terraform module must already be initialized: {source}')
    expected = check_migration_source(source, layout, module)
    backup = archive_root.with_name(archive_root.name + '-before')
    if backup_legacy_states(source, backup) != expected:
        raise ValueError('source state changed while preparing the migration backup')
    target = layout.module_root(module)
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    # An implicit local backend ignores -backend-config in older checkouts.
    # Migrate private copies through a minimal explicit-backend working dir;
    # never alter the old checkout's Terraform configuration or state in place.
    import shutil
    import tempfile
    env = os.environ.copy()
    env.pop('TF_WORKSPACE', None)
    env.pop('TF_DATA_DIR', None)
    previous_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix='faig-state-migration-', dir=backup.parent) as tmp:
            staging = Path(tmp)
            (staging / 'main.tf').write_text('terraform {\n  backend "local" {}\n}\n', encoding='utf-8')
            def init(*args):
                command = ['terraform', '-chdir=' + str(staging), 'init', '-input=false', *args]
                result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
                if result.returncode:
                    raise RuntimeError(f'Terraform migration failed for {module}; inspect backend configuration before retrying')
            init()
            for workspace, path in inventory_legacy_states(source).items():
                destination = (staging / 'terraform.tfstate' if workspace == 'default' else
                               staging / 'terraform.tfstate.d' / workspace / 'terraform.tfstate')
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(path, destination)
                os.chmod(destination, 0o600)
            init('-migrate-state', '-force-copy', *layout.backend_args(module))
    finally:
        os.umask(previous_umask)
    verify_migrated_states(layout, module, expected)
    archive_migrated_sources(source, layout, module, expected, archive_root)


@dataclass(frozen=True)
class StorageSettings:
    """Joint deployment preference; secrets stay separate even with local state."""
    secrets_root: Path
    state: StateLayout | None
    workspace: str = 'default'
    terraform_vars_dir: Path | None = None

    def __post_init__(self):
        if not self.secrets_root.is_absolute():
            raise ValueError('secrets root must be an absolute path')
        secrets = self.secrets_root.resolve()
        object.__setattr__(self, 'secrets_root', secrets)
        if not _WORKSPACE.fullmatch(self.workspace) or self.workspace.lower() == 'static':
            raise ValueError('invalid Terraform workspace name')
        if self.terraform_vars_dir is not None:
            if not self.terraform_vars_dir.is_absolute():
                raise ValueError('Terraform overrides directory must be absolute')
            object.__setattr__(self, 'terraform_vars_dir', self.terraform_vars_dir.resolve())
        if self.state is not None:
            state = self.state.root
            if state == secrets or state in secrets.parents or secrets in state.parents:
                raise ValueError('state and generated secrets directories must not overlap')


def read_storage_settings(path: Path) -> StorageSettings | None:
    import json
    import os
    if path.is_symlink():
        raise ValueError('storage settings may not be a symlink')
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise ValueError('storage settings must be an owner-only regular file')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 2 or not isinstance(data.get('external_state'), bool):
        raise ValueError('invalid coordinated storage settings')
    secrets_root = data.get('secrets_root')
    if not isinstance(secrets_root, str) or not secrets_root:
        raise ValueError('generated secrets root is missing')
    state_root = data.get('state_root')
    if data['external_state'] and (not isinstance(state_root, str) or not state_root):
        raise ValueError('external state root is missing')
    workspace = data.get('workspace', 'default')
    vars_dir = data.get('terraform_vars_dir')
    if not isinstance(workspace, str) or (vars_dir is not None and not isinstance(vars_dir, str)):
        raise ValueError('invalid workspace or Terraform overrides directory')
    return StorageSettings(Path(secrets_root), StateLayout(Path(state_root)) if data['external_state'] else None,
                           workspace, Path(vars_dir) if vars_dir else None)


def write_storage_settings(path: Path, settings: StorageSettings) -> None:
    import json
    import os
    import tempfile
    if path.is_symlink():
        raise ValueError('storage settings may not be a symlink')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {'version': 2, 'external_state': settings.state is not None,
               'state_root': str(settings.state.root) if settings.state else None,
               'secrets_root': str(settings.secrets_root), 'workspace': settings.workspace,
               'terraform_vars_dir': str(settings.terraform_vars_dir) if settings.terraform_vars_dir else None}
    fd, name = tempfile.mkstemp(prefix='.storage-settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def prepare_external_module(module_root: Path, layout: StateLayout, module: str, workspace: str,
                            *, require_existing: bool = False) -> list[str]:
    """Build safe init arguments only after legacy state has been migrated."""
    import os
    # The mere presence of a source snapshot must not be ignored: another
    # checkout might otherwise create fresh state for existing resources.
    # Read-only discovery can follow an old shared-worktree alias, but any
    # actual legacy snapshot must be migrated before this checkout initializes.
    workspace_root = module_root / 'terraform.tfstate.d'
    default_state = module_root / 'terraform.tfstate'
    legacy_default = default_state.is_file() and not is_moved_sentinel(default_state)
    legacy_named = (workspace_root.is_dir() and any(
        (child / 'terraform.tfstate').is_file() and not is_moved_sentinel(child / 'terraform.tfstate')
        for child in workspace_root.iterdir() if child.is_dir()))
    if legacy_default or legacy_named:
        raise ValueError(f'legacy state still exists for {module}; migrate and verify it first')
    target = layout.state_path(module, workspace)
    if require_existing and not target.is_file():
        raise ValueError(f'required external state is missing for {module}/{workspace}')
    if target.is_symlink():
        raise ValueError(f'external state file may not be a symlink: {target}')
    module_dir = layout.module_root(module)
    if layout.root.is_symlink() or module_dir.is_symlink():
        raise ValueError('external state directories may not be symlinks')
    layout.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    module_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(layout.root, 0o700)
    os.chmod(module_dir, 0o700)
    return ['init', '-input=false', *layout.backend_args(module)]


def discover_worktree_states(worktrees: list[Path], module: str, *, allow_moved: bool = False) -> dict[str, Path]:
    """Find unique legacy state files across worktrees; reject ambiguous owners.

    Existing symlinked worktrees can be inventoried read-only. A migration must
    run from the real owning checkout, not from an alias.
    """
    if module not in MODULES:
        raise ValueError('unknown Terraform module')
    found: dict[str, Path] = {}
    for tree in worktrees:
        module_root = tree / 'terraform' / module
        default = module_root / 'terraform.tfstate'
        candidates = [('default', default)]
        directory = module_root / 'terraform.tfstate.d'
        if directory.is_dir():
            for child in directory.iterdir():
                if not child.is_dir() or not _WORKSPACE.fullmatch(child.name):
                    raise ValueError(f'unexpected workspace entry: {child}')
                candidates.append((child.name, child / 'terraform.tfstate'))
        for workspace, path in candidates:
            if not path.is_file():
                continue
            real = path.resolve()
            if is_moved_sentinel(real):
                if allow_moved:
                    continue
                raise ValueError(f'{module}/{workspace} has moved-state marker; inspect the saved storage profile')
            prior = found.get(workspace)
            if prior is not None and prior != real:
                # Different on-disk snapshots are ambiguous even when their
                # lineage/serial currently match; either could be written.
                raise ValueError(f'multiple legacy state files for {module}/{workspace}: {prior}, {real}')
            checked_state_identity(real)
            found[workspace] = real
    return found


def backup_legacy_states(module_root: Path, backup_root: Path) -> dict[str, tuple[str, int, int, str]]:
    """Copy old snapshots and state backups privately before running migration."""
    import os
    import shutil
    sources = inventory_legacy_states(module_root)
    expected = {workspace: checked_state_identity(path) for workspace, path in sources.items()}
    if backup_root.is_symlink() or (backup_root.exists() and any(backup_root.iterdir())):
        raise ValueError(f'backup destination must be a new empty directory: {backup_root}')
    backup_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(backup_root, 0o700)
    for workspace, source in sources.items():
        destination = backup_root / workspace
        destination.mkdir(mode=0o700)
        for path in (source, source.with_suffix(source.suffix + '.backup')):
            if path.is_symlink():
                raise ValueError(f'legacy state backup is a symlink: {path}')
            if not path.exists():
                continue
            if not path.is_file():
                raise ValueError(f'legacy state backup is not a regular file: {path}')
            target = destination / path.name
            with path.open('rb') as src, target.open('xb') as dst:
                os.chmod(target, 0o600)
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            if path.read_bytes() != target.read_bytes():
                raise ValueError(f'legacy state backup verification failed: {path}')
    return expected


def build_migration_plan(worktrees: list[Path], layout: StateLayout) -> dict[str, dict]:
    """Inventory every state workspace and identify its real source module."""
    plan = {}
    for module in MODULES:
        snapshots = discover_worktree_states(worktrees, module)
        owners = set()
        for workspace, snapshot in snapshots.items():
            owner = snapshot.parent if workspace == 'default' else snapshot.parents[2]
            if owner.name != module or owner.parent.name != 'terraform':
                raise ValueError(f'cannot identify owning Terraform module for {module}/{workspace}')
            owners.add(owner)
        if len(owners) > 1:
            raise ValueError(f'{module} workspaces have different owning checkouts; reconcile before migration')
        target = layout.module_root(module)
        if target.exists() and any(target.iterdir()):
            raise ValueError(f'external state target is not empty: {target}')
        owner = next(iter(owners), None)
        if owner is not None:
            source = check_migration_source(owner, layout, module)
            if set(source) != set(snapshots):
                raise ValueError(f'incomplete source state inventory for {module}')
        else:
            source = {}
        plan[module] = {'module_root': owner, 'workspaces': source}
    return plan


def install_legacy_guards(worktrees: list[Path], plan: dict[str, dict]) -> None:
    """Block raw local Terraform for known workspaces in every old checkout."""
    import os
    workspaces = {'default'}
    for item in plan.values():
        workspaces.update(item['workspaces'])
    for tree in worktrees:
        for module in MODULES:
            module_root = tree / 'terraform' / module
            if not module_root.is_dir():
                continue
            for workspace in sorted(workspaces):
                path = (module_root / 'terraform.tfstate' if workspace == 'default' else
                        module_root / 'terraform.tfstate.d' / workspace / 'terraform.tfstate')
                if path.exists() or path.is_symlink():
                    if is_moved_sentinel(path):
                        continue
                    raise ValueError(f'legacy state guard would overwrite an existing file: {path}')
                for parent in (path.parent, *path.parent.parents):
                    if parent == tree.parent:
                        break
                    if parent.is_symlink():
                        raise ValueError(f'legacy state guard path contains a symlink: {parent}')
                path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    stream.write(MOVED_SENTINEL)
                    stream.flush()
                    os.fsync(stream.fileno())


def migrate_plan(plan: dict[str, dict], layout: StateLayout, backup_root: Path, *, worktrees: list[Path] | None = None) -> None:
    """Migrate an inventoried set with private backups and a fail-closed journal.

    No cloud resources are changed. An interrupted journal is intentionally not
    replayed automatically: verify both copies before explicitly recovering it.
    """
    import fcntl
    import json
    import os
    if layout.root.is_symlink() or backup_root.is_symlink():
        raise ValueError('state and backup roots must not be symlinks')
    layout.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(layout.root, 0o700)
    lock_path = layout.root / '.migration.lock'
    if lock_path.is_symlink():
        raise ValueError('migration lock must not be a symlink')
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with os.fdopen(fd, 'r+', encoding='utf-8') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            journal = layout.root / '.migration-in-progress.json'
            if journal.exists() or journal.is_symlink():
                raise ValueError('an earlier state migration needs inspection before retrying')
            if backup_root.exists() and any(backup_root.iterdir()):
                raise ValueError('migration backup destination must be new or empty')
            backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(backup_root, 0o700)
            for name in ('preflight', 'retired'):
                directory = backup_root / name
                directory.mkdir(mode=0o700, exist_ok=True)
                os.chmod(directory, 0o700)
            # Confirm and back up every source before moving any module.
            for module in MODULES:
                item = plan[module]
                source = item['module_root']
                if source is None:
                    continue
                current = check_migration_source(source, layout, module)
                if current != item['workspaces']:
                    raise ValueError(f'{module} source changed since the migration plan')
                if backup_legacy_states(source, backup_root / 'preflight' / module) != current:
                    raise ValueError(f'{module} source changed while backing it up')
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            journal_fd = os.open(journal, flags, 0o600)
            with os.fdopen(journal_fd, 'w', encoding='utf-8') as out:
                json.dump({'version': 1, 'modules': [name for name in MODULES if plan[name]['module_root']],
                           'backup_root': str(backup_root)}, out)
                out.flush()
                os.fsync(out.fileno())
            # Keep the journal if any migration fails or execution is interrupted.
            for module in MODULES:
                source = plan[module]['module_root']
                if source is not None:
                    migrate_one_module(source, layout, module, backup_root / 'retired' / module)
            for module in MODULES:
                verify_migrated_states(layout, module, plan[module]['workspaces'])
            if worktrees is not None:
                install_legacy_guards(worktrees, plan)
            journal.unlink()
    except BlockingIOError:
        raise ValueError('another state migration is already running') from None


def activate_storage_settings(settings: StorageSettings, profile_path: Path, worktrees: list[Path],
                              backup_root: Path) -> None:
    """Persist a new selection and migrate old local state before it is used.

    This function is not yet invoked by quickstart. It fails closed if an
    incomplete migration or an ambiguous existing external state is found.
    """
    for tree in worktrees:
        repo = tree.resolve()
        for root in (settings.secrets_root, settings.state.root if settings.state else None):
            if root is not None and (root == repo or repo in root.parents):
                raise ValueError('state and generated secrets must be outside every Git worktree')
    prior = read_storage_settings(profile_path)
    if prior is not None and prior != settings:
        raise ValueError('storage profile differs from existing settings; explicit migration is required')
    if settings.state is None:
        if prior is None:
            write_storage_settings(profile_path, settings)
        return
    layout = settings.state
    journal = layout.root / '.migration-in-progress.json'
    if journal.exists() or journal.is_symlink():
        raise ValueError('an earlier state migration needs inspection before continuing')
    if prior is not None:
        # An existing profile is authoritative. Refuse stale local copies;
        # never silently create a fresh state while old snapshots still exist.
        if not layout.root.is_dir():
            raise ValueError('configured external state root is missing; inspect the profile before continuing')
        verify_state_manifest(layout)
        for module in MODULES:
            if discover_worktree_states(worktrees, module, allow_moved=True):
                raise ValueError(f'legacy state still exists for {module}; inspect the existing profile and migration')
        return
    if (layout.root / '.state-inventory.json').exists():
        # A second environment profile may reuse an already migrated state
        # root, but only after verifying its inventory and absence of old state.
        verify_state_manifest(layout)
        for module in MODULES:
            if discover_worktree_states(worktrees, module, allow_moved=True):
                raise ValueError(f'legacy state still exists for {module}; inspect before using external state')
        write_storage_settings(profile_path, settings)
        return
    plan = build_migration_plan(worktrees, layout)
    print('Local Terraform state migration inventory (resource counts are state records, not AWS status):')
    for module, item in plan.items():
        if not item['workspaces']:
            print(f'- {module}: no existing snapshots')
        for workspace, identity in sorted(item['workspaces'].items()):
            print(f'- {module}/{workspace}: {identity[2]} managed instance records')
    print(f'Private state backup location: {backup_root}')
    # Save the user's choice before migration. If interrupted, the migration
    # journal prevents any later quickstart from using a partial state layout.
    write_storage_settings(profile_path, settings)
    migrate_plan(plan, layout, backup_root, worktrees=worktrees)
    manifest = {module: {workspace: identity[0] for workspace, identity in item['workspaces'].items()}
                for module, item in plan.items()}
    write_state_manifest(layout, manifest)


def secure_state_files(path: Path, *, named_workspace: bool) -> None:
    """Restrict an existing Terraform snapshot and its backup to the owner."""
    import os
    if path.is_symlink():
        raise ValueError(f'state snapshot may not be a symlink: {path}')
    for candidate in (path, path.with_suffix(path.suffix + '.backup')):
        if candidate.is_symlink():
            raise ValueError(f'state snapshot or backup may not be a symlink: {candidate}')
        if candidate.exists():
            if not candidate.is_file() or candidate.stat().st_uid != os.getuid():
                raise ValueError(f'state must be an owner-owned regular file: {candidate}')
            os.chmod(candidate, 0o600)
    if named_workspace and path.parent.exists():
        if path.parent.is_symlink() or path.parent.stat().st_uid != os.getuid():
            raise ValueError('workspace state directory must be owned by the current user and not a symlink')
        os.chmod(path.parent, 0o700)


def read_state_manifest(layout: StateLayout) -> dict[str, dict[str, str]]:
    """Read the non-secret inventory of state lineages expected to persist."""
    import json
    import os
    path = layout.root / '.state-inventory.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise ValueError('external state inventory is missing or unsafe')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('modules'), dict):
        raise ValueError('external state inventory has an invalid format')
    return data['modules']


def write_state_manifest(layout: StateLayout, modules: dict[str, dict[str, str]]) -> None:
    import json
    import os
    import tempfile
    path = layout.root / '.state-inventory.json'
    if path.is_symlink():
        raise ValueError('external state inventory may not be a symlink')
    fd, tmp = tempfile.mkstemp(prefix='.state-inventory-', dir=layout.root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({'version': 1, 'modules': modules}, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def verify_state_manifest(layout: StateLayout) -> None:
    """Never treat a missing or wrong-lineage managed state as a fresh lab."""
    modules = read_state_manifest(layout)
    for module, workspaces in modules.items():
        if module not in MODULES or not isinstance(workspaces, dict):
            raise ValueError('external state inventory names an invalid module')
        for workspace, lineage in workspaces.items():
            path = layout.state_path(module, workspace)
            if path.is_symlink() or not path.is_file() or checked_state_identity(path)[0] != lineage:
                raise ValueError(f'external state is missing or has the wrong lineage for {module}/{workspace}')


def register_state(layout: StateLayout, module: str, workspace: str) -> None:
    """Record a newly created workspace or verify its original lineage."""
    modules = read_state_manifest(layout)
    lineage = checked_state_identity(layout.state_path(module, workspace))[0]
    known = modules.setdefault(module, {})
    if workspace in known and known[workspace] != lineage:
        raise ValueError(f'external state lineage changed for {module}/{workspace}')
    known[workspace] = lineage
    write_state_manifest(layout, modules)


def acquire_operation_lock(layout: StateLayout):
    """Hold an exclusive cross-worktree lock until the returned file closes."""
    import fcntl
    import os
    if layout.root.is_symlink():
        raise ValueError('external state root may not be a symlink')
    layout.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(layout.root, 0o700)
    path = layout.root / '.operation.lock'
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    stream = os.fdopen(fd, 'r+', encoding='utf-8')
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        stream.close()
        raise ValueError('another operation is using the shared Terraform state') from None
    return stream


def terraform_data_dir(layout: StateLayout, repo_root: Path, module: str) -> Path:
    """A private, checkout-specific TF_DATA_DIR sharing one authoritative state."""
    import hashlib
    if module not in MODULES:
        raise ValueError('unknown Terraform module')
    checkout = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:16]
    return layout.root / '.terraform-data' / checkout / module


def prime_backend_data(layout: StateLayout, repo_root: Path, module: str, terraform_binary: str) -> Path:
    """Initialize backend metadata without touching a checkout's guard files."""
    import os
    import subprocess
    import tempfile
    data_dir = terraform_data_dir(layout, repo_root, module)
    metadata = data_dir / 'terraform.tfstate'
    parents = (layout.root / '.terraform-data', data_dir.parent, data_dir)
    if any(path.is_symlink() for path in parents) or metadata.is_symlink():
        raise ValueError('Terraform data directory or backend metadata may not be a symlink')
    for path in parents:
        path.mkdir(mode=0o700, exist_ok=True)
        if path.stat().st_uid != os.getuid():
            raise ValueError('Terraform data directory must be owned by the current user')
        os.chmod(path, 0o700)
    if metadata.is_file():
        if metadata.stat().st_uid != os.getuid():
            raise ValueError('Terraform backend metadata must be owned by the current user')
        os.chmod(metadata, 0o600)
        return data_dir
    with tempfile.TemporaryDirectory(prefix='faig-backend-prime-') as tmp:
        staging = Path(tmp)
        (staging / 'main.tf').write_text('terraform {\n  backend "local" {}\n}\n', encoding='utf-8')
        env = os.environ.copy()
        env['TF_DATA_DIR'] = str(data_dir)
        # Backend initialization must not select or create a workspace.
        env.pop('TF_WORKSPACE', None)
        command = [terraform_binary, '-chdir=' + str(staging), 'init', '-input=false', *layout.backend_args(module)]
        result = subprocess.run(command, env=env, text=True, capture_output=True, check=False, umask=0o077)
        if result.returncode:
            raise RuntimeError(f'Cannot initialize external Terraform backend metadata for {module}.')
    return data_dir


def configure_terraform_proxy(repo_root: Path, profile_path: Path) -> str:
    """Make controller-side Ansible and Python use the same state backend."""
    import os
    import shutil
    wrapper = (repo_root / 'scripts/bin/terraform').resolve()
    real = os.environ.get('FAIG_REAL_TERRAFORM') or shutil.which('terraform')
    if not real or not Path(real).is_absolute() or Path(real).resolve() == wrapper:
        raise ValueError('cannot locate the real Terraform executable for external state')
    if not wrapper.is_file():
        raise ValueError('external Terraform launcher is missing')
    os.environ['FAIG_REAL_TERRAFORM'] = real
    os.environ['FAIG_STORAGE_PROFILE'] = str(profile_path)
    directory = str(wrapper.parent)
    parts = os.environ.get('PATH', '').split(os.pathsep)
    if directory not in parts:
        os.environ['PATH'] = directory + os.pathsep + os.environ.get('PATH', '')
    return real
