#!/usr/bin/env python3
"""Create a local backup of FortiAIGate demo operator config and state.

This is intentionally broader than the automated quick start's pre-edit backup:
it includes generated Ansible values and local Terraform state so an operator can
recover or import existing resources more easily.
"""

from __future__ import annotations

import argparse
import datetime as dt
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def collect_files() -> list[Path]:
    files: set[Path] = set()

    terraform_root = REPO_ROOT / "terraform"
    if terraform_root.exists():
        for pattern in ("*.tfvars", "*.tfstate", "*.tfstate.backup"):
            files.update(path for path in terraform_root.rglob(pattern) if path.is_file() or path.is_symlink())

        state_dirs = [path for path in terraform_root.rglob("terraform.tfstate.d") if path.is_dir()]
        for state_dir in state_dirs:
            files.update(path for path in state_dir.rglob("*") if path.is_file() or path.is_symlink())

    ansible_group_vars = REPO_ROOT / "ansible/group_vars"
    if ansible_group_vars.exists():
        for pattern in ("*.yml", "*.yaml"):
            files.update(
                path
                for path in ansible_group_vars.glob(pattern)
                if (path.is_file() or path.is_symlink()) and not path.name.endswith((".example.yml", ".example.yaml"))
                and not path.name.endswith((".yml.example", ".yaml.example"))
                and path.name != "system.yml"
            )

    ansible_inventory = REPO_ROOT / "ansible/inventory"
    if ansible_inventory.exists():
        files.update(
            path
            for path in ansible_inventory.glob("*.ini")
            if (path.is_file() or path.is_symlink()) and not path.name.endswith(".example.ini")
        )

    return sorted(files)


def create_backup(backup_dir: Path, archive_prefix: str, dry_run: bool) -> Path | None:
    files = collect_files()
    if not files:
        print("No local config, generated values, or Terraform state files found to back up.")
        return None

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = backup_dir / f"{archive_prefix}-{timestamp}.tar.gz"

    print("Files selected for backup:")
    for path in files:
        print(f"- {path.relative_to(REPO_ROOT)}")

    if dry_run:
        print(f"\nDry run only. Archive would be created at: {archive_path}")
        return archive_path

    backup_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(REPO_ROOT), recursive=False)

    print(f"\nCreated backup: {archive_path}")
    return archive_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up local FortiAIGate demo tfvars, generated Ansible values, inventory, and Terraform state."
    )
    parser.add_argument(
        "--backup-dir",
        default=str(REPO_ROOT.parent / "backup"),
        help="Directory for tar.gz backups. Default: repo_root/../backup.",
    )
    parser.add_argument(
        "--archive-prefix",
        default="fortiaigate-demo-full-backup",
        help="Archive filename prefix. A timestamp and .tar.gz are appended.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be backed up without creating an archive.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_backup(Path(args.backup_dir).expanduser(), args.archive_prefix, args.dry_run)


if __name__ == "__main__":
    main()
