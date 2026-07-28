#!/usr/bin/env python3
"""Export/import local generated inventory and vars without touching the lab."""

from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
import time
from pathlib import Path
from pathlib import PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_VARS_ARCHIVE = REPO_ROOT.parent / "local_vars_backup.tgz"
LOCAL_VARS_ARCHIVE_VERSION = 1
MANIFEST_PATH = ".faig-local-vars.json"

LOCAL_GENERATED_FILES = [
    Path("ansible/inventory/local.generated.ini"),
    Path("ansible/inventory/fortigate.local.generated.ini"),
    Path("ansible/inventory/fortiweb.local.generated.ini"),
    Path("ansible/group_vars/local.generated.yml"),
    Path("ansible/group_vars/registry.generated.yml"),
    Path("ansible/group_vars/local.secrets.yml"),
]


def print_header(message: str) -> None:
    print(f"\n== {message} ==")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        value = input(f"{prompt}{suffix}: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Answer yes or no.")


def check_repo_root() -> None:
    required = ["terraform", "ansible", "scripts", "ansible.cfg"]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"Repository root check failed. Missing: {', '.join(missing)}")


def existing_local_files() -> list[Path]:
    return [path for path in LOCAL_GENERATED_FILES if (REPO_ROOT / path).exists()]


def resolve_archive_path(path: Path | None) -> Path:
    archive_path = path or DEFAULT_LOCAL_VARS_ARCHIVE
    archive_path = archive_path.expanduser()
    if not archive_path.is_absolute():
        archive_path = (REPO_ROOT / archive_path).resolve()
    return archive_path


def safe_member_path(member_name: str) -> Path:
    pure = PurePosixPath(member_name)
    if pure.is_absolute() or ".." in pure.parts:
        raise SystemExit(f"Refusing unsafe archive path: {member_name}")
    return Path(*pure.parts)


def print_local_files(files: list[Path]) -> None:
    print_header("Local Generated Files")
    if not files:
        print("No local generated files found.")
        return

    for path in files:
        print(f"- {path.as_posix()}")


def export_local_vars(archive_arg: Path | None, *, dry_run: bool, yes: bool) -> None:
    archive_path = resolve_archive_path(archive_arg)
    files = existing_local_files()
    print_local_files(files)
    if not files:
        return

    print_header("Local Vars Backup")
    print(f"Backup archive: {archive_path}")
    print("This archive may contain appliance API tokens or managed passwords. Treat it as sensitive.")

    if dry_run:
        print("\nDry run only; no archive was created and no files were removed.")
        return

    if archive_path.exists() and not yes and not prompt_yes_no("Overwrite existing backup archive?", False):
        print("Stopped. No files were removed.")
        return

    if not yes and not prompt_yes_no("Back up and remove these local generated files?", False):
        print("Stopped. No files were removed.")
        return

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "local_vars_archive_version": LOCAL_VARS_ARCHIVE_VERSION,
        "created_at": int(time.time()),
        "files": [path.as_posix() for path in files],
    }

    with tarfile.open(archive_path, "w:gz") as archive:
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        manifest_info = tarfile.TarInfo(MANIFEST_PATH)
        manifest_info.size = len(manifest_bytes)
        manifest_info.mtime = int(time.time())
        with tempfile.SpooledTemporaryFile() as fileobj:
            fileobj.write(manifest_bytes)
            fileobj.seek(0)
            archive.addfile(manifest_info, fileobj=fileobj)

        for path in files:
            archive.add(REPO_ROOT / path, arcname=path.as_posix(), recursive=False)

    print(f"created: {archive_path}")

    print_header("Removing Files")
    for path in files:
        (REPO_ROOT / path).unlink()
        print(f"removed: {path.as_posix()}")

    print("\nLocal generated vars/inventories were backed up and removed. Run scripts/local_setup.py to regenerate them.")


def import_local_vars(archive_arg: Path | None, *, dry_run: bool, yes: bool) -> None:
    archive_path = resolve_archive_path(archive_arg)
    if not archive_path.is_file():
        raise SystemExit(f"Local vars backup archive does not exist: {archive_path}")

    allowlist = {path.as_posix(): path for path in LOCAL_GENERATED_FILES}
    imported: list[Path] = []
    skipped: list[Path] = []

    print_header("Import Local Vars Backup")
    print(f"Backup archive: {archive_path}")
    print("This archive may contain appliance API tokens or managed passwords. Treat it as sensitive.")

    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        if MANIFEST_PATH not in names:
            raise SystemExit(f"Local vars archive is missing {MANIFEST_PATH}.")
        manifest_file = archive.extractfile(MANIFEST_PATH)
        if manifest_file is None:
            raise SystemExit(f"Local vars archive has unreadable {MANIFEST_PATH}.")
        manifest = json.loads(manifest_file.read().decode("utf-8"))
        if manifest.get("local_vars_archive_version") != LOCAL_VARS_ARCHIVE_VERSION:
            raise SystemExit(f"Unsupported local vars archive version: {manifest.get('local_vars_archive_version')}")

        restore_members = [member for member in members if member.name != MANIFEST_PATH]
        print_header("Files In Backup")
        for member in restore_members:
            print(f"- {member.name}")

        if dry_run:
            print("\nDry run only; no files were restored.")
            return

        for member in restore_members:
            member_path = safe_member_path(member.name)
            member_key = member_path.as_posix()
            if member_key not in allowlist:
                raise SystemExit(f"Refusing unexpected local vars file: {member.name}")
            if member.isdir() or member.issym() or member.islnk() or not member.isfile():
                raise SystemExit(f"Refusing non-regular local vars entry: {member.name}")

            dest = REPO_ROOT / member_path
            if dest.exists() and not yes and not prompt_yes_no(f"Overwrite {member_key}?", False):
                skipped.append(member_path)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise SystemExit(f"Could not read local vars file: {member.name}")
            dest.write_bytes(source.read())
            imported.append(member_path)

    print(f"imported from: {archive_path}")
    for path in imported:
        print(f"- {path.as_posix()}")
    for path in skipped:
        print(f"kept: {path.as_posix()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export/import local generated vars/inventories without deleting k3s, apps, images, appliances, or Terraform state."
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["export", "import"],
        default="export",
        help="Action to run. Default: export.",
    )
    parser.add_argument(
        "archive",
        nargs="?",
        type=Path,
        help=f"Backup archive path. Default: {DEFAULT_LOCAL_VARS_ARCHIVE}",
    )

    parser.add_argument("--dry-run", action="store_true", help="Show the export/import actions without changing files.")
    parser.add_argument("--yes", "-y", action="store_true", help="Do not prompt before exporting/removing or restoring files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    check_repo_root()

    print("FortiAIGate local generated var export/import")
    print(f"Repo root: {REPO_ROOT}")
    print("This backs up/restores only ignored local generated vars/inventories from this checkout.")
    print("It does not uninstall k3s, FortiAIGate, Ollama, Docker images, FortiGate, FortiWeb, or Terraform state.")

    action = args.action or "export"
    if action == "export":
        export_local_vars(args.archive, dry_run=args.dry_run, yes=args.yes)
    elif action == "import":
        import_local_vars(args.archive, dry_run=args.dry_run, yes=args.yes)
    else:
        raise SystemExit(f"Unsupported action: {action}")


if __name__ == "__main__":
    main()
