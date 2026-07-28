#!/usr/bin/env python3
"""Remove local generated inventory and vars without touching the lab."""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

LOCAL_GENERATED_FILES = [
    "ansible/inventory/local.generated.ini",
    "ansible/inventory/fortigate.local.generated.ini",
    "ansible/inventory/fortiweb.local.generated.ini",
    "ansible/group_vars/local.generated.yml",
    "ansible/group_vars/registry.generated.yml",
    "ansible/group_vars/local.secrets.yml",
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
    return [REPO_ROOT / path for path in LOCAL_GENERATED_FILES if (REPO_ROOT / path).exists()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove local generated vars/inventories without deleting k3s, apps, images, appliances, or Terraform state."
    )
    parser.add_argument("--dry-run", action="store_true", help="List files that would be removed, but do not remove them.")
    parser.add_argument("--yes", "-y", action="store_true", help="Do not prompt before removing local generated files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    check_repo_root()

    print("FortiAIGate local generated var cleanup")
    print(f"Repo root: {REPO_ROOT}")
    print("This removes only ignored local generated vars/inventories from this checkout.")
    print("It does not uninstall k3s, FortiAIGate, Ollama, Docker images, FortiGate, FortiWeb, or Terraform state.")

    files = existing_local_files()
    print_header("Local Generated Files")
    if not files:
        print("No local generated files found.")
        return

    for path in files:
        print(f"- {path.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("\nDry run only; no files were removed.")
        return

    if not args.yes and not prompt_yes_no("Remove these local generated files?", False):
        print("Stopped. No files were removed.")
        return

    print_header("Removing Files")
    for path in files:
        path.unlink()
        print(f"removed: {path.relative_to(REPO_ROOT)}")

    print("\nLocal generated vars/inventories were removed. Run scripts/local_setup.py to regenerate them.")


if __name__ == "__main__":
    main()
