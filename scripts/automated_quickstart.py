#!/usr/bin/env python3
"""Guided Terraform bootstrap for the FortiAIGate demo.

This script intentionally stops after Terraform ECR, AWS prep, and EC2 k3s
foundation. Image publishing, k3s bootstrap, and application deployment remain
explicit follow-on steps.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

LOCAL_FILE_PAIRS = [
    ("terraform/common.tfvars.example", "terraform/common.tfvars"),
    ("terraform/aws-ecr/terraform.tfvars.example", "terraform/aws-ecr/terraform.tfvars"),
    ("terraform/aws-prep/terraform.tfvars.example", "terraform/aws-prep/terraform.tfvars"),
    ("terraform/aws-ec2-k3s/terraform.tfvars.example", "terraform/aws-ec2-k3s/terraform.tfvars"),
    ("ansible/group_vars/env.example.yml", "ansible/group_vars/env.yml"),
    ("ansible/group_vars/all.example.yml", "ansible/group_vars/all.yml"),
    ("ansible/group_vars/images.example.yml", "ansible/group_vars/images.yml"),
]

REQUIRED_COMMANDS = ["terraform", "aws", "ansible-playbook"]
TERRAFORM_MODULES = [
    ("ECR registry", "terraform/aws-ecr"),
    ("AWS prep", "terraform/aws-prep"),
    ("EC2 k3s foundation", "terraform/aws-ec2-k3s"),
]
APPLICATION_PLAYBOOKS = [
    ("LiteLLM proxy", "deploy_litellm.yml", "status_litellm.yml"),
    ("Open WebUI", "deploy_openwebui.yml", "status_openwebui.yml"),
    ("custom chatbot UI", "deploy_chatbots.yml", "status_chatbots.yml"),
    ("demo home page", "deploy_demo_home.yml", "status_demo_home.yml"),
]
SKIP_SSH_PRIVATE_KEY_NAMES = {
    "authorized_keys",
    "config",
    "environment",
    "known_hosts",
    "known_hosts.old",
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


def command_output(argv: list[str], *, check: bool = True) -> str:
    result = run_command(argv, capture=True, check=check)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
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


def check_host_os() -> None:
    system = platform.system()
    if system in {"Darwin", "Linux"}:
        print(f"Host OS: {system}")
        return
    if system == "Windows":
        print("Windows detected. WSL2 Ubuntu is strongly recommended for this workflow.")
        return
    print(f"Host OS {system} is untested for this workflow.")


def check_requirements() -> None:
    print_header("Checking Requirements")
    check_host_os()
    missing = []
    for command in REQUIRED_COMMANDS:
        path = shutil.which(command)
        if path:
            print(f"{command}: {path}")
        else:
            missing.append(command)
    if missing:
        raise SystemExit(f"Missing required commands: {', '.join(missing)}")


def collect_private_config_files() -> list[Path]:
    files: list[Path] = []
    terraform_root = REPO_ROOT / "terraform"
    ansible_group_vars = REPO_ROOT / "ansible/group_vars"

    if terraform_root.exists():
        files.extend(path for path in terraform_root.rglob("*.tfvars") if path.is_file() or path.is_symlink())

    if ansible_group_vars.exists():
        files.extend(
            path
            for path in ansible_group_vars.glob("*.yml")
            if (path.is_file() or path.is_symlink())
            and not path.name.endswith(".example.yml")
            and not path.name.endswith(".generated.yml")
        )

    return sorted(set(files))


def backup_private_config(backup_dir: Path) -> Path | None:
    print_header("Backing Up Local Config")
    files = collect_private_config_files()
    if not files:
        print("No existing private tfvars/YAML config files found to back up.")
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = backup_dir / f"fortiaigate-demo-config-{timestamp}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(REPO_ROOT), recursive=False)

    print(f"created: {archive_path}")
    print("included:")
    for path in files:
        print(f"- {path.relative_to(REPO_ROOT)}")
    return archive_path


def copy_missing_examples() -> None:
    print_header("Preparing Local Config Files")
    for source_rel, dest_rel in LOCAL_FILE_PAIRS:
        source = REPO_ROOT / source_rel
        dest = REPO_ROOT / dest_rel
        if dest.exists():
            print(f"exists: {dest_rel}")
            continue
        shutil.copyfile(source, dest)
        print(f"created: {dest_rel} from {source_rel}")


def list_aws_profiles() -> list[str]:
    output = command_output(["aws", "configure", "list-profiles"], check=False)
    profiles = [line.strip() for line in output.splitlines() if line.strip()]
    return profiles


def choose_aws_profile(default_profile: str = "") -> str:
    print_header("AWS Profile")
    profiles = list_aws_profiles()
    if profiles:
        for index, profile in enumerate(profiles, start=1):
            marker = " (current)" if profile == default_profile else ""
            print(f"{index}. {profile}{marker}")
    else:
        print("No AWS profiles were returned by aws configure list-profiles.")

    while True:
        selected = prompt_text("AWS profile name or number", default_profile or (profiles[0] if profiles else ""))
        if selected.isdigit() and profiles:
            index = int(selected)
            if 1 <= index <= len(profiles):
                return profiles[index - 1]
        if selected:
            return selected
        print("Enter an AWS profile.")


def ensure_aws_login(profile: str) -> None:
    print_header("Checking AWS Login")
    result = run_command(["aws", "sts", "get-caller-identity", "--profile", profile], check=False)
    if result.returncode == 0:
        return
    print("AWS caller identity check failed.")
    if prompt_yes_no(f"Run aws sso login for profile {profile} now?", True):
        run_command(["aws", "sso", "login", "--profile", profile])
        run_command(["aws", "sts", "get-caller-identity", "--profile", profile])
    else:
        raise SystemExit("AWS login is required before Terraform can run.")


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def get_tf_string(content: str, key: str, default: str = "") -> str:
    match = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"', content)
    return match.group(1) if match else default


def get_tf_list_strings(content: str, key: str) -> list[str]:
    match = re.search(rf"(?ms)^\s*{re.escape(key)}\s*=\s*\[(.*?)\]", content)
    if not match:
        single = get_tf_string(content, key)
        return [single] if single else []
    return re.findall(r'"([^"]+)"', match.group(1))


def get_tf_map_strings(content: str, key: str) -> dict[str, str]:
    match = re.search(rf"(?ms)^\s*{re.escape(key)}\s*=\s*\{{(.*?)\}}", content)
    if not match:
        return {}
    pairs: dict[str, str] = {}
    for pair_match in re.finditer(r'(?m)^\s*"?([^"\s=]+)"?\s*=\s*"([^"]*)"', match.group(1)):
        pairs[pair_match.group(1)] = pair_match.group(2)
    return pairs


def set_tf_string(content: str, key: str, value: str) -> str:
    replacement = f'{key} = "{value}"'
    pattern = rf'(?m)^\s*{re.escape(key)}\s*=\s*"[^"]*"'
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_tf_list_strings(content: str, key: str, values: list[str]) -> str:
    rendered_values = "\n".join(f'  "{value}",' for value in values)
    replacement = f"{key} = [\n{rendered_values}\n]"
    list_pattern = rf"(?ms)^\s*{re.escape(key)}\s*=\s*\[.*?\]"
    if re.search(list_pattern, content):
        return re.sub(list_pattern, replacement, content, count=1)
    string_pattern = rf'(?m)^\s*{re.escape(key)}\s*=\s*"[^"]*"'
    if re.search(string_pattern, content):
        return re.sub(string_pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_tf_map_strings(content: str, key: str, values: dict[str, str]) -> str:
    if values:
        rendered_values = "\n".join(f'  {map_key} = "{map_value}"' for map_key, map_value in sorted(values.items()))
        replacement = f"{key} = {{\n{rendered_values}\n}}"
    else:
        replacement = f"{key} = {{}}"
    map_pattern = rf"(?ms)^\s*{re.escape(key)}\s*=\s*\{{.*?\}}"
    if re.search(map_pattern, content):
        return re.sub(map_pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def parse_tags_text(value: str) -> dict[str, str]:
    if not value.strip():
        return {}
    tags: dict[str, str] = {}
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise SystemExit(f"Invalid tag '{entry}'. Use key=value.")
        tag_key, tag_value = entry.split("=", 1)
        tag_key = tag_key.strip()
        tag_value = tag_value.strip()
        if not tag_key:
            raise SystemExit("Tag keys cannot be empty.")
        tags[tag_key] = tag_value
    return tags


def render_tags_prompt_default(tags: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(tags.items()))


def validate_cidr_list(values: list[str], label: str) -> list[str]:
    validated: list[str] = []
    for value in values:
        if "/" not in value:
            raise SystemExit(f"{label} must use CIDR notation with a prefix length. Invalid value: {value}. Example: 203.0.113.10/32")
        try:
            validated.append(str(ipaddress.ip_network(value, strict=False)))
        except ValueError as error:
            raise SystemExit(f"{label} must contain valid CIDR blocks. Invalid value: {value}. Error: {error}")
    return validated


def get_yaml_scalar(content: str, key: str, default: str = "") -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*(.*)$", content)
    if not match:
        return default
    return match.group(1).strip().strip('"').strip("'")


def set_yaml_scalar(content: str, key: str, value: str) -> str:
    replacement = f"{key}: {value}"
    pattern = rf"(?m)^\s*{re.escape(key)}:\s*.*$"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def configure_common_tfvars(profile: str) -> tuple[str, str, str, list[str]]:
    print_header("Shared Terraform Config")
    path = REPO_ROOT / "terraform/common.tfvars"
    content = read_file(path)

    current_region = get_tf_string(content, "aws_region", "us-east-1")
    profile_region = command_output(["aws", "configure", "get", "region", "--profile", profile], check=False)
    default_region = profile_region or current_region or "us-east-1"
    current_prefix = get_tf_string(content, "name_prefix", "fortiaigate-demo")
    current_cidrs = get_tf_list_strings(content, "allowed_ingress_cidr")
    current_tags = get_tf_map_strings(content, "tags")

    region = prompt_text("AWS region", default_region)
    name_prefix = prompt_text("Deployment name prefix", current_prefix)
    cidr_default = ", ".join(current_cidrs) if current_cidrs else ""
    cidr_text = prompt_text("Trusted source CIDR list, comma-separated", cidr_default)
    cidrs = [entry.strip() for entry in cidr_text.split(",") if entry.strip()]
    if not cidrs:
        raise SystemExit("At least one trusted source CIDR is required.")
    cidrs = validate_cidr_list(cidrs, "Trusted source CIDR list")
    tags_text = prompt_text("Optional Terraform tags, comma-separated key=value", render_tags_prompt_default(current_tags))
    tags = parse_tags_text(tags_text)

    content = set_tf_string(content, "aws_profile", profile)
    content = set_tf_string(content, "aws_region", region)
    content = set_tf_string(content, "name_prefix", name_prefix)
    content = set_tf_list_strings(content, "allowed_ingress_cidr", cidrs)
    content = set_tf_map_strings(content, "tags", tags)
    write_file(path, content)
    print(f"updated: {path.relative_to(REPO_ROOT)}")

    return profile, region, name_prefix, cidrs


def configure_ansible_env(profile: str, region: str) -> None:
    path = REPO_ROOT / "ansible/group_vars/env.yml"
    content = read_file(path)
    content = set_yaml_scalar(content, "aws_profile", profile)
    content = set_yaml_scalar(content, "aws_region", region)
    write_file(path, content)
    print(f"updated: {path.relative_to(REPO_ROOT)}")


def list_ec2_key_pairs(profile: str, region: str) -> list[str]:
    output = command_output(
        [
            "aws",
            "ec2",
            "describe-key-pairs",
            "--profile",
            profile,
            "--region",
            region,
            "--query",
            "KeyPairs[].KeyName",
            "--output",
            "text",
        ],
        check=False,
    )
    return [key.strip() for key in re.split(r"\s+", output) if key.strip()]


def choose_ec2_key_pair(profile: str, region: str, default_key: str = "") -> str:
    print_header("EC2 SSH Key Pair")
    keys = list_ec2_key_pairs(profile, region)
    if keys:
        print(f"Available EC2 key pairs in {region}:")
        for index, key_name in enumerate(keys, start=1):
            marker = " (current)" if key_name == default_key else ""
            print(f"{index}. {key_name}{marker}")
    else:
        print(f"No EC2 key pairs were returned for profile {profile} in {region}.")

    while True:
        selected = prompt_text("EC2 key pair name or number", default_key or (keys[0] if keys else ""))
        if selected.isdigit() and keys:
            index = int(selected)
            if 1 <= index <= len(keys):
                return keys[index - 1]
        if selected:
            return selected
        print("Enter an EC2 key pair name.")


def display_path(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(home.resolve()))
    except ValueError:
        return str(path)


def list_local_ssh_private_keys() -> list[Path]:
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return []

    candidates: list[Path] = []
    for path in ssh_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in SKIP_SSH_PRIVATE_KEY_NAMES:
            continue
        if path.name.endswith(".pub"):
            continue
        if path.name.startswith("known_hosts"):
            continue
        candidates.append(path)
    return sorted(candidates)


def choose_local_ssh_private_key(default_private_key: str, key_name: str) -> str:
    print_header("Local SSH Private Key")
    candidates = list_local_ssh_private_keys()
    candidate_display = [display_path(path) for path in candidates]

    fallback = default_private_key or f"~/.ssh/{key_name}"
    if candidates:
        print("Likely private keys in ~/.ssh:")
        for index, path_text in enumerate(candidate_display, start=1):
            marker = " (current)" if path_text == default_private_key else ""
            print(f"{index}. {path_text}{marker}")
        print("m. Enter a path manually")

    while True:
        selected = prompt_text("Local SSH private key number, path, or m", fallback)
        if selected.lower() == "m":
            manual = prompt_text("Local SSH private key path", fallback)
            if manual:
                return manual
        if selected.isdigit() and candidates:
            index = int(selected)
            if 1 <= index <= len(candidates):
                return candidate_display[index - 1]
        if selected:
            return selected
        print("Enter a private key path.")


def configure_ec2_tfvars(profile: str, region: str) -> None:
    path = REPO_ROOT / "terraform/aws-ec2-k3s/terraform.tfvars"
    content = read_file(path)
    current_key_name = get_tf_string(content, "ssh_key_name")
    current_private_key = get_tf_string(content, "ssh_private_key_file")

    key_name = choose_ec2_key_pair(profile, region, current_key_name)
    private_key = choose_local_ssh_private_key(current_private_key, key_name)

    content = set_tf_string(content, "ssh_key_name", key_name)
    content = set_tf_string(content, "ssh_private_key_file", private_key)
    write_file(path, content)
    print(f"updated: {path.relative_to(REPO_ROOT)}")


def parse_ecr_tfvars() -> tuple[str, list[str]]:
    content = read_file(REPO_ROOT / "terraform/aws-ecr/terraform.tfvars")
    repo_prefix = get_tf_string(content, "repo_prefix", "fortiaigate")
    repositories = get_tf_list_strings(content, "repositories")
    if not repositories:
        raise SystemExit("No repositories found in terraform/aws-ecr/terraform.tfvars.")
    return repo_prefix, repositories


def prompt_manual_review() -> None:
    print_header("Manual Review Before Terraform")
    print("Review these files before continuing:")
    review_files = [
        "terraform/common.tfvars",
        "terraform/aws-ecr/terraform.tfvars",
        "terraform/aws-prep/terraform.tfvars",
        "terraform/aws-ec2-k3s/terraform.tfvars",
        "ansible/group_vars/env.yml",
        "ansible/group_vars/all.yml",
        "ansible/group_vars/images.yml",
    ]
    for path in review_files:
        print(f"- {path}")
    print("\nCritical EC2 values usually needing edits:")
    print("- terraform/aws-ec2-k3s/terraform.tfvars: ssh_key_name")
    print("- terraform/aws-ec2-k3s/terraform.tfvars: ssh_private_key_file")
    print("- terraform/aws-ec2-k3s/terraform.tfvars: instance_type")
    print("\nAnsible files are prepared now. The next phase can publish images and deploy the demo.")
    input("Press Enter after reviewing/editing those files.")


def terraform_init_validate(module_path: str) -> None:
    run_command(["terraform", "-chdir=" + module_path, "init"])
    run_command(["terraform", "-chdir=" + module_path, "validate"])


def terraform_apply(module_path: str, auto_approve: bool) -> None:
    argv = ["terraform", "-chdir=" + module_path, "apply"]
    if auto_approve:
        argv.append("-auto-approve")
    run_command(argv)


def import_existing_ecr_repos() -> None:
    print_header("Importing Existing ECR Repositories")
    repo_prefix, repositories = parse_ecr_tfvars()
    for repository in repositories:
        address = f'aws_ecr_repository.this["{repository}"]'
        import_id = f"{repo_prefix}/{repository}"
        result = run_command(
            ["terraform", "-chdir=terraform/aws-ecr", "import", address, import_id],
            check=False,
        )
        if result.returncode == 0:
            continue
        print(f"Import failed for {import_id}. It may already be imported or may not exist.")
        if not prompt_yes_no("Continue importing/applying the remaining repositories?", True):
            raise SystemExit(result.returncode)


def run_terraform(ecr_mode: str, auto_approve: bool) -> None:
    print_header("Terraform: ECR")
    terraform_init_validate("terraform/aws-ecr")
    if ecr_mode == "existing":
        import_existing_ecr_repos()
    terraform_apply("terraform/aws-ecr", auto_approve)

    for label, module_path in TERRAFORM_MODULES[1:]:
        print_header(f"Terraform: {label}")
        terraform_init_validate(module_path)
        terraform_apply(module_path, auto_approve)


def get_ec2_instance_id() -> str:
    return command_output(["terraform", "-chdir=terraform/aws-ec2-k3s", "output", "-raw", "instance_id"])


def show_ec2_instance_status(profile: str, region: str, instance_id: str) -> bool:
    print_header("EC2 Instance Status")
    output = command_output(
        [
            "aws",
            "ec2",
            "describe-instance-status",
            "--profile",
            profile,
            "--region",
            region,
            "--instance-ids",
            instance_id,
            "--include-all-instances",
            "--query",
            "InstanceStatuses[0].[InstanceState.Name,SystemStatus.Status,InstanceStatus.Status]",
            "--output",
            "text",
        ]
    )
    parts = output.split()
    state = parts[0] if len(parts) > 0 else "unknown"
    system_status = parts[1] if len(parts) > 1 else "unknown"
    instance_status = parts[2] if len(parts) > 2 else "unknown"
    ready = state == "running" and system_status == "ok" and instance_status == "ok"

    print(f"Region: {region}")
    print(f"Instance ID: {instance_id}")
    print(f"EC2 status: {'READY' if ready else 'NOT READY'}")
    print(f"State: {state}")
    print(f"System status: {system_status}")
    print(f"Instance status: {instance_status}")
    return ready


def prompt_ec2_status(profile: str, region: str) -> None:
    instance_id = get_ec2_instance_id()
    if not instance_id:
        print("Could not read EC2 instance_id from terraform/aws-ec2-k3s outputs.")
        return

    while True:
        show_ec2_instance_status(profile, region, instance_id)
        choice = prompt_text("Continue, recheck, or quit", "continue").strip().lower()
        if choice in {"", "c", "continue"}:
            return
        if choice in {"r", "recheck", "refresh", "retry", "status"}:
            continue
        if choice in {"q", "quit", "exit", "stop"}:
            raise SystemExit("Stopped after EC2 status check.")
        print("Enter continue, recheck, or quit.")


def choose_ecr_mode() -> str:
    print_header("ECR Mode")
    print("1. Create/manage ECR repositories with Terraform")
    print("2. Import existing ECR repositories, then apply")
    while True:
        value = prompt_text("Choose ECR mode", "1")
        if value == "1":
            return "new"
        if value == "2":
            return "existing"
        print("Choose 1 or 2.")


def run_ansible_playbook(
    playbook: str,
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = run_command(
        ["ansible-playbook", f"ansible/playbooks/{playbook}"],
        check=False if capture else check,
        capture=capture,
    )
    if capture:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if check and result.returncode != 0:
            raise SystemExit(result.returncode)
    return result


def run_image_publishing() -> None:
    print_header("Ansible: ECR Image Publishing")
    if not prompt_yes_no(
        "Run ECR image publishing now? This can take a while and requires local Docker image archives",
        True,
    ):
        print("Skipping image publishing. Deployments assume required images already exist in the registry.")
        return

    run_ansible_playbook("publish_images.yml")
    run_ansible_playbook("publish_chatbot_images.yml")


def wait_for_fortiaigate_ready(delay_seconds: int, max_attempts: int) -> None:
    print_header("Ansible: FortiAIGate Status")
    attempts = max(1, max_attempts)
    delay = max(1, delay_seconds)

    for attempt in range(1, attempts + 1):
        print(f"Checking FortiAIGate readiness, attempt {attempt}/{attempts}.")
        result = run_ansible_playbook("status_fortiaigate.yml", check=False, capture=True)
        output = (result.stdout or "") + "\n" + (result.stderr or "")

        if "FortiAIGate status: READY" in output:
            print("FortiAIGate is READY.")
            return

        if attempt == attempts:
            print("FortiAIGate is still NOT READY after the configured wait attempts.")
            if prompt_yes_no("Continue with the remaining demo deployments anyway?", False):
                return
            raise SystemExit("Stopped because FortiAIGate did not become ready.")

        print(
            "FortiAIGate is not ready yet. Kubernetes may still be pulling images, "
            "starting Triton, or waiting for probes. Waiting "
            f"{delay} seconds before checking again."
        )
        time.sleep(delay)


def deploy_with_status(label: str, deploy_playbook: str, status_playbook: str) -> None:
    print_header(f"Ansible: Deploy {label}")
    run_ansible_playbook(deploy_playbook)
    print_header(f"Ansible: Status {label}")
    run_ansible_playbook(status_playbook, check=False)


def run_application_deployments() -> None:
    for label, deploy_playbook, status_playbook in APPLICATION_PLAYBOOKS:
        deploy_with_status(label, deploy_playbook, status_playbook)

    print_header("Ansible: Optional HTTPS Gateway")
    if prompt_yes_no(
        "Run optional HTTPS gateway playbook now? Requires demo_https_gateway_enabled and Terraform-opened HTTPS ports",
        False,
    ):
        run_ansible_playbook("deploy_demo_https_gateway.yml")

    print_header("Ansible: Demo Outputs")
    run_ansible_playbook("show_demo_outputs.yml", check=False)


def run_ansible_flow(args: argparse.Namespace) -> None:
    print_header("Ansible Deployment")
    if not prompt_yes_no("Ready to start Ansible image publishing and deployment?", False):
        raise SystemExit("Stopped before Ansible execution.")

    run_image_publishing()

    print_header("Ansible: Bootstrap k3s")
    run_ansible_playbook("bootstrap_gpu_k3s.yml")

    print_header("Ansible: Deploy FortiAIGate")
    run_ansible_playbook("deploy_fortiaigate.yml")
    wait_for_fortiaigate_ready(args.faig_status_delay, args.faig_status_retries)

    run_application_deployments()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guided Terraform bootstrap for the FortiAIGate demo.")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Pass -auto-approve to Terraform apply. Default is interactive Terraform approval.",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(REPO_ROOT.parent / "backup"),
        help="Directory for tar.gz backups of existing private tfvars/YAML config files. Default: repo_root/../backup.",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Do not create a backup archive before copying or editing local config files.",
    )
    parser.add_argument(
        "--skip-terraform",
        action="store_true",
        help="Skip Terraform execution and continue from existing local Terraform outputs.",
    )
    parser.add_argument(
        "--skip-ansible",
        action="store_true",
        help="Stop after Terraform and EC2 status instead of running Ansible deployment.",
    )
    parser.add_argument(
        "--faig-status-delay",
        type=int,
        default=60,
        help="Seconds to wait between FortiAIGate status checks. Default: 60.",
    )
    parser.add_argument(
        "--faig-status-retries",
        type=int,
        default=30,
        help="Maximum FortiAIGate status checks before prompting to continue or stop. Default: 30.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(REPO_ROOT)
    check_repo_root()

    print("FortiAIGate automated quick start")
    print(f"Repo root: {REPO_ROOT}")
    print("This script can run Terraform, publish images, bootstrap k3s, and deploy the demo.")
    print("Existing local tfvars/YAML values are used as prompt defaults when present.")

    check_requirements()
    if args.skip_backup:
        print_header("Backing Up Local Config")
        print("Skipped by --skip-backup.")
    else:
        backup_private_config(Path(args.backup_dir).expanduser())
    copy_missing_examples()

    current_common = read_file(REPO_ROOT / "terraform/common.tfvars")
    default_profile = get_tf_string(current_common, "aws_profile")
    profile = choose_aws_profile(default_profile)
    ensure_aws_login(profile)
    profile, region, _name_prefix, _cidrs = configure_common_tfvars(profile)
    configure_ansible_env(profile, region)
    configure_ec2_tfvars(profile, region)

    prompt_manual_review()
    if args.skip_terraform:
        print_header("Terraform")
        print("Skipped by --skip-terraform.")
    else:
        if not prompt_yes_no("Ready to start Terraform execution?", False):
            raise SystemExit("Stopped before Terraform execution.")

        ecr_mode = choose_ecr_mode()
        run_terraform(ecr_mode, args.auto_approve)
    prompt_ec2_status(profile, region)

    print_header("Terraform Phase Complete")
    print("Generated files should now include:")
    print("- ansible/group_vars/ecr.generated.yml")
    print("- ansible/group_vars/ports.generated.yml")
    print("- ansible/inventory/aws.generated.ini")

    if args.skip_ansible:
        print("\nStopped before Ansible because --skip-ansible was set.")
        return

    run_ansible_flow(args)

    print_header("Automated Quick Start Complete")
    print("Terraform and Ansible deployment steps completed.")


if __name__ == "__main__":
    main()
