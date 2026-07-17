#!/usr/bin/env python3
"""No-apply release smoke tests for the FortiAIGate demo repo."""

from __future__ import annotations

import argparse
import fnmatch
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_MODULES = [
    "terraform/aws-ecr",
    "terraform/aws-prep",
    "terraform/aws-ec2-k3s",
    "terraform/aws-fortigate",
    "terraform/aws-fortiweb",
]
REQUIRED_PATHS = [
    "CHANGELOG.md",
    "README.md",
    "scripts/automated_quickstart.py",
    "scripts/automated_teardown.py",
    "scripts/instruction_profiles.py",
    "scripts/scenario_profiles.py",
    "scripts/user_profile.py",
    "terraform/user.tfvars.example",
    "ansible/group_vars/system.yml",
    "ansible/group_vars/user.yml.example",
]
FORBIDDEN_TRACKED_PATTERNS = [
    "terraform/common.tfvars",
    "terraform/*/terraform.tfvars",
    "terraform/*/99-local.auto.tfvars",
    "terraform/*/*.tfstate",
    "terraform/*/*.tfstate.backup",
    "ansible/group_vars/user.yml",
    "ansible/group_vars/all.yml",
    "ansible/group_vars/env.yml",
    "ansible/group_vars/images.yml",
    "chatbot/instructions/local/*",
    "*.lic",
    ".env",
]


class SmokeFailure(RuntimeError):
    """Raised when one or more smoke checks fail."""


def run(
    cmd: list[str], *, check: bool = True, show_stdout: bool = True
) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if show_stdout and result.stdout.strip():
        print(result.stdout.rstrip())
    if check and result.returncode != 0:
        if not show_stdout and result.stdout.strip():
            print(result.stdout.rstrip())
        raise SmokeFailure(f"Command failed with rc={result.returncode}: {' '.join(cmd)}")
    return result


def check_required_paths() -> None:
    missing = [path for path in REQUIRED_PATHS if not (REPO_ROOT / path).exists()]
    if missing:
        raise SmokeFailure("Missing required repo paths: " + ", ".join(missing))
    print("ok required paths")


def check_python_compile() -> None:
    for path in sorted((REPO_ROOT / "scripts").glob("*.py")):
        py_compile.compile(str(path), doraise=True)
    print("ok python compile")


def check_script_help() -> None:
    for script in [
        "scripts/user_profile.py",
        "scripts/instruction_profiles.py",
        "scripts/scenario_profiles.py",
        "scripts/automated_quickstart.py",
        "scripts/automated_teardown.py",
        "scripts/smoke_test.py",
    ]:
        run([sys.executable, script, "--help"], show_stdout=False)


def check_tracked_secrets() -> None:
    result = run(["git", "ls-files"], check=True, show_stdout=False)
    tracked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    matches: list[str] = []
    for path in tracked:
        for pattern in FORBIDDEN_TRACKED_PATTERNS:
            if fnmatch.fnmatch(path, pattern):
                matches.append(path)
                break
    if matches:
        raise SmokeFailure("Forbidden tracked local/secret files: " + ", ".join(matches))
    print("ok tracked file guard")


def check_user_tfvars_symlinks() -> None:
    problems: list[str] = []
    for module in TERRAFORM_MODULES:
        path = REPO_ROOT / module / "50-user.auto.tfvars"
        if not path.is_symlink():
            problems.append(f"{path.relative_to(REPO_ROOT)} is not a symlink")
            continue
        if path.readlink() != Path("../user.tfvars"):
            problems.append(f"{path.relative_to(REPO_ROOT)} points to {path.readlink()}")
    if problems:
        raise SmokeFailure("; ".join(problems))
    print("ok terraform user tfvars symlinks")


def check_terraform_fmt(strict_tools: bool) -> None:
    if not shutil.which("terraform"):
        message = "terraform not found; skipping terraform fmt checks"
        if strict_tools:
            raise SmokeFailure(message)
        print(f"skip {message}")
        return
    run(["terraform", "fmt", "-check", *TERRAFORM_MODULES])


def check_ansible_syntax(strict_tools: bool, playbooks: list[Path]) -> None:
    if not shutil.which("ansible-playbook"):
        message = "ansible-playbook not found; skipping Ansible syntax checks"
        if strict_tools:
            raise SmokeFailure(message)
        print(f"skip {message}")
        return
    for playbook in playbooks:
        run(
            ["ansible-playbook", "--syntax-check", str(playbook.relative_to(REPO_ROOT))],
            show_stdout=False,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run no-apply release smoke checks. This does not run terraform apply, terraform destroy, or Ansible deployment tasks."
    )
    parser.add_argument("--skip-terraform", action="store_true", help="Skip terraform fmt checks.")
    parser.add_argument("--skip-ansible", action="store_true", help="Skip ansible-playbook syntax checks.")
    parser.add_argument(
        "--strict-tools",
        action="store_true",
        help="Fail when terraform or ansible-playbook is missing instead of skipping that check.",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        default=[],
        help="Limit Ansible syntax checks to one playbook path. Can be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    playbooks = (
        [REPO_ROOT / playbook for playbook in args.playbook]
        if args.playbook
        else sorted((REPO_ROOT / "ansible/playbooks").glob("*.yml"))
    )
    try:
        check_required_paths()
        check_python_compile()
        check_script_help()
        check_tracked_secrets()
        check_user_tfvars_symlinks()
        if not args.skip_terraform:
            check_terraform_fmt(args.strict_tools)
        if not args.skip_ansible:
            check_ansible_syntax(args.strict_tools, playbooks)
    except (SmokeFailure, py_compile.PyCompileError) as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1
    print("\nPASS: no-apply smoke checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
