#!/usr/bin/env python3
"""Guided local configuration reset/review for the FortiAIGate demo."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import ipaddress
import os
import re
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PAIRS = [
    ("terraform/common.tfvars.example", "terraform/common.tfvars"),
    ("terraform/aws-ecr/terraform.tfvars.example", "terraform/aws-ecr/terraform.tfvars"),
    ("terraform/aws-prep/terraform.tfvars.example", "terraform/aws-prep/terraform.tfvars"),
    ("terraform/aws-ec2-k3s/terraform.tfvars.example", "terraform/aws-ec2-k3s/terraform.tfvars"),
    ("terraform/aws-fortigate/terraform.tfvars.example", "terraform/aws-fortigate/terraform.tfvars"),
    ("terraform/aws-fortiweb/terraform.tfvars.example", "terraform/aws-fortiweb/terraform.tfvars"),
    ("ansible/group_vars/env.example.yml", "ansible/group_vars/env.yml"),
    ("ansible/group_vars/all.example.yml", "ansible/group_vars/all.yml"),
    ("ansible/group_vars/images.example.yml", "ansible/group_vars/images.yml"),
]

SKIP_SSH_PRIVATE_KEY_NAMES = {
    "authorized_keys",
    "config",
    "environment",
    "known_hosts",
    "known_hosts.old",
}

SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "password",
    "secret",
    "token",
    "access_key",
    "private_key",
)


@dataclass(frozen=True)
class ConfigPair:
    example: Path
    local: Path


@dataclass(frozen=True)
class VarBlock:
    key: str
    start: int
    end: int
    lines: list[str]


@dataclass(frozen=True)
class ConfigItem:
    path: str
    key: str
    label: str
    kind: str = "string"
    section: str = ""
    sensitive: bool = False
    validate_cidr: bool = False


IMPORTANT_ITEMS = [
    ConfigItem("terraform/common.tfvars", "aws_profile", "AWS profile", section="Shared Terraform"),
    ConfigItem("terraform/common.tfvars", "aws_region", "AWS region", section="Shared Terraform"),
    ConfigItem("terraform/common.tfvars", "name_prefix", "Deployment name prefix", section="Shared Terraform"),
    ConfigItem("terraform/common.tfvars", "ssh_key_name", "AWS EC2 key pair name", section="Shared Terraform"),
    ConfigItem("terraform/common.tfvars", "allowed_ingress_cidr", "Trusted source CIDRs", "list", "Shared Terraform", validate_cidr=True),
    ConfigItem("terraform/common.tfvars", "tags", "Terraform tags", "map", "Shared Terraform"),
    ConfigItem("terraform/aws-ecr/terraform.tfvars", "repo_prefix", "ECR repository prefix", section="ECR"),
    ConfigItem("terraform/aws-ecr/terraform.tfvars", "image_tag_mutability", "Default ECR image tag mutability", section="ECR"),
    ConfigItem("terraform/aws-ecr/terraform.tfvars", "scan_on_push", "Enable ECR scan on push", "bool", "ECR"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "enable_bedrock_iam", "Create Bedrock IAM user/access key", "bool", "AWS prep / Bedrock"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "enable_ec2_bedrock_iam", "Attach Bedrock IAM to EC2 role", "bool", "AWS prep / Bedrock"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "bedrock_model_ids", "Bedrock model IDs", "list", "AWS prep / Bedrock"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "bedrock_allowed_regions", "Bedrock allowed regions", "list", "AWS prep / Bedrock"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "bedrock_no_ip_restriction", "Disable Bedrock source-IP restriction", "bool", "AWS prep / Bedrock"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "bedrock_allowed_source_cidrs", "Bedrock allowed source CIDRs", "list", "AWS prep / Bedrock", validate_cidr=True),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "allocate_eips", "Prep EIP allocation map", "map_bool", "AWS prep / Appliances"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "fortiweb_enabled", "Create FortiWeb cloud-init IAM/S3 prep", "bool", "AWS prep / Appliances"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "fortiweb_cloudinit_bucket_name", "FortiWeb cloud-init bucket name", section="AWS prep / Appliances"),
    ConfigItem("terraform/aws-prep/terraform.tfvars", "fortiweb_cloudinit_bucket_force_destroy", "Allow FortiWeb cloud-init bucket force destroy", "bool", "AWS prep / Appliances"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "ssh_private_key_file", "Local SSH private key path", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "ec2_pull_github_keys", "GitHub users to add to authorized_keys", "list", "EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "instance_type", "k3s EC2 instance type", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "availability_zone", "Availability zone override", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "vpc_cidr", "VPC CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "public_subnet_cidr", "k3s public subnet CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "k3s_private_subnet_cidr", "k3s private subnet CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "fortigate_public_subnet_cidr", "FortiGate public subnet CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "fortiweb_public_subnet_cidr", "FortiWeb public subnet CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "fortigate_internal_subnet_cidr", "FortiGate internal subnet CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "fortiweb_internal_subnet_cidr", "FortiWeb internal subnet CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "k3s_cluster_cidr", "k3s pod CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "k3s_service_cidr", "k3s service CIDR", section="EC2 k3s", validate_cidr=True),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "k3s_cluster_dns", "k3s cluster DNS IP", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "k3s_subnet_mode", "k3s subnet mode", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "demo_http_base_port", "Demo HTTP NodePort base", "number", "EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "demo_https_base_port", "Demo HTTPS NodePort base", "number", "EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "additional_ingress_tcp_ports", "Additional public TCP ports", "list_number", "EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "ingress_routing_strategy", "Ingress routing strategy (current demo is port_based)", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "ingress_base_domain", "Ingress base domain", section="EC2 k3s"),
    ConfigItem("terraform/aws-ec2-k3s/terraform.tfvars", "magic_dns_zone", "Magic DNS zone", section="EC2 k3s"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_enabled", "Deploy FortiGate", "bool", "FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_instance_type", "FortiGate instance type", section="FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_version", "FortiGate version filter", section="FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_license_type", "FortiGate Marketplace license type", section="FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_license_mode", "FortiGate license mode", section="FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_license_source_dir", "FortiGate license source directory", section="FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_license_file_name", "FortiGate license file", section="FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_admin_port", "FortiGate admin HTTPS port", "number", "FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_enable_ssh", "Enable FortiGate SSH", "bool", "FortiGate"),
    ConfigItem("terraform/aws-fortigate/terraform.tfvars", "fortigate_enable_api", "Enable FortiGate API admin", "bool", "FortiGate"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_enabled", "Deploy FortiWeb", "bool", "FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_instance_type", "FortiWeb instance type", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_version", "FortiWeb version filter", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_license_type", "FortiWeb Marketplace license type", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_license_mode", "FortiWeb license mode", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_license_source_dir", "FortiWeb license source directory", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_license_file_name", "FortiWeb license file", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_config_file", "FortiWeb custom config file", section="FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_admin_https_port", "FortiWeb HTTPS admin port", "number", "FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_admin_http_port", "FortiWeb HTTP admin port", "number", "FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_set_initial_password", "Set FortiWeb initial password in user-data", "bool", "FortiWeb"),
    ConfigItem("terraform/aws-fortiweb/terraform.tfvars", "fortiweb_admin_password", "FortiWeb initial admin password", section="FortiWeb", sensitive=True),
    ConfigItem("ansible/group_vars/all.yml", "fortiaigate_version", "FortiAIGate version", section="FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "fortiaigate_image_tag", "FortiAIGate image tag", section="FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "fortiaigate_triton_model_image_tag", "FortiAIGate Triton model image tag", section="FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "fortiaigate_triton_image_tag", "FortiAIGate Triton image tag", section="FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "image_archive_dir", "FortiAIGate image archive directory", section="FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "license_source_dir", "FortiAIGate license source directory", section="FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "fortiaigate_license_files", "FortiAIGate license files", "list", "FortiAIGate"),
    ConfigItem("ansible/group_vars/all.yml", "direct_model_provider", "Direct model provider", section="Model paths"),
    ConfigItem("ansible/group_vars/all.yml", "direct_model_bedrock_model", "Direct Bedrock model override", section="Model paths"),
    ConfigItem("ansible/group_vars/all.yml", "direct_model_bedrock_region", "Direct Bedrock region override", section="Model paths"),
    ConfigItem("ansible/group_vars/all.yml", "litellm_master_key", "LiteLLM API/master key", section="LiteLLM", sensitive=True),
    ConfigItem("ansible/group_vars/all.yml", "litellm_ui_username", "LiteLLM admin username", section="LiteLLM"),
    ConfigItem("ansible/group_vars/all.yml", "litellm_ui_password", "LiteLLM admin password", section="LiteLLM", sensitive=True),
    ConfigItem("ansible/group_vars/all.yml", "openwebui_enabled", "Deploy Open WebUI", "bool", "Applications"),
    ConfigItem("ansible/group_vars/all.yml", "chatbot_image_tag", "Chatbot image tag", section="Applications"),
    ConfigItem("ansible/group_vars/images.yml", "publish_auto_image_map", "Auto-map loaded image tags", "bool", "Image publishing"),
    ConfigItem("ansible/group_vars/images.yml", "publish_image_version", "Publish image version selector", section="Image publishing"),
    ConfigItem("ansible/group_vars/images.yml", "publish_image_state", "Publish image state selector", section="Image publishing"),
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def print_header(message: str) -> None:
    print(f"\n== {message} ==")


def run_command(argv: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        print("")
        return default
    return value if value else default


def prompt_secret(prompt: str, current_set: bool) -> str | None:
    suffix = " [keep current]" if current_set else ""
    try:
        value = getpass.getpass(f"{prompt}{suffix}: ")
    except EOFError:
        if current_set:
            print("")
            return None
        return ""
    if not value and current_set:
        return None
    return value


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        try:
            value = input(f"{prompt}{suffix}: ").strip().lower()
        except EOFError:
            print("")
            return default
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Answer yes or no.")


def prompt_choice(prompt: str, choices: dict[str, str], default: str) -> str:
    while True:
        value = prompt_text(prompt, default).strip().lower()
        if value in choices:
            return value
        matches = [key for key, label in choices.items() if value == label.lower()]
        if matches:
            return matches[0]
        print("Choices:")
        for key, label in choices.items():
            print(f"- {key}: {label}")


def detect_format(path: Path) -> str:
    if path.name.endswith((".tfvars", ".tfvars.example")):
        return "hcl"
    if path.name.endswith((".yml", ".yaml", ".yml.example", ".yaml.example")):
        return "yaml"
    raise SystemExit(f"Unsupported config file type: {path}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"would update: {rel(path)}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"updated: {rel(path)}")


def copy_missing_examples(*, dry_run: bool) -> None:
    print_header("Preparing Local Config Files")
    for example_rel, local_rel in CONFIG_PAIRS:
        example = REPO_ROOT / example_rel
        local = REPO_ROOT / local_rel
        if local.exists():
            print(f"exists: {local_rel}")
            continue
        if dry_run:
            print(f"would create: {local_rel} from {example_rel}")
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, local)
        print(f"created: {local_rel} from {example_rel}")


def collect_private_config_files() -> list[Path]:
    files: list[Path] = []
    terraform_root = REPO_ROOT / "terraform"
    ansible_group_vars = REPO_ROOT / "ansible/group_vars"
    files.extend(path for path in terraform_root.rglob("*.tfvars") if path.is_file())
    files.extend(
        path
        for path in ansible_group_vars.glob("*.yml")
        if path.is_file()
        and not path.name.endswith(".example.yml")
        and not path.name.endswith(".generated.yml")
    )
    return sorted(set(files))


def backup_private_config(backup_dir: Path, *, dry_run: bool) -> None:
    print_header("Backing Up Local Config")
    files = collect_private_config_files()
    if not files:
        print("No local tfvars/YAML files found.")
        return
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = backup_dir / f"fortiaigate-demo-reconfigure-{timestamp}.tar.gz"
    if dry_run:
        print(f"would create: {archive_path}")
    else:
        backup_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in files:
                archive.add(path, arcname=path.relative_to(REPO_ROOT), recursive=False)
        print(f"created: {archive_path}")
    print("included:")
    for path in files:
        print(f"- {rel(path)}")


def top_level_key_indexes(lines: list[str], file_format: str) -> list[tuple[int, str]]:
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=" if file_format == "hcl" else r"^([A-Za-z_][A-Za-z0-9_]*)\s*:")
    indexes: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            indexes.append((index, match.group(1)))
    return indexes


def parse_var_blocks(content: str, file_format: str) -> dict[str, VarBlock]:
    lines = content.splitlines(keepends=True)
    indexes = top_level_key_indexes(lines, file_format)
    blocks: dict[str, VarBlock] = {}
    for position, (start, key) in enumerate(indexes):
        end = indexes[position + 1][0] if position + 1 < len(indexes) else len(lines)
        blocks[key] = VarBlock(key=key, start=start, end=end, lines=lines[start:end])
    return blocks


def block_text(block: VarBlock | None) -> str:
    return "".join(block.lines).strip() if block else ""


def block_value_text(block: VarBlock | None, file_format: str) -> str:
    if block is None:
        return ""
    text = block_text(block)
    first_line = text.splitlines()[0] if text else ""
    separator = "=" if file_format == "hcl" else ":"
    if separator not in first_line:
        return ""
    return first_line.split(separator, 1)[1].strip()


def normalize_block_for_compare(block: VarBlock | None) -> str:
    return "\n".join(line.rstrip() for line in (block.lines if block else [])).strip()


def get_hcl_string(content: str, key: str, default: str = "") -> str:
    match = re.search(rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"([^"]*)"', content)
    return match.group(1) if match else default


def get_hcl_bool(content: str, key: str, default: bool = False) -> bool:
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(true|false)\b", content)
    return (match.group(1) == "true") if match else default


def get_hcl_number(content: str, key: str, default: str = "") -> str:
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*([0-9]+)\b", content)
    return match.group(1) if match else default


def get_hcl_list(content: str, key: str) -> list[str]:
    match = re.search(rf"(?ms)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\[(.*?)\]", content)
    if not match:
        single = get_hcl_string(content, key)
        return [single] if single else []
    body = match.group(1)
    quoted = re.findall(r'"([^"]*)"', body)
    if quoted:
        return quoted
    return [entry.strip().strip(",") for entry in body.splitlines() if entry.strip().strip(",")]


def get_hcl_map(content: str, key: str) -> dict[str, str]:
    match = re.search(rf"(?ms)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\{{(.*?)^\s*\}}", content)
    if not match:
        return {}
    values: dict[str, str] = {}
    for pair_match in re.finditer(r'(?m)^[ \t]*"?([^"\s=]+)"?[ \t]*=[ \t]*"?([^"\n]+?)"?[ \t]*(?:#.*)?$', match.group(1)):
        values[pair_match.group(1)] = pair_match.group(2).strip()
    return values


def get_hcl_object_bool(content: str, key: str) -> dict[str, bool]:
    return {name: value.lower() == "true" for name, value in get_hcl_map(content, key).items() if value.lower() in {"true", "false"}}


def get_yaml_scalar(content: str, key: str, default: str = "") -> str:
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}:[ \t]*(.*)$", content)
    if not match:
        return default
    return match.group(1).strip().strip('"').strip("'")


def get_yaml_bool(content: str, key: str, default: bool = False) -> bool:
    value = get_yaml_scalar(content, key, str(default).lower()).lower()
    return value in {"true", "yes", "on", "1"}


def yaml_block_span(content: str, key: str) -> tuple[int, int] | None:
    lines = content.splitlines(keepends=True)
    offset = 0
    start = None
    start_index = None
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:\s*", line):
            start = offset
            start_index = index
            break
        offset += len(line)
    if start is None or start_index is None:
        return None
    end = start + len(lines[start_index])
    for next_line in lines[start_index + 1 :]:
        if next_line.strip() and not next_line.startswith((" ", "\t", "#")):
            break
        end += len(next_line)
    return start, end


def get_yaml_list(content: str, key: str) -> list[str]:
    span = yaml_block_span(content, key)
    if span is None:
        scalar = get_yaml_scalar(content, key)
        return [scalar] if scalar else []
    block = content[span[0] : span[1]]
    values: list[str] = []
    for line in block.splitlines()[1:]:
        match = re.match(r"\s*-\s*(.*?)\s*$", line)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            if value:
                values.append(value)
    return values


def set_hcl_string(content: str, key: str, value: str) -> str:
    replacement = f'{key} = "{value}"'
    pattern = rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"[^"]*"'
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_hcl_bool(content: str, key: str, value: bool) -> str:
    replacement = f"{key} = {str(value).lower()}"
    pattern = rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(true|false)\b"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_hcl_number(content: str, key: str, value: str) -> str:
    replacement = f"{key} = {value}"
    pattern = rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*[0-9]+\b"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_hcl_list(content: str, key: str, values: list[str], *, quote: bool = True) -> str:
    if quote:
        rendered = "\n".join(f'  "{value}",' for value in values)
    else:
        rendered = "\n".join(f"  {value}," for value in values)
    replacement = f"{key} = [\n{rendered}\n]"
    pattern = rf"(?ms)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\[.*?\]"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    string_pattern = rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"[^"]*"'
    if re.search(string_pattern, content):
        return re.sub(string_pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_hcl_map(content: str, key: str, values: dict[str, str], *, bool_values: bool = False) -> str:
    if values:
        if bool_values:
            rendered = "\n".join(f"  {map_key} = {str(map_value).lower()}" for map_key, map_value in sorted(values.items()))
        else:
            rendered = "\n".join(f'  {map_key} = "{map_value}"' for map_key, map_value in sorted(values.items()))
        replacement = f"{key} = {{\n{rendered}\n}}"
    else:
        replacement = f"{key} = {{}}"
    pattern = rf"(?ms)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\{{.*?^\s*\}}"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_yaml_scalar(content: str, key: str, value: str) -> str:
    replacement = f"{key}: {value}"
    pattern = rf"(?m)^[ \t]*{re.escape(key)}:[ \t]*.*$"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_yaml_list(content: str, key: str, values: list[str]) -> str:
    rendered = "\n".join(f"  - {value}" for value in values)
    replacement = f"{key}:\n{rendered}\n"
    span = yaml_block_span(content, key)
    if span is None:
        return content.rstrip() + f"\n{replacement}"
    return content[: span[0]] + replacement + content[span[1] :]


def replace_block(content: str, blocks: dict[str, VarBlock], key: str, replacement: str) -> str:
    block = blocks.get(key)
    if block is None:
        return content.rstrip() + "\n" + replacement.rstrip() + "\n"
    return content[: sum(len(line) for line in content.splitlines(keepends=True)[: block.start])] + replacement.rstrip() + "\n" + content[
        sum(len(line) for line in content.splitlines(keepends=True)[: block.end]) :
    ]


def normalize_cidr(value: str) -> str:
    if "/" not in value:
        address = ipaddress.ip_address(value)
        return f"{address}/{32 if address.version == 4 else 128}"
    return str(ipaddress.ip_network(value, strict=False))


def validate_cidrs(values: list[str], label: str) -> list[str]:
    normalized: list[str] = []
    for value in values:
        try:
            normalized.append(normalize_cidr(value))
        except ValueError as error:
            raise SystemExit(f"{label} contains an invalid CIDR/IP value: {value}. {error}") from error
    return normalized


def parse_csv(value: str) -> list[str]:
    return [entry.strip() for entry in value.split(",") if entry.strip()]


def parse_map_text(value: str) -> dict[str, str]:
    if not value.strip():
        return {}
    result: dict[str, str] = {}
    for entry in value.split(","):
        if not entry.strip():
            continue
        if "=" not in entry:
            raise SystemExit(f"Invalid map entry '{entry}'. Use key=value.")
        key, map_value = entry.split("=", 1)
        result[key.strip()] = map_value.strip()
    return result


def render_map_text(values: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(values.items()))


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in {"ssh_key_name"} or lowered.endswith("_key_length"):
        return False
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def masked(value: str, *, sensitive: bool) -> str:
    if not sensitive:
        return value if len(value) <= 140 else value[:137] + "..."
    return "<set>" if value else "<empty>"


def list_aws_profiles() -> list[str]:
    result = run_command(["aws", "configure", "list-profiles"])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def choose_aws_profile(default: str) -> str:
    profiles = list_aws_profiles()
    if profiles:
        print("Available AWS profiles:")
        for index, profile in enumerate(profiles, start=1):
            marker = " (current)" if profile == default else ""
            print(f"{index}. {profile}{marker}")
    while True:
        selected = prompt_text("AWS profile name or number", default or (profiles[0] if profiles else ""))
        if selected.isdigit() and profiles:
            index = int(selected)
            if 1 <= index <= len(profiles):
                return profiles[index - 1]
        if selected:
            return selected
        print("Enter an AWS profile.")


def list_ec2_key_pairs(profile: str, region: str) -> list[str]:
    result = run_command(
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
        ]
    )
    if result.returncode != 0:
        return []
    return [key.strip() for key in re.split(r"\s+", result.stdout) if key.strip()]


def choose_ec2_key_pair(profile: str, region: str, default: str) -> str:
    keys = list_ec2_key_pairs(profile, region)
    if keys:
        print("Available EC2 key pairs:")
        for index, key_name in enumerate(keys, start=1):
            marker = " (current)" if key_name == default else ""
            print(f"{index}. {key_name}{marker}")
    while True:
        selected = prompt_text("EC2 key pair name or number", default or (keys[0] if keys else ""))
        if selected.isdigit() and keys:
            index = int(selected)
            if 1 <= index <= len(keys):
                return keys[index - 1]
        if selected:
            return selected
        print("Enter an EC2 key pair name.")


def display_path(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)


def list_local_ssh_private_keys() -> list[Path]:
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return []
    return sorted(
        path
        for path in ssh_dir.iterdir()
        if path.is_file()
        and path.name not in SKIP_SSH_PRIVATE_KEY_NAMES
        and not path.name.endswith(".pub")
        and not path.name.startswith("known_hosts")
    )


def choose_private_key(default: str, key_name: str) -> str:
    candidates = list_local_ssh_private_keys()
    displays = [display_path(path) for path in candidates]
    fallback = default or f"~/.ssh/{key_name}"
    if candidates:
        print("Likely private keys in ~/.ssh:")
        for index, path_text in enumerate(displays, start=1):
            marker = " (current)" if path_text == default else ""
            print(f"{index}. {path_text}{marker}")
        print("m. Enter a path manually")
    selected = prompt_text("Local SSH private key number, path, or m", fallback)
    if selected.lower() == "m":
        return prompt_text("Local SSH private key path", fallback)
    if selected.isdigit() and candidates:
        index = int(selected)
        if 1 <= index <= len(candidates):
            return displays[index - 1]
    return selected


def resolve_module_path(value: str, module_path: Path) -> Path:
    path = Path(value.strip().strip('"').strip("'")).expanduser()
    if not path.is_absolute():
        path = module_path / path
    return path


def render_license_source_dir(path: Path, module_path: Path) -> str:
    license_dir = (REPO_ROOT.parent / "licenses").resolve()
    resolved = path.expanduser().resolve()
    try:
        if resolved == license_dir:
            return "../../../licenses"
    except FileNotFoundError:
        pass
    try:
        return str(resolved.relative_to(module_path))
    except ValueError:
        return os.path.relpath(resolved, module_path)


def list_license_candidates(source_dir: Path) -> list[Path]:
    if not source_dir.exists() or not source_dir.is_dir():
        return []
    preferred = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in {".lic", ".license"})
    if preferred:
        return preferred
    return sorted(path for path in source_dir.iterdir() if path.is_file())


def choose_license_file_name(label: str, source_dir: Path, default_file: str) -> str:
    candidates = list_license_candidates(source_dir)
    if candidates:
        print(f"Available {label} license files in {source_dir}:")
        for index, path in enumerate(candidates, start=1):
            marker = " (current)" if path.name == default_file else ""
            print(f"{index}. {path.name}{marker}")
        print("m. Enter a file name manually")
    else:
        print(f"No license files were found in {source_dir}.")

    while True:
        selected = prompt_text(f"{label} license file name, number, or m", default_file or (candidates[0].name if candidates else ""))
        if selected.lower() == "m":
            manual = prompt_text(f"{label} license file name")
            if manual:
                return Path(manual).name
        if selected.isdigit() and candidates:
            index = int(selected)
            if 1 <= index <= len(candidates):
                return candidates[index - 1].name
        if selected:
            return Path(selected).name
        print("Enter a license file name.")


def appliance_prefix_from_key(key: str) -> str:
    return key.removesuffix("_license_source_dir").removesuffix("_license_file_name")


def module_path_for_config(path: str) -> Path:
    return REPO_ROOT / Path(path).parent


def legacy_license_path_from_content(content: str, prefix: str, module_path: Path) -> Path | None:
    legacy = get_hcl_string(content, f"{prefix}_license_file")
    if not legacy:
        return None
    return resolve_module_path(legacy, module_path)


def should_skip_item(item: ConfigItem) -> bool:
    if item.key == "fortiweb_admin_password":
        path = REPO_ROOT / item.path
        if path.exists() and not get_hcl_bool(read_text(path), "fortiweb_set_initial_password", False):
            print("Skipping FortiWeb initial admin password because fortiweb_set_initial_password=false.")
            return True
    return False


def current_value(content: str, key: str, kind: str, file_format: str) -> object:
    if file_format == "hcl":
        if kind == "bool":
            return get_hcl_bool(content, key)
        if kind == "number":
            return get_hcl_number(content, key)
        if kind in {"list", "list_number"}:
            return get_hcl_list(content, key)
        if kind == "map":
            return get_hcl_map(content, key)
        if kind == "map_bool":
            return get_hcl_object_bool(content, key)
        return get_hcl_string(content, key)
    if kind == "bool":
        return get_yaml_bool(content, key)
    if kind in {"list", "list_number"}:
        return get_yaml_list(content, key)
    return get_yaml_scalar(content, key)


def apply_value(content: str, key: str, kind: str, file_format: str, value: object) -> str:
    if file_format == "hcl":
        if kind == "bool":
            return set_hcl_bool(content, key, bool(value))
        if kind == "number":
            return set_hcl_number(content, key, str(value))
        if kind == "list":
            return set_hcl_list(content, key, list(value), quote=True)
        if kind == "list_number":
            return set_hcl_list(content, key, [str(item) for item in list(value)], quote=False)
        if kind == "map":
            return set_hcl_map(content, key, dict(value))
        if kind == "map_bool":
            return set_hcl_map(content, key, dict(value), bool_values=True)
        return set_hcl_string(content, key, str(value))
    if kind == "bool":
        return set_yaml_scalar(content, key, str(bool(value)).lower())
    if kind in {"list", "list_number"}:
        return set_yaml_list(content, key, [str(item) for item in list(value)])
    return set_yaml_scalar(content, key, str(value))


def prompt_for_item(item: ConfigItem, content: str, *, default_from_common: str = "") -> object | None:
    file_format = detect_format(REPO_ROOT / item.path)
    current = current_value(content, item.key, item.kind, file_format)
    module_path = module_path_for_config(item.path)
    if item.key.endswith("_license_source_dir"):
        prefix = appliance_prefix_from_key(item.key)
        legacy_path = legacy_license_path_from_content(content, prefix, module_path)
        default_dir = render_license_source_dir(legacy_path.parent, module_path) if legacy_path else str(current)
        selected = prompt_text(item.label, default_dir)
        source_dir = resolve_module_path(selected, module_path)
        candidates = list_license_candidates(source_dir)
        print(f"{item.label}: {source_dir}")
        if candidates:
            print("License files found:")
            for path in candidates:
                print(f"- {path.name}")
        else:
            print("No license files found in this directory.")
        return selected
    if item.key.endswith("_license_file_name"):
        prefix = appliance_prefix_from_key(item.key)
        source_dir_value = get_hcl_string(content, f"{prefix}_license_source_dir", "../../../licenses")
        legacy_path = legacy_license_path_from_content(content, prefix, module_path)
        source_dir = legacy_path.parent if legacy_path else resolve_module_path(source_dir_value, module_path)
        default_file = legacy_path.name if legacy_path else str(current)
        label = "FortiGate" if prefix == "fortigate" else "FortiWeb"
        return choose_license_file_name(label, source_dir, default_file)
    if item.key == "aws_profile":
        return choose_aws_profile(str(current))
    if item.key == "ssh_key_name":
        common = read_text(REPO_ROOT / "terraform/common.tfvars")
        profile = get_hcl_string(common, "aws_profile")
        region = get_hcl_string(common, "aws_region", "us-east-1")
        return choose_ec2_key_pair(profile, region, str(current))
    if item.key == "ssh_private_key_file":
        return choose_private_key(str(current), default_from_common)

    if item.kind == "bool":
        return prompt_yes_no(item.label, bool(current))
    if item.kind in {"list", "list_number"}:
        current_list = [str(value) for value in list(current)]
        value = prompt_text(item.label + " (comma-separated)", ", ".join(current_list))
        values = parse_csv(value)
        if item.validate_cidr and values:
            values = validate_cidrs(values, item.label)
        return values
    if item.kind == "map":
        value = prompt_text(item.label + " (comma-separated key=value)", render_map_text(dict(current)))
        return parse_map_text(value)
    if item.kind == "map_bool":
        current_map = {key: str(value).lower() for key, value in dict(current).items()}
        value = prompt_text(item.label + " (comma-separated key=true/false)", render_map_text(current_map))
        parsed = parse_map_text(value)
        return {key: map_value.lower() in {"true", "yes", "1", "on"} for key, map_value in parsed.items()}
    if item.sensitive:
        new_secret = prompt_secret(item.label, bool(str(current)))
        return new_secret
    value = prompt_text(item.label, str(current))
    if item.validate_cidr and value:
        return normalize_cidr(value)
    return value


def configure_important_items(*, dry_run: bool) -> set[tuple[str, str]]:
    print_header("Guided Important Configuration")
    handled: set[tuple[str, str]] = set()
    current_section = ""
    common_ssh_key = ""

    for item in IMPORTANT_ITEMS:
        path = REPO_ROOT / item.path
        if not path.exists():
            print(f"skip missing file: {item.path}")
            continue
        if should_skip_item(item):
            handled.add((item.path, item.key))
            continue
        if item.section != current_section:
            current_section = item.section
            print_header(current_section or rel(path))
        content = read_text(path)
        if item.path == "terraform/aws-ec2-k3s/terraform.tfvars":
            common_ssh_key = get_hcl_string(read_text(REPO_ROOT / "terraform/common.tfvars"), "ssh_key_name")
        file_format = detect_format(path)
        original_value = current_value(content, item.key, item.kind, file_format)
        value = prompt_for_item(item, content, default_from_common=common_ssh_key)
        if value is None:
            handled.add((item.path, item.key))
            continue
        if value == original_value:
            handled.add((item.path, item.key))
            continue
        updated = apply_value(content, item.key, item.kind, file_format, value)
        if item.key.endswith("_license_file_name"):
            prefix = appliance_prefix_from_key(item.key)
            updated = set_hcl_string(updated, f"{prefix}_license_file", "")
        if updated != content:
            write_text(path, updated, dry_run=dry_run)
        handled.add((item.path, item.key))

    sync_ansible_env_with_common(dry_run=dry_run)
    sync_appliance_prep_from_enabled(dry_run=dry_run)
    return handled


def sync_ansible_env_with_common(*, dry_run: bool) -> None:
    common_path = REPO_ROOT / "terraform/common.tfvars"
    env_path = REPO_ROOT / "ansible/group_vars/env.yml"
    if not common_path.exists() or not env_path.exists():
        return
    common = read_text(common_path)
    env = read_text(env_path)
    profile = get_hcl_string(common, "aws_profile")
    region = get_hcl_string(common, "aws_region")
    updated = set_yaml_scalar(env, "aws_profile", profile)
    updated = set_yaml_scalar(updated, "aws_region", region)
    if updated != env:
        print_header("Ansible Environment Sync")
        write_text(env_path, updated, dry_run=dry_run)


def sync_appliance_prep_from_enabled(*, dry_run: bool) -> None:
    prep_path = REPO_ROOT / "terraform/aws-prep/terraform.tfvars"
    fgt_path = REPO_ROOT / "terraform/aws-fortigate/terraform.tfvars"
    fwb_path = REPO_ROOT / "terraform/aws-fortiweb/terraform.tfvars"
    if not prep_path.exists():
        return
    prep = read_text(prep_path)
    updated = prep
    fgt_enabled = fgt_path.exists() and get_hcl_bool(read_text(fgt_path), "fortigate_enabled", False)
    fwb_enabled = fwb_path.exists() and get_hcl_bool(read_text(fwb_path), "fortiweb_enabled", False)
    allocate = get_hcl_object_bool(updated, "allocate_eips")
    allocate_changed = False
    if fgt_enabled and not allocate.get("fortigate", False):
        allocate["fortigate"] = True
        allocate_changed = True
    if fwb_enabled and not allocate.get("fortiweb", False):
        allocate["fortiweb"] = True
        allocate_changed = True
    if fwb_enabled and not get_hcl_bool(updated, "fortiweb_enabled", False):
        updated = set_hcl_bool(updated, "fortiweb_enabled", True)
    if allocate and allocate_changed:
        updated = set_hcl_map(updated, "allocate_eips", allocate, bool_values=True)
    if updated != prep:
        print_header("Appliance Prep Sync")
        write_text(prep_path, updated, dry_run=dry_run)


def sync_missing_defaults(*, dry_run: bool) -> None:
    print_header("Syncing Missing Defaults")
    if dry_run:
        upgrade_command = [sys.executable, "scripts/upgrade_v0_3_to_v0_4.py", "--check"]
        command = [sys.executable, "scripts/sync_all_vars.py", "--dry-run"]
    else:
        upgrade_command = [sys.executable, "scripts/upgrade_v0_3_to_v0_4.py"]
        command = [sys.executable, "scripts/sync_all_vars.py"]
    result = run_command(upgrade_command)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    result = run_command(command)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def block_is_scalar(block: VarBlock | None, file_format: str) -> bool:
    if block is None:
        return False
    text = block_text(block)
    if file_format == "hcl":
        value = block_value_text(block, file_format)
        return bool(value) and not value.startswith(("[", "{"))
    first = text.splitlines()[0] if text else ""
    value = first.split(":", 1)[1].strip() if ":" in first else ""
    return bool(value)


def blocks_semantically_equal(local_block: VarBlock | None, example_block: VarBlock | None, file_format: str) -> bool:
    if block_is_scalar(local_block, file_format) and block_is_scalar(example_block, file_format):
        local_value = block_value_text(local_block, file_format).strip().strip('"').strip("'")
        example_value = block_value_text(example_block, file_format).strip().strip('"').strip("'")
        return local_value == example_value
    return normalize_block_for_compare(local_block) == normalize_block_for_compare(example_block)


def prompt_scalar_diff(local_value: str, example_value: str, key: str, *, sensitive: bool) -> str:
    print(f"Current: {masked(local_value, sensitive=sensitive)}")
    print(f"Example: {masked(example_value, sensitive=sensitive)}")
    choices = {"k": "keep current", "r": "reset to example", "e": "enter new value"}
    choice = prompt_choice(f"{key}: keep, reset, or edit", choices, "k")
    if choice == "r":
        return example_value
    if choice == "e":
        if sensitive:
            return getpass.getpass(f"{key} new value: ")
        return prompt_text(f"{key} new value", local_value)
    return local_value


def review_remaining_diffs(handled: set[tuple[str, str]], *, dry_run: bool) -> None:
    print_header("Local Differences From Examples")
    for example_rel, local_rel in CONFIG_PAIRS:
        example = REPO_ROOT / example_rel
        local = REPO_ROOT / local_rel
        if not example.exists() or not local.exists():
            continue
        file_format = detect_format(local)
        example_content = read_text(example)
        local_content = read_text(local)
        example_blocks = parse_var_blocks(example_content, file_format)
        local_blocks = parse_var_blocks(local_content, file_format)
        keys = [key for key in local_blocks if key in example_blocks]
        changed = [
            key
            for key in keys
            if (local_rel, key) not in handled
            and not blocks_semantically_equal(local_blocks[key], example_blocks[key], file_format)
        ]
        if not changed:
            continue

        print_header(local_rel)
        updated = local_content
        for key in changed:
            local_blocks = parse_var_blocks(updated, file_format)
            local_block = local_blocks[key]
            example_block = example_blocks[key]
            sensitive = is_sensitive_key(key)
            print(f"\n{key} differs from {example_rel}.")
            if block_is_scalar(local_block, file_format) and block_is_scalar(example_block, file_format):
                local_value = block_value_text(local_block, file_format).strip().strip('"').strip("'")
                example_value = block_value_text(example_block, file_format).strip().strip('"').strip("'")
                selected = prompt_scalar_diff(local_value, example_value, key, sensitive=sensitive)
                if selected != local_value:
                    if file_format == "hcl":
                        if selected.lower() in {"true", "false"} and example_value.lower() in {"true", "false"}:
                            updated = set_hcl_bool(updated, key, selected.lower() == "true")
                        elif re.fullmatch(r"[0-9]+", selected) and re.fullmatch(r"[0-9]+", example_value):
                            updated = set_hcl_number(updated, key, selected)
                        else:
                            updated = set_hcl_string(updated, key, selected)
                    else:
                        updated = set_yaml_scalar(updated, key, selected)
                continue

            print("Current block:")
            print(masked(block_text(local_block), sensitive=sensitive))
            print("Example block:")
            print(masked(block_text(example_block), sensitive=sensitive))
            choices = {"k": "keep current", "r": "reset to example"}
            choice = prompt_choice(f"{key}: keep or reset", choices, "k")
            if choice == "r":
                updated = replace_block(updated, local_blocks, key, block_text(example_block))

        if updated != local_content:
            write_text(local, updated, dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactively reconfigure local ignored tfvars/YAML files without running Terraform or Ansible."
    )
    parser.add_argument(
        "--backup-dir",
        default=str(REPO_ROOT.parent / "backup"),
        help="Directory for backup archives. Default: repo_root/../backup.",
    )
    parser.add_argument("--skip-backup", action="store_true", help="Do not back up local config before editing.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files.")
    parser.add_argument("--skip-sync", action="store_true", help="Do not run v0.3-to-v0.4 migration or sync missing defaults.")
    parser.add_argument("--skip-diff-review", action="store_true", help="Skip the final local-vs-example difference review.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (REPO_ROOT / "ansible.cfg").exists():
        raise SystemExit("Run this script from inside the fortiaigate_demo repository.")

    print("FortiAIGate local reconfiguration")
    print(f"Repo root: {REPO_ROOT}")
    print("This updates ignored local tfvars/YAML files only. It does not run Terraform or Ansible.")

    if not args.skip_backup:
        backup_private_config(Path(args.backup_dir).expanduser(), dry_run=args.dry_run)
    copy_missing_examples(dry_run=args.dry_run)
    if not args.skip_sync:
        sync_missing_defaults(dry_run=args.dry_run)

    handled = configure_important_items(dry_run=args.dry_run)
    if not args.skip_diff_review:
        review_remaining_diffs(handled, dry_run=args.dry_run)

    print_header("Done")
    print("Local configuration review complete.")
    print("No Terraform or Ansible commands were run.")


if __name__ == "__main__":
    main()
