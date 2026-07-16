#!/usr/bin/env python3
"""Guided teardown for repeat FortiAIGate demo provision/deprovision cycles."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COMMANDS = ["terraform", "aws"]

TERRAFORM_MODULES = {
    "ecr": "terraform/aws-ecr",
    "ec2": "terraform/aws-ec2-k3s",
    "prep": "terraform/aws-prep",
    "fortigate": "terraform/aws-fortigate",
    "fortiweb": "terraform/aws-fortiweb",
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


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def check_repo_root() -> None:
    required = ["terraform", "ansible", "scripts", "ansible.cfg"]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"Repository root check failed. Missing: {', '.join(missing)}")


def check_required_commands() -> None:
    missing = [command for command in REQUIRED_COMMANDS if shutil.which(command) is None]
    if missing:
        raise SystemExit(f"Missing required command(s): {', '.join(missing)}")


def get_tf_string(content: str, key: str, default: str = "") -> str:
    match = re.search(rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"([^"]*)"', content)
    return match.group(1) if match else default


def quiet_command_output(argv: list[str], *, check: bool = False) -> str:
    result = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def aws_profile_uses_sso(profile: str) -> bool:
    sso_keys = ["sso_session", "sso_start_url", "sso_account_id", "sso_role_name"]
    return any(quiet_command_output(["aws", "configure", "get", key, "--profile", profile]) for key in sso_keys)


def choose_aws_login_method(profile: str) -> str:
    detected_sso = aws_profile_uses_sso(profile)
    default_method = "sso" if detected_sso else "login"
    print(
        "Profile appears to use AWS SSO/IAM Identity Center."
        if detected_sso
        else "Profile does not expose SSO settings through aws configure."
    )
    print("Login options:")
    print("1. aws sso login")
    print("2. aws login")
    print("3. stop")

    while True:
        value = prompt_text("AWS login command", default_method).strip().lower()
        if value in {"1", "sso", "aws sso login"}:
            return "sso"
        if value in {"2", "login", "aws login"}:
            return "login"
        if value in {"3", "stop", "none", "no"}:
            return "stop"
        print("Choose aws sso login, aws login, or stop.")


def aws_profile_from_user_tfvars() -> str:
    path = REPO_ROOT / "terraform/user.tfvars"
    if not path.exists():
        raise SystemExit("Cannot check AWS login because terraform/user.tfvars does not exist.")
    profile = get_tf_string(path.read_text(encoding="utf-8"), "aws_profile")
    if not profile:
        raise SystemExit("Cannot check AWS login because aws_profile is missing from terraform/user.tfvars.")
    return profile


def ensure_aws_login() -> None:
    print_header("Checking AWS Login")
    profile = aws_profile_from_user_tfvars()
    result = run_command(["aws", "sts", "get-caller-identity", "--profile", profile], check=False)
    if result.returncode == 0:
        return

    print(f"AWS caller identity check failed for profile {profile}.")
    method = choose_aws_login_method(profile)
    if method == "stop":
        raise SystemExit("AWS login is required before Terraform teardown can run.")

    if method == "sso":
        argv = ["aws", "sso", "login", "--profile", profile]
        if prompt_yes_no("Use device-code flow for aws sso login?", False):
            argv.append("--use-device-code")
    else:
        argv = ["aws", "login", "--profile", profile]
        if prompt_yes_no("Pass --use-device-code to aws login?", False):
            argv.append("--use-device-code")

    run_command(argv)
    run_command(["aws", "sts", "get-caller-identity", "--profile", profile])


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


def terraform_destroy(module_path: str, *, auto_approve: bool) -> None:
    argv = ["terraform", "-chdir=" + module_path, "destroy"]
    if auto_approve:
        argv.append("-auto-approve")
    run_command(argv)


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

    if not has_lifecycle and not has_local_file:
        print("No ECR lifecycle policy or generated local output resources are tracked in state.")
        return

    print("Running full ECR module destroy after repository state removal.")
    print("This preserves ECR repositories because they are removed from state before the ECR destroy.")
    terraform_destroy(module_path, auto_approve=auto_approve)


def destroy_module(label: str, module_path: str, auto_approve: bool) -> None:
    print_header(f"Terraform Destroy: {label}")
    state_addresses = terraform_state_list(module_path)
    if not state_addresses:
        print(f"No Terraform resources are tracked in {module_path}. Skipping destroy.")
        return
    terraform_destroy(module_path, auto_approve=auto_approve)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preserve ECR repositories and destroy demo AWS infrastructure."
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Pass -auto-approve to Terraform destroy commands.",
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
        "--skip-fortigate",
        action="store_true",
        help="Skip terraform/aws-fortigate destroy.",
    )
    parser.add_argument(
        "--skip-fortiweb",
        action="store_true",
        help="Skip terraform/aws-fortiweb destroy.",
    )
    parser.add_argument(
        "--skip-appliances",
        action="store_true",
        help="Skip both optional FortiGate and FortiWeb appliance destroys.",
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
    check_required_commands()

    print("FortiAIGate automated teardown")
    print(f"Repo root: {REPO_ROOT}")
    print("Planned order:")
    print("1. Destroy terraform/aws-fortiweb if state exists.")
    print("2. Destroy terraform/aws-fortigate if state exists.")
    print("3. Destroy terraform/aws-ec2-k3s.")
    print("4. Destroy terraform/aws-prep.")
    print("5. Remove ECR repository resources from Terraform state so repositories are not deleted.")
    print("6. Destroy ECR lifecycle policy and generated local output resources only.")

    if not args.yes and not prompt_yes_no("Proceed with teardown?", False):
        raise SystemExit("Stopped before teardown.")

    ensure_aws_login()

    if args.skip_appliances or args.skip_fortiweb:
        print_header("Terraform: FortiWeb Appliance")
        print("Skipped by --skip-appliances or --skip-fortiweb.")
    else:
        terraform_init(TERRAFORM_MODULES["fortiweb"])
        destroy_module("FortiWeb Appliance", TERRAFORM_MODULES["fortiweb"], args.auto_approve)

    if args.skip_appliances or args.skip_fortigate:
        print_header("Terraform: FortiGate Appliance")
        print("Skipped by --skip-appliances or --skip-fortigate.")
    else:
        terraform_init(TERRAFORM_MODULES["fortigate"])
        destroy_module("FortiGate Appliance", TERRAFORM_MODULES["fortigate"], args.auto_approve)

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

    if args.skip_ecr:
        print_header("Terraform: ECR")
        print("Skipped by --skip-ecr.")
    else:
        terraform_init(TERRAFORM_MODULES["ecr"])
        remove_ecr_repository_state(TERRAFORM_MODULES["ecr"])
        destroy_ecr_lifecycle_and_outputs(TERRAFORM_MODULES["ecr"], args.auto_approve)

    print_header("Automated Teardown Complete")
    print("ECR repositories were protected by removing repository resources from Terraform state.")
    print("Run scripts/automated_quickstart.py when ready to provision again.")


if __name__ == "__main__":
    main()
