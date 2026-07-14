#!/usr/bin/env python3
"""Guided teardown for repeat FortiAIGate demo provision/deprovision cycles."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

TERRAFORM_MODULES = {
    "ecr": "terraform/aws-ecr",
    "ec2": "terraform/aws-ec2-k3s",
    "prep": "terraform/aws-prep",
}


def print_header(message: str) -> None:
    print(f"\n== {message} ==")


def run_command(
    argv: list[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(argv)}")
    result = subprocess.run(
        argv,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout, end="")
        if capture and result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


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


def terraform_init(module_path: str) -> None:
    run_command(["terraform", "-chdir=" + module_path, "init"])


def terraform_state_list(module_path: str) -> list[str]:
    result = run_command(
        ["terraform", "-chdir=" + module_path, "state", "list"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def terraform_state_rm(module_path: str, address: str) -> None:
    result = run_command(
        ["terraform", "-chdir=" + module_path, "state", "rm", address],
        check=False,
    )
    if result.returncode != 0:
        print(f"Warning: failed to remove {address} from state. It may already be absent.")


def terraform_destroy(module_path: str, *, auto_approve: bool, targets: list[str] | None = None) -> None:
    argv = ["terraform", "-chdir=" + module_path, "destroy"]
    for target in targets or []:
        argv.append(f"-target={target}")
    if auto_approve:
        argv.append("-auto-approve")
    run_command(argv)


def run_backup(backup_dir: Path, skip_backup: bool) -> None:
    print_header("Backup")
    if skip_backup:
        print("Skipped by --skip-backup.")
        return

    run_command(
        [
            sys.executable,
            "scripts/backup_config.py",
            "--backup-dir",
            str(backup_dir.expanduser()),
            "--archive-prefix",
            "fortiaigate-demo-teardown-backup",
        ]
    )


def remove_ecr_repository_state(module_path: str) -> None:
    print_header("ECR Repository State Protection")
    state_addresses = terraform_state_list(module_path)
    repository_addresses = [
        address for address in state_addresses if address.startswith("aws_ecr_repository.this")
    ]

    if not repository_addresses:
        print("No ECR repository resources are currently tracked in Terraform state.")
        print("ECR repositories are already protected from terraform destroy in this state.")
        return

    print("Removing these ECR repository resources from Terraform state only:")
    for address in repository_addresses:
        print(f"- {address}")
    print("The repositories remain in AWS. Only local Terraform state is changed.")

    for address in repository_addresses:
        terraform_state_rm(module_path, address)


def destroy_ecr_lifecycle_and_outputs(module_path: str, auto_approve: bool) -> None:
    print_header("Terraform Destroy: ECR Lifecycle And Generated Outputs")
    state_addresses = terraform_state_list(module_path)
    has_lifecycle = any(address.startswith("aws_ecr_lifecycle_policy.this") for address in state_addresses)
    has_local_file = "local_file.ansible_ecr_vars" in state_addresses

    targets: list[str] = []
    if has_lifecycle:
        targets.append("aws_ecr_lifecycle_policy.this")
    if has_local_file:
        targets.append("local_file.ansible_ecr_vars")

    if not targets:
        print("No ECR lifecycle policy or generated local output resources are tracked in state.")
        return

    terraform_destroy(module_path, auto_approve=auto_approve, targets=targets)


def destroy_module(label: str, module_path: str, auto_approve: bool) -> None:
    print_header(f"Terraform Destroy: {label}")
    state_addresses = terraform_state_list(module_path)
    if not state_addresses:
        print(f"No Terraform resources are tracked in {module_path}. Skipping destroy.")
        return
    terraform_destroy(module_path, auto_approve=auto_approve)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up local state/config, preserve ECR repositories, and destroy demo AWS infrastructure."
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Pass -auto-approve to Terraform destroy commands.",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(REPO_ROOT.parent / "backup"),
        help="Directory for teardown backups. Default: repo_root/../backup.",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Do not create a backup archive before teardown.",
    )
    parser.add_argument(
        "--skip-ecr",
        action="store_true",
        help="Skip ECR state protection and ECR lifecycle/local-output destroy.",
    )
    parser.add_argument(
        "--skip-ec2",
        action="store_true",
        help="Skip terraform/aws-ec2-k3s destroy.",
    )
    parser.add_argument(
        "--skip-prep",
        action="store_true",
        help="Skip terraform/aws-prep destroy.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the script-level destructive action confirmation prompt.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    check_repo_root()

    print("FortiAIGate automated teardown")
    print(f"Repo root: {REPO_ROOT}")
    print("Planned order:")
    print("1. Back up local config, generated values, inventory, and Terraform state.")
    print("2. Remove ECR repository resources from Terraform state so repositories are not deleted.")
    print("3. Destroy ECR lifecycle policy and generated local output resources only.")
    print("4. Destroy terraform/aws-ec2-k3s.")
    print("5. Destroy terraform/aws-prep.")

    if not args.yes and not prompt_yes_no("Proceed with teardown?", False):
        raise SystemExit("Stopped before teardown.")

    run_backup(Path(args.backup_dir), args.skip_backup)

    if args.skip_ecr:
        print_header("Terraform: ECR")
        print("Skipped by --skip-ecr.")
    else:
        terraform_init(TERRAFORM_MODULES["ecr"])
        remove_ecr_repository_state(TERRAFORM_MODULES["ecr"])
        destroy_ecr_lifecycle_and_outputs(TERRAFORM_MODULES["ecr"], args.auto_approve)

    if args.skip_ec2:
        print_header("Terraform: EC2 k3s Foundation")
        print("Skipped by --skip-ec2.")
    else:
        terraform_init(TERRAFORM_MODULES["ec2"])
        destroy_module("EC2 k3s Foundation", TERRAFORM_MODULES["ec2"], args.auto_approve)

    if args.skip_prep:
        print_header("Terraform: AWS Prep")
        print("Skipped by --skip-prep.")
    else:
        terraform_init(TERRAFORM_MODULES["prep"])
        destroy_module("AWS Prep", TERRAFORM_MODULES["prep"], args.auto_approve)

    print_header("Automated Teardown Complete")
    print("ECR repositories were protected by removing repository resources from Terraform state.")
    print("Run scripts/automated_quickstart.py when ready to provision again.")


if __name__ == "__main__":
    main()
