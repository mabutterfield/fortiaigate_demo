#!/usr/bin/env python3
"""Guided Terraform and Ansible quick start for the FortiAIGate demo."""

from __future__ import annotations

import argparse
import ipaddress
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import user_profile as profile_tool


REPO_ROOT = Path(__file__).resolve().parents[1]

APPLIANCE_LOCAL_FILE_PAIRS = {
    "fortigate": ("terraform/aws-fortigate/99-local.auto.tfvars.example", "terraform/aws-fortigate/99-local.auto.tfvars"),
    "fortiweb": ("terraform/aws-fortiweb/99-local.auto.tfvars.example", "terraform/aws-fortiweb/99-local.auto.tfvars"),
}

REQUIRED_COMMANDS = ["terraform", "aws", "ansible-playbook", "ansible-galaxy"]
TERRAFORM_MODULES = [
    ("ECR registry", "terraform/aws-ecr"),
    ("AWS prep", "terraform/aws-prep"),
    ("EC2 k3s foundation", "terraform/aws-ec2-k3s"),
]
APPLIANCE_TERRAFORM_MODULES = {
    "fortigate": ("FortiGate appliance", "terraform/aws-fortigate"),
    "fortiweb": ("FortiWeb appliance", "terraform/aws-fortiweb"),
}
APPLIANCE_ANSIBLE_PLANS = {
    "fortigate": {
        "label": "FortiGate appliance",
        "inventory": "ansible/inventory/fortigate.generated.ini",
        "status": "status_fortigate.yml",
        "configure": [
            ("FortiGate baseline configuration", "configure_fortigate.yml"),
            ("FortiGate API accounts", "configure_fortigate_api_accounts.yml"),
        ],
    },
    "fortiweb": {
        "label": "FortiWeb appliance",
        "inventory": "ansible/inventory/fortiweb.generated.ini",
        "status": "status_fortiweb.yml",
        "configure": [
            ("FortiWeb baseline configuration", "configure_fortiweb.yml"),
        ],
    },
}
APPLIANCE_COLLECTION_REQUIREMENTS = {
    "fortigate": {
        "ansible.netcommon": "8.2.0",
        "fortinet.fortios": "2.5.1",
    },
    "fortiweb": {
        "ansible.netcommon": "8.2.0",
        "fortinet.fortiweb": "1.3.2",
    },
}
APPLIANCE_LICENSES = {
    "fortigate": {
        "label": "FortiGate",
        "module_path": "terraform/aws-fortigate",
        "mode_key": "fortigate_license_mode",
        "file_key": "fortigate_license_file",
        "source_dir_key": "fortigate_license_source_dir",
        "file_name_key": "fortigate_license_file_name",
        "default_file": "FGVMSLTM00000000.lic",
    },
    "fortiweb": {
        "label": "FortiWeb",
        "module_path": "terraform/aws-fortiweb",
        "mode_key": "fortiweb_license_mode",
        "file_key": "fortiweb_license_file",
        "source_dir_key": "fortiweb_license_source_dir",
        "file_name_key": "fortiweb_license_file_name",
        "default_file": "FWBVMSTM00000000.lic",
    },
}
APPLICATION_PLAYBOOKS = [
    ("LiteLLM proxy", "deploy_litellm.yml", "status_litellm.yml"),
    ("MCP demo tools", "deploy_mcp.yml", "status_mcp.yml"),
    ("optional Open WebUI", "deploy_openwebui.yml", "status_openwebui.yml", "openwebui_enabled"),
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
ANSIBLE_VAR_LOAD_ORDER = [
    "ansible/group_vars/env.yml",
    "ansible/group_vars/images.yml",
    "ansible/group_vars/system.yml",
    "ansible/group_vars/terraform.generated.yml",
    "ansible/group_vars/ecr.generated.yml",
    "ansible/group_vars/ports.generated.yml",
    "ansible/group_vars/fortiweb.generated.yml",
    "ansible/group_vars/user.yml",
]


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


def installed_ansible_collection_version(collection_name: str) -> str:
    result = subprocess.run(
        ["ansible-galaxy", "collection", "list", collection_name],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return ""

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == collection_name:
            return parts[1]
    return ""


def required_appliance_collections(appliance_keys: list[str]) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for appliance_key in appliance_keys:
        requirements.update(APPLIANCE_COLLECTION_REQUIREMENTS.get(appliance_key, {}))
    return requirements


def find_appliance_collection_problems(appliance_keys: list[str]) -> list[str]:
    requirements = required_appliance_collections(appliance_keys)
    if not requirements:
        return []

    problems: list[str] = []
    for collection_name, required_version in sorted(requirements.items()):
        installed_version = installed_ansible_collection_version(collection_name)
        if not installed_version:
            problems.append(f"{collection_name}: missing, required {required_version}")
            print(f"{collection_name}: missing, required {required_version}")
            continue
        if installed_version != required_version:
            problems.append(f"{collection_name}: installed {installed_version}, required {required_version}")
            print(f"{collection_name}: installed {installed_version}, required {required_version}")
            continue
        print(f"{collection_name}: {installed_version}")
    return problems


def ensure_appliance_collections(appliance_keys: list[str]) -> None:
    requirements = required_appliance_collections(appliance_keys)
    if not requirements:
        return

    print_header("Checking Fortinet Ansible Collections")
    problems = find_appliance_collection_problems(appliance_keys)
    if not problems:
        return

    print("Installing pinned Fortinet Ansible collections from ansible/collections/requirements.yml.")
    run_command(
        [
            "ansible-galaxy",
            "collection",
            "install",
            "-r",
            "ansible/collections/requirements.yml",
            "--force-with-deps",
        ]
    )

    print_header("Verifying Fortinet Ansible Collections")
    problems = find_appliance_collection_problems(appliance_keys)
    if problems:
        raise SystemExit(
            "Fortinet Ansible collection installation did not produce the required versions: "
            + "; ".join(problems)
        )


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
    print("3. skip")

    while True:
        value = prompt_text("AWS login command", default_method).strip().lower()
        if value in {"1", "sso", "aws sso login"}:
            return "sso"
        if value in {"2", "login", "aws login"}:
            return "login"
        if value in {"3", "skip", "none", "no"}:
            return "skip"
        print("Choose aws sso login, aws login, or skip.")


def ensure_aws_login(profile: str) -> None:
    print_header("Checking AWS Login")
    result = run_command(["aws", "sts", "get-caller-identity", "--profile", profile], check=False)
    if result.returncode == 0:
        return
    print("AWS caller identity check failed.")
    method = choose_aws_login_method(profile)
    if method == "skip":
        raise SystemExit("AWS login is required before Terraform can run.")

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


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def module_system_tfvars_path(module_path: str) -> Path:
    return REPO_ROOT / module_path / "00-system.auto.tfvars"


def module_local_tfvars_path(module_path: str) -> Path:
    return REPO_ROOT / module_path / "99-local.auto.tfvars"


def read_existing_file(path: Path) -> str:
    return read_file(path) if path.exists() else ""


def read_effective_module_tfvars(module_path: str) -> str:
    parts = [
        read_existing_file(module_system_tfvars_path(module_path)),
        read_existing_file(module_local_tfvars_path(module_path)),
    ]
    return "\n".join(part for part in parts if part)


def get_tf_string(content: str, key: str, default: str = "") -> str:
    matches = re.findall(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"', content)
    return matches[-1] if matches else default


def get_tf_bool(content: str, key: str, default: bool = False) -> bool:
    matches = re.findall(rf"(?m)^\s*{re.escape(key)}\s*=\s*(true|false)\b", content)
    if not matches:
        return default
    return matches[-1] == "true"


def get_tf_object_bool(content: str, object_key: str, item_key: str, default: bool = False) -> bool:
    matches = re.findall(rf"(?ms)^\s*{re.escape(object_key)}\s*=\s*\{{(.*?)^\s*\}}", content)
    if not matches:
        return default
    item_match = re.search(rf"(?m)^\s*{re.escape(item_key)}\s*=\s*(true|false)\b", matches[-1])
    if not item_match:
        return default
    return item_match.group(1) == "true"


def get_tf_list_strings(content: str, key: str) -> list[str]:
    matches = re.findall(rf"(?ms)^\s*{re.escape(key)}\s*=\s*\[(.*?)\]", content)
    if not matches:
        single = get_tf_string(content, key)
        return [single] if single else []
    return re.findall(r'"([^"]+)"', matches[-1])


def get_tf_map_strings(content: str, key: str) -> dict[str, str]:
    matches = re.findall(rf"(?ms)^\s*{re.escape(key)}\s*=\s*\{{(.*?)\}}", content)
    if not matches:
        return {}
    pairs: dict[str, str] = {}
    for pair_match in re.finditer(r'(?m)^\s*"?([^"\s=]+)"?\s*=\s*"([^"]*)"', matches[-1]):
        pairs[pair_match.group(1)] = pair_match.group(2)
    return pairs


def set_tf_string(content: str, key: str, value: str) -> str:
    replacement = f'{key} = "{value}"'
    pattern = rf'(?m)^\s*{re.escape(key)}\s*=\s*"[^"]*"'
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_tf_bool(content: str, key: str, value: bool) -> str:
    replacement = f"{key} = {str(value).lower()}"
    pattern = rf"(?m)^\s*{re.escape(key)}\s*=\s*(true|false)\b"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_tf_object_bool(content: str, object_key: str, item_key: str, value: bool) -> str:
    value_text = str(value).lower()
    pattern = rf"(?ms)^(\s*{re.escape(object_key)}\s*=\s*\{{\n)(.*?)(^\s*\}})"
    match = re.search(pattern, content)
    if not match:
        replacement = f"{object_key} = {{\n  {item_key} = {value_text}\n}}\n"
        return content.rstrip() + f"\n{replacement}"

    prefix, body, suffix = match.group(1), match.group(2), match.group(3)
    item_pattern = rf"(?m)^(\s*{re.escape(item_key)}\s*=\s*)(true|false)\b"
    if re.search(item_pattern, body):
        updated_body = re.sub(item_pattern, rf"\g<1>{value_text}", body, count=1)
    else:
        updated_body = body
        if updated_body and not updated_body.endswith("\n"):
            updated_body += "\n"
        updated_body += f"  {item_key} = {value_text}\n"
    return content[: match.start()] + prefix + updated_body + suffix + content[match.end() :]


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


def normalize_cidr_value(value: str, label: str) -> str:
    if "/" not in value:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ValueError(f"{label} must contain valid CIDR blocks. Invalid value: {value}. Error: {error}") from error

        host_prefix = 32 if address.version == 4 else 128
        suggested = f"{address}/{host_prefix}"
        if prompt_yes_no(f"{value} is a single IP address. Use {suggested}?", True):
            return suggested
        raise ValueError(f"{label} must use CIDR notation with a prefix length. Example: 203.0.113.10/32")

    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError as error:
        raise ValueError(f"{label} must contain valid CIDR blocks. Invalid value: {value}. Error: {error}") from error


def validate_cidr_list(values: list[str], label: str) -> list[str]:
    validated: list[str] = []
    for value in values:
        validated.append(normalize_cidr_value(value, label))
    return validated


def prompt_cidr_list(prompt: str, default: str, label: str) -> list[str]:
    while True:
        cidr_text = prompt_text(prompt, default)
        cidrs = [entry.strip() for entry in cidr_text.split(",") if entry.strip()]
        if not cidrs:
            print("At least one trusted source CIDR is required.")
            continue
        try:
            return validate_cidr_list(cidrs, label)
        except ValueError as error:
            print(error)


def get_yaml_scalar(content: str, key: str, default: str = "") -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*(.*)$", content)
    if not match:
        return default
    return match.group(1).strip().strip('"').strip("'")


def get_yaml_bool(content: str, key: str, default: bool = False) -> bool:
    value = get_yaml_scalar(content, key, str(default).lower()).lower()
    return value in {"true", "yes", "on", "1"}


def get_layered_yaml_bool(key: str, default: bool = False) -> bool:
    value = default
    for rel_path in ANSIBLE_VAR_LOAD_ORDER:
        path = REPO_ROOT / rel_path
        if path.exists():
            value = get_yaml_bool(read_file(path), key, value)
    return value


def set_yaml_scalar(content: str, key: str, value: str) -> str:
    replacement = f"{key}: {value}"
    pattern = rf"(?m)^\s*{re.escape(key)}:\s*.*$"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


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
    if start is None:
        return None

    end = start + len(lines[start_index])
    for next_line in lines[start_index + 1 :]:
        if next_line.strip() and not next_line.startswith((" ", "\t", "#")):
            break
        end += len(next_line)
    return start, end


def get_yaml_list_strings(content: str, key: str) -> list[str]:
    span = yaml_block_span(content, key)
    if span is None:
        return []
    block = content[span[0] : span[1]]
    values: list[str] = []
    for line in block.splitlines()[1:]:
        match = re.match(r"\s*-\s*(.*?)\s*$", line)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            if value:
                values.append(value)
    return values


def get_yaml_map_strings(content: str, key: str) -> dict[str, str]:
    span = yaml_block_span(content, key)
    if span is None:
        return {}
    block = content[span[0] : span[1]]
    first_line = block.splitlines()[0] if block.splitlines() else ""
    if re.search(r":\s*\{\s*\}\s*$", first_line):
        return {}

    values: dict[str, str] = {}
    for line in block.splitlines()[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r'\s*([^:#][^:]*):\s*"?([^"#]+?)"?\s*(?:#.*)?$', line)
        if match:
            values[match.group(1).strip().strip('"').strip("'")] = match.group(2).strip().strip('"').strip("'")
    return values


def set_yaml_list_strings(content: str, key: str, values: list[str]) -> str:
    rendered = "\n".join(f"  - {value}" for value in values)
    replacement = f"{key}:\n{rendered}\n"
    span = yaml_block_span(content, key)
    if span is None:
        return content.rstrip() + f"\n{replacement}"
    return content[: span[0]] + replacement + content[span[1] :]


def resolve_ansible_path(value: str) -> Path:
    workspace_root = os.environ.get("FAIG_WORKSPACE_ROOT") or str(REPO_ROOT.parent)
    resolved = value.strip().strip('"').strip("'")
    resolved = resolved.replace("{{ faig_workspace_root }}", workspace_root)
    resolved = resolved.replace("{{faig_workspace_root}}", workspace_root)
    path = Path(resolved).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def render_license_source_dir_for_yaml(path: Path) -> str:
    default_license_dir = (REPO_ROOT.parent / "licenses").resolve()
    try:
        if path.expanduser().resolve() == default_license_dir:
            return '"{{ faig_workspace_root }}/licenses"'
    except FileNotFoundError:
        pass
    return str(path.expanduser())


def list_license_candidates(source_dir: Path) -> list[Path]:
    if not source_dir.exists() or not source_dir.is_dir():
        return []
    preferred_suffixes = {".lic", ".license"}
    preferred = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in preferred_suffixes)
    if preferred:
        return preferred
    return sorted(path for path in source_dir.iterdir() if path.is_file())


def choose_license_file(source_dir: Path, default_license: str = "") -> str:
    candidates = list_license_candidates(source_dir)
    if candidates:
        print(f"Available license files in {source_dir}:")
        for index, path in enumerate(candidates, start=1):
            marker = " (current)" if path.name == default_license else ""
            print(f"{index}. {path.name}{marker}")
        print("m. Enter a file name manually")
    else:
        print(f"No license files were found in {source_dir}.")

    while True:
        selected = prompt_text("FortiAIGate license file name, number, or m", default_license or (candidates[0].name if candidates else ""))
        if selected.lower() == "m":
            manual = prompt_text("FortiAIGate license file name")
            if manual:
                return Path(manual).name
        if selected.isdigit() and candidates:
            index = int(selected)
            if 1 <= index <= len(candidates):
                return candidates[index - 1].name
        if selected:
            return Path(selected).name
        print("Enter a license file name.")


def resolve_tf_path(value: str, module_path: str) -> Path:
    path = Path(value.strip().strip('"').strip("'")).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / module_path / path
    return path


def resolve_appliance_license_parts(content: str, config: dict[str, str]) -> tuple[Path, str, str]:
    module_path = config["module_path"]
    legacy_value = get_tf_string(content, config["file_key"])
    if legacy_value:
        legacy_path = resolve_tf_path(legacy_value, module_path)
        return legacy_path, legacy_value, legacy_path.name

    source_dir_value = get_tf_string(content, config["source_dir_key"], "../../../licenses")
    file_name = get_tf_string(content, config["file_name_key"], config["default_file"])
    source_dir = resolve_tf_path(source_dir_value, module_path)
    return source_dir / file_name, f"{source_dir_value.rstrip('/')}/{file_name}", file_name


def render_appliance_license_dir_for_tfvars(selected_path: Path, module_path: str) -> str:
    license_dir = (REPO_ROOT.parent / "licenses").resolve()
    resolved = selected_path.expanduser().resolve()
    try:
        if resolved.parent == license_dir:
            return "../../../licenses"
    except FileNotFoundError:
        pass

    try:
        return os.path.relpath(resolved.parent, REPO_ROOT / module_path)
    except ValueError:
        return str(resolved.parent)


def choose_appliance_license_file(label: str, source_dir: Path, default_license: str = "") -> Path:
    candidates = list_license_candidates(source_dir)
    if candidates:
        print(f"Available {label} license files in {source_dir}:")
        for index, path in enumerate(candidates, start=1):
            marker = " (current)" if path.name == default_license else ""
            print(f"{index}. {path.name}{marker}")
        print("m. Enter a path manually")
    else:
        print(f"No license files were found in {source_dir}.")

    while True:
        selected = prompt_text(f"{label} license file name, path, number, or m", default_license or (candidates[0].name if candidates else ""))
        if selected.lower() == "m":
            manual = prompt_text(f"{label} license file path")
            if manual:
                selected_path = Path(manual).expanduser()
            else:
                continue
        elif selected.isdigit() and candidates:
            index = int(selected)
            if 1 <= index <= len(candidates):
                selected_path = candidates[index - 1]
            else:
                print("Choose a listed number, m, or a file path.")
                continue
        else:
            selected_path = Path(selected).expanduser()

        if not selected_path.is_absolute():
            selected_path = source_dir / selected_path
        if selected_path.is_file():
            return selected_path
        print(f"Selected {label} license file does not exist: {selected_path}")


def configure_appliance_license_preflight(appliance_keys: list[str], *, noninteractive: bool = False) -> None:
    if not appliance_keys:
        return

    print_header("Appliance License Preflight")
    default_license_dir = (REPO_ROOT.parent / "licenses").resolve()

    for appliance_key in appliance_keys:
        config = APPLIANCE_LICENSES[appliance_key]
        label = config["label"]
        module_path = config["module_path"]
        tfvars_path = module_local_tfvars_path(module_path)
        effective_content = read_effective_module_tfvars(module_path)
        local_content = read_existing_file(tfvars_path)
        license_mode = get_tf_string(effective_content, config["mode_key"], "byol_file")

        if license_mode != "byol_file":
            print(f"{label}: {config['mode_key']}={license_mode}; no local BYOL license file stat needed.")
            continue

        license_path, license_value, license_name = resolve_appliance_license_parts(effective_content, config)
        if not license_name:
            raise SystemExit(f"{label} license preflight failed: {config['file_name_key']} is empty.")

        using_default = license_name == config["default_file"]
        if license_path.is_file() and not using_default:
            print(f"{label}: found license file {license_path}")
            continue

        if noninteractive:
            reason = "uses the committed placeholder path" if using_default else "does not exist"
            raise SystemExit(
                f"{label} license preflight failed: {license_value} {reason}. "
                f"Set {config['source_dir_key']} and {config['file_name_key']}, or use {config['mode_key']}=\"none\"."
            )

        reason = "is still the committed placeholder" if using_default else "does not exist"
        print(f"{label}: license {reason}: {license_value}")
        selected_path = choose_appliance_license_file(label, default_license_dir, license_name if not using_default else "")
        local_content = set_tf_string(local_content, config["file_key"], "")
        local_content = set_tf_string(local_content, config["source_dir_key"], render_appliance_license_dir_for_tfvars(selected_path, module_path))
        local_content = set_tf_string(local_content, config["file_name_key"], selected_path.name)
        write_file(tfvars_path, local_content)
        print(f"updated: {tfvars_path.relative_to(REPO_ROOT)}")
        print(f"{label}: license directory {selected_path.parent}")
        print(f"{label}: selected license file {selected_path}")


def configure_license_preflight(*, noninteractive: bool = False) -> None:
    print_header("FortiAIGate License Preflight")
    path = REPO_ROOT / "ansible/group_vars/user.yml"
    content = read_file(path)

    raw_source_dir = get_yaml_scalar(content, "license_source_dir", "{{ faig_workspace_root }}/licenses")
    source_dir = resolve_ansible_path(raw_source_dir)
    license_files = get_yaml_list_strings(content, "fortiaigate_license_files")
    explicit_license_map = get_yaml_map_strings(content, "fortiaigate_licenses")
    required_files = sorted(set(explicit_license_map.values())) if explicit_license_map else license_files[:1]

    def missing_files() -> list[str]:
        return [name for name in required_files if not (source_dir / name).is_file()]

    missing = missing_files()
    if required_files and not missing:
        print(f"License source directory: {source_dir}")
        for license_file in required_files:
            print(f"found: {license_file}")
        return

    if noninteractive:
        if not required_files:
            raise SystemExit(
                "FortiAIGate license preflight failed: no fortiaigate_license_files or fortiaigate_licenses are configured."
            )
        raise SystemExit(
            "FortiAIGate license preflight failed. Missing files under "
            f"{source_dir}: {', '.join(missing)}"
        )

    print("FortiAIGate licenses are expected before deployment.")
    print("The Ansible role later copies the selected file from the license source directory into the temporary Helm chart copy.")
    selected_source_dir = prompt_text("License source directory", str(source_dir))
    source_dir = Path(selected_source_dir).expanduser()
    if not source_dir.is_absolute():
        source_dir = (REPO_ROOT / source_dir).resolve()

    default_license = license_files[0] if license_files else ""
    selected_license = choose_license_file(source_dir, default_license)
    selected_path = source_dir / selected_license
    if not selected_path.is_file():
        raise SystemExit(f"Selected FortiAIGate license file does not exist: {selected_path}")

    content = set_yaml_scalar(content, "license_source_dir", render_license_source_dir_for_yaml(source_dir))
    content = set_yaml_list_strings(content, "fortiaigate_license_files", [selected_license])
    write_file(path, content)
    print(f"updated: {path.relative_to(REPO_ROOT)}")
    print(f"selected license: {selected_path}")


def configure_litellm_credentials(*, noninteractive: bool = False) -> None:
    print_header("LiteLLM Credentials")
    path = REPO_ROOT / "ansible/group_vars/user.yml"
    content = read_file(path)

    if noninteractive:
        print("Skipping LiteLLM credential prompts because --yolo was set.")
        print("Using LiteLLM credential values already configured in ansible/group_vars/user.yml.")
        return

    print("Press Enter to keep the current value, or type a new value.")
    fields = [
        ("litellm_master_key", "LiteLLM API/master key"),
        ("litellm_ui_username", "LiteLLM admin username"),
        ("litellm_ui_password", "LiteLLM admin password"),
    ]
    updated_content = content
    for key, label in fields:
        current_value = get_yaml_scalar(updated_content, key)
        new_value = prompt_text(label, current_value)
        if new_value:
            updated_content = set_yaml_scalar(updated_content, key, new_value)

    if updated_content != content:
        write_file(path, updated_content)
        print(f"updated: {path.relative_to(REPO_ROOT)}")
    else:
        print("LiteLLM credentials unchanged.")


def configure_user_tfvars(profile: str) -> tuple[str, str, str, list[str], str]:
    print_header("Shared Terraform Config")
    path = REPO_ROOT / "terraform/user.tfvars"
    content = read_file(path)

    current_region = get_tf_string(content, "aws_region", "us-east-1")
    profile_region = command_output(["aws", "configure", "get", "region", "--profile", profile], check=False)
    default_region = profile_region or current_region or "us-east-1"
    current_prefix = get_tf_string(content, "name_prefix", "fortiaigate-demo")
    current_key_name = get_tf_string(content, "ssh_key_name")
    current_private_key = get_tf_string(content, "ssh_private_key_file")
    current_cidrs = get_tf_list_strings(content, "allowed_ingress_cidr")
    current_tags = get_tf_map_strings(content, "tags")

    region = prompt_text("AWS region", default_region)
    name_prefix = prompt_text("Deployment name prefix", current_prefix)
    key_name = choose_ec2_key_pair(profile, region, current_key_name)
    private_key = choose_local_ssh_private_key(current_private_key, key_name)
    cidr_default = ", ".join(current_cidrs) if current_cidrs else ""
    cidrs = prompt_cidr_list("Trusted source CIDR list, comma-separated", cidr_default, "Trusted source CIDR list")
    tags_text = prompt_text("Optional Terraform tags, comma-separated key=value", render_tags_prompt_default(current_tags))
    tags = parse_tags_text(tags_text)

    content = set_tf_string(content, "aws_profile", profile)
    content = set_tf_string(content, "aws_region", region)
    content = set_tf_string(content, "name_prefix", name_prefix)
    content = set_tf_string(content, "ssh_key_name", key_name)
    content = set_tf_string(content, "ssh_private_key_file", private_key)
    content = set_tf_list_strings(content, "allowed_ingress_cidr", cidrs)
    content = set_tf_map_strings(content, "tags", tags)
    write_file(path, content)
    print(f"updated: {path.relative_to(REPO_ROOT)}")

    return profile, region, name_prefix, cidrs, key_name


def configure_ansible_env(profile: str, region: str) -> None:
    print_header("Ansible Terraform Bridge")
    print(
        "Terraform will write aws_profile, aws_region, SSH key details, CIDRs, "
        "and k3s host facts to ansible/group_vars/terraform.generated.yml."
    )


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


def requested_appliance_keys(args: argparse.Namespace) -> list[str]:
    requested: list[str] = []
    if args.include_appliances or args.include_fortigate:
        requested.append("fortigate")
    if args.include_appliances or args.include_fortiweb:
        requested.append("fortiweb")
    return requested


def appliance_tfvars_path(appliance_key: str) -> Path:
    return REPO_ROOT / APPLIANCE_LOCAL_FILE_PAIRS[appliance_key][1]


def appliance_enabled_from_tfvars(appliance_key: str) -> bool:
    module_path = APPLIANCE_TERRAFORM_MODULES[appliance_key][1]
    content = read_effective_module_tfvars(module_path)
    enabled_key = f"{appliance_key}_enabled"
    return get_tf_bool(content, enabled_key, False)


def selected_appliance_keys(args: argparse.Namespace) -> list[str]:
    requested = set(requested_appliance_keys(args))
    selected: list[str] = []
    for appliance_key in APPLIANCE_LOCAL_FILE_PAIRS:
        if appliance_key in requested or appliance_enabled_from_tfvars(appliance_key):
            selected.append(appliance_key)
    return selected


def configure_appliance_tfvars(appliance_keys: list[str]) -> None:
    if not appliance_keys:
        return

    print_header("Appliance Terraform Config")
    for appliance_key in appliance_keys:
        path = appliance_tfvars_path(appliance_key)
        content = read_existing_file(path)
        content = set_tf_bool(content, f"{appliance_key}_enabled", True)
        write_file(path, content)
        print(f"updated: {path.relative_to(REPO_ROOT)}")


def ensure_appliance_prep_tfvars(appliance_keys: list[str]) -> None:
    if not appliance_keys:
        return

    print_header("Appliance AWS Prep Config")
    path = module_local_tfvars_path("terraform/aws-prep")
    content = read_existing_file(path)
    effective = read_effective_module_tfvars("terraform/aws-prep")
    updated = content
    changes: list[str] = []

    if "fortigate" in appliance_keys and not get_tf_object_bool(effective, "allocate_eips", "fortigate", False):
        updated = set_tf_object_bool(updated, "allocate_eips", "fortigate", True)
        changes.append("allocate_eips.fortigate=true")

    if "fortiweb" in appliance_keys:
        if not get_tf_object_bool(effective, "allocate_eips", "fortiweb", False):
            updated = set_tf_object_bool(updated, "allocate_eips", "fortiweb", True)
            changes.append("allocate_eips.fortiweb=true")
        if not get_tf_bool(effective, "fortiweb_enabled", False):
            updated = set_tf_bool(updated, "fortiweb_enabled", True)
            changes.append("fortiweb_enabled=true")

    if updated != content:
        write_file(path, updated)
        print(f"updated: {path.relative_to(REPO_ROOT)}")
        print("enabled for appliance deployment:")
        for change in changes:
            print(f"- {change}")
    else:
        print("AWS prep already has the required appliance settings enabled.")


def parse_ecr_tfvars() -> tuple[str, list[str]]:
    content = read_effective_module_tfvars("terraform/aws-ecr")
    repo_prefix = get_tf_string(content, "repo_prefix", "fortiaigate")
    repositories = get_tf_list_strings(content, "repositories")
    if not repositories:
        raise SystemExit("No repositories found in terraform/aws-ecr effective tfvars.")
    return repo_prefix, repositories


def get_ecr_state_repository_names() -> set[str]:
    result = run_command(
        ["terraform", "-chdir=terraform/aws-ecr", "state", "list"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return set()

    names: set[str] = set()
    for line in (result.stdout or "").splitlines():
        match = re.search(r'aws_ecr_repository\.this\["([^"]+)"\]', line)
        if match:
            names.add(match.group(1))
    return names


def show_ecr_state_status(repositories: list[str]) -> tuple[list[str], list[str]]:
    print_header("ECR Terraform State")
    configured = set(repositories)
    tracked = get_ecr_state_repository_names()
    tracked_configured = sorted(configured.intersection(tracked))
    missing = sorted(configured.difference(tracked))
    extra = sorted(tracked.difference(configured))

    if not tracked_configured and missing:
        print("No configured ECR repositories are currently tracked in Terraform state.")
        print("Recommended action: import existing repositories before apply if these repos already exist.")
        print("If this is a brand-new registry, continuing with apply will create them.")
    elif missing:
        print("Terraform state tracks some, but not all, configured ECR repositories.")
        print("Safe action: import the missing repositories if they already exist, then apply.")
        print("If the missing repositories are intentionally new, apply can create only those missing repos.")
    else:
        print("Terraform state tracks all configured ECR repositories.")
        print("Safe for apply: Terraform should update policy/settings instead of trying to recreate repositories.")

    print("Configured repositories:")
    for repository in sorted(configured):
        state = "tracked" if repository in tracked else "missing from state"
        print(f"- {repository}: {state}")

    if extra:
        print("State also tracks repositories not currently configured:")
        for repository in extra:
            print(f"- {repository}")

    return tracked_configured, missing


def profile_review_files() -> list[Path]:
    return [path for path in profile_tool.ALLOWLIST if (REPO_ROOT / path).exists()]


def page_file(path: Path) -> None:
    absolute_path = REPO_ROOT / path
    pager = shutil.which("less")
    if pager and sys.stdin.isatty():
        subprocess.run([pager, str(absolute_path)], cwd=str(REPO_ROOT), check=False)
        return
    print(absolute_path.read_text(encoding="utf-8"))


def prompt_profile_review() -> None:
    print_header("User Profile Review")
    review_files = profile_review_files()
    if not review_files:
        print("No profile files exist to review.")
        return
    if not prompt_yes_no("Would you like to review user profile files before Terraform?", True):
        return

    while True:
        print("Profile files:")
        for index, path in enumerate(review_files, start=1):
            print(f"{index}. {path.as_posix()}")
        print("d. done")
        choice = prompt_text("File number or done", "done").strip().lower()
        if choice in {"", "d", "done", "q", "quit", "exit"}:
            return
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(review_files):
                page_file(review_files[index - 1])
                continue
        print("Choose a listed number or done.")


def terraform_init_validate(module_path: str) -> None:
    run_command(["terraform", "-chdir=" + module_path, "init"])
    run_command(["terraform", "-chdir=" + module_path, "validate"])


def terraform_apply(module_path: str, auto_approve: bool) -> None:
    argv = ["terraform", "-chdir=" + module_path, "apply"]
    if auto_approve:
        argv.append("-auto-approve")
    run_command(argv)


def import_existing_ecr_repos(
    repositories_to_import: list[str] | None = None,
    *,
    prompt_on_failure: bool = True,
) -> None:
    print_header("Importing Existing ECR Repositories")
    repo_prefix, repositories = parse_ecr_tfvars()
    target_repositories = repositories_to_import if repositories_to_import is not None else repositories
    if not target_repositories:
        print("No ECR repositories need import based on current Terraform state.")
        return

    for repository in target_repositories:
        address = f'aws_ecr_repository.this["{repository}"]'
        import_id = f"{repo_prefix}/{repository}"
        result = run_command(
            ["terraform", "-chdir=terraform/aws-ecr", "import", address, import_id],
            check=False,
        )
        if result.returncode == 0:
            continue
        print(f"Import failed for {import_id}. It may already be imported or may not exist.")
        if not prompt_on_failure:
            print("Continuing because noninteractive import mode is enabled.")
            continue
        if not prompt_yes_no("Continue importing/applying the remaining repositories?", True):
            raise SystemExit(result.returncode)


def aws_ecr_repository_exists(profile: str, region: str, repository_name: str) -> bool:
    result = subprocess.run(
        [
            "aws",
            "ecr",
            "describe-repositories",
            "--profile",
            profile,
            "--region",
            region,
            "--repository-names",
            repository_name,
            "--query",
            "repositories[0].repositoryName",
            "--output",
            "text",
        ],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0 and (result.stdout or "").strip() == repository_name


def find_existing_aws_ecr_repos(profile: str, region: str, repo_prefix: str, repositories: list[str]) -> list[str]:
    print_header("AWS ECR Repository Discovery")
    existing: list[str] = []
    for repository in repositories:
        repository_name = f"{repo_prefix}/{repository}"
        if aws_ecr_repository_exists(profile, region, repository_name):
            existing.append(repository)
            print(f"- {repository_name}: exists")
        else:
            print(f"- {repository_name}: not found")
    return existing


def run_terraform(
    ecr_mode: str,
    auto_approve: bool,
    appliance_keys: list[str],
    profile: str,
    region: str,
    *,
    noninteractive_import: bool = False,
) -> None:
    print_header("Terraform: ECR")
    terraform_init_validate("terraform/aws-ecr")
    repo_prefix, repositories = parse_ecr_tfvars()
    _tracked_repositories, missing_repositories = show_ecr_state_status(repositories)
    if ecr_mode == "existing":
        import_existing_ecr_repos(missing_repositories, prompt_on_failure=not noninteractive_import)
    elif ecr_mode == "auto":
        existing_repositories = find_existing_aws_ecr_repos(profile, region, repo_prefix, missing_repositories)
        if existing_repositories:
            import_existing_ecr_repos(existing_repositories)
        else:
            print("No missing configured ECR repositories were found in AWS. Terraform apply can create them.")
    elif missing_repositories:
        if prompt_yes_no("Import missing ECR repositories before apply?", True):
            import_existing_ecr_repos(missing_repositories)
    terraform_apply("terraform/aws-ecr", auto_approve)

    for label, module_path in TERRAFORM_MODULES[1:]:
        print_header(f"Terraform: {label}")
        terraform_init_validate(module_path)
        terraform_apply(module_path, auto_approve)

    for appliance_key in appliance_keys:
        label, module_path = APPLIANCE_TERRAFORM_MODULES[appliance_key]
        print_header(f"Terraform: {label}")
        terraform_init_validate(module_path)
        terraform_apply(module_path, auto_approve)


def get_ec2_instance_id() -> str:
    return command_output(["terraform", "-chdir=terraform/aws-ec2-k3s", "output", "-raw", "instance_id"])


def get_appliance_instance_id(appliance_key: str) -> str:
    _label, module_path = APPLIANCE_TERRAFORM_MODULES[appliance_key]
    output_name = f"{appliance_key}_instance_id"
    value = command_output(["terraform", "-chdir=" + module_path, "output", "-raw", output_name], check=False)
    return "" if value == "null" else value


def show_ec2_instance_status(profile: str, region: str, instance_id: str, label: str = "EC2 instance") -> bool:
    print_header(f"{label} Status")
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


def wait_for_ec2_status_ready(
    profile: str,
    region: str,
    instance_id: str,
    delay_seconds: int,
    max_attempts: int,
    label: str = "EC2 instance",
) -> None:
    attempts = max(1, max_attempts)
    delay = max(1, delay_seconds)

    for attempt in range(1, attempts + 1):
        print(f"Checking {label} readiness, attempt {attempt}/{attempts}.")
        if show_ec2_instance_status(profile, region, instance_id, label):
            print(f"{label} status is READY.")
            return

        if attempt == attempts:
            raise SystemExit(f"Stopped because {label} status did not become READY.")

        print(f"{label} is not ready yet. Waiting {delay} seconds before checking again.")
        time.sleep(delay)


def prompt_ec2_status(
    profile: str,
    region: str,
    *,
    wait_until_ready: bool = False,
    delay_seconds: int = 30,
    max_attempts: int = 20,
) -> None:
    instance_id = get_ec2_instance_id()
    if not instance_id:
        print("Could not read EC2 instance_id from terraform/aws-ec2-k3s outputs.")
        return

    if wait_until_ready:
        wait_for_ec2_status_ready(profile, region, instance_id, delay_seconds, max_attempts, "k3s EC2 instance")
        return

    while True:
        show_ec2_instance_status(profile, region, instance_id, "k3s EC2 instance")
        choice = prompt_text("Continue, recheck, or quit", "continue").strip().lower()
        if choice in {"", "c", "continue"}:
            return
        if choice in {"r", "recheck", "refresh", "retry", "status"}:
            continue
        if choice in {"q", "quit", "exit", "stop"}:
            raise SystemExit("Stopped after EC2 status check.")
        print("Enter continue, recheck, or quit.")


def show_appliance_ec2_statuses(
    profile: str,
    region: str,
    appliance_keys: list[str],
) -> None:
    if not appliance_keys:
        return

    print_header("Appliance EC2 Status Snapshot")
    print("Appliance API polling remains the readiness gate; AWS EC2 status can lag behind appliance login/API readiness.")
    for appliance_key in appliance_keys:
        label, _module_path = APPLIANCE_TERRAFORM_MODULES[appliance_key]
        instance_id = get_appliance_instance_id(appliance_key)
        if not instance_id:
            raise SystemExit(f"Could not read {appliance_key}_instance_id from Terraform outputs.")
        show_ec2_instance_status(profile, region, instance_id, f"{label} EC2 instance")


def choose_ecr_mode() -> str:
    print_header("ECR Mode")
    print("1. Auto-import existing ECR repositories missing from state, then apply")
    print("2. Create/manage ECR repositories with Terraform without import")
    print("3. Import all configured repositories missing from state, then apply")
    while True:
        value = prompt_text("Choose ECR mode", "1").strip().lower()
        if value in {"", "1", "auto"}:
            return "auto"
        if value in {"2", "new", "create"}:
            return "new"
        if value in {"3", "existing", "import"}:
            return "existing"
        print("Choose 1, 2, or 3.")


def run_ansible_playbook(
    playbook: str,
    *,
    inventory: str | None = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    argv = ["ansible-playbook"]
    if inventory:
        argv.extend(["-i", inventory])
    argv.append(f"ansible/playbooks/{playbook}")
    result = run_command(
        argv,
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


def run_ansible_playbook_until_success(
    label: str,
    playbook: str,
    *,
    inventory: str | None = None,
    delay_seconds: int = 30,
    max_attempts: int = 10,
) -> None:
    attempts = max(1, max_attempts)
    delay = max(1, delay_seconds)

    for attempt in range(1, attempts + 1):
        print(f"Checking {label}, attempt {attempt}/{attempts}.")
        result = run_ansible_playbook(playbook, inventory=inventory, check=False, capture=True)
        if result.returncode == 0:
            print(f"{label} is ready.")
            return

        if attempt == attempts:
            raise SystemExit(f"Stopped because {label} did not become ready.")

        print(f"{label} is not ready yet. Waiting {delay} seconds before checking again.")
        time.sleep(delay)


def run_image_publishing(args: argparse.Namespace) -> None:
    print_header("Ansible: ECR Image Publishing")
    if args.yolo:
        print("Skipping image publishing because --yolo was set.")
        print("Deployments assume required images already exist in the registry.")
        return

    print("Choose which images to publish now:")
    print("1. none (default)")
    print("2. chatbot only")
    print("3. FortiAIGate only")
    print("4. all")
    while True:
        selection = prompt_text("Image publishing selection", "none").strip().lower()
        if selection in {"", "1", "n", "none", "no", "skip"}:
            selection = "none"
            break
        if selection in {"2", "chatbot", "chat", "bot"}:
            selection = "chatbot"
            break
        if selection in {"3", "fortiaigate", "faig", "fortiai"}:
            selection = "fortiaigate"
            break
        if selection in {"4", "all", "both"}:
            selection = "all"
            break
        print("Choose none, chatbot, fortiaigate, or all.")

    if selection == "none":
        print("Skipping image publishing. Deployments assume required images already exist in the registry.")
        return

    if selection in {"fortiaigate", "all"}:
        run_ansible_playbook("publish_images.yml")
    if selection in {"chatbot", "all"}:
        run_ansible_playbook("publish_chatbot_images.yml")


def wait_for_fortiaigate_ready(
    delay_seconds: int,
    max_attempts: int,
) -> None:
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


def run_fortiaigate_status_once(label: str = "Ansible: FortiAIGate Status") -> None:
    print_header(label)
    run_ansible_playbook("status_fortiaigate.yml", check=False)


def deploy_with_status(label: str, deploy_playbook: str, status_playbook: str) -> None:
    print_header(f"Ansible: Deploy {label}")
    run_ansible_playbook(deploy_playbook)
    print_header(f"Ansible: Status {label}")
    run_ansible_playbook(status_playbook, check=False)


def optional_playbook_enabled(enabled_key: str) -> bool:
    return get_layered_yaml_bool(enabled_key, False)


def run_application_deployments(args: argparse.Namespace) -> None:
    for playbook_entry in APPLICATION_PLAYBOOKS:
        label, deploy_playbook, status_playbook, *optional_enabled_key = playbook_entry
        if optional_enabled_key and not optional_playbook_enabled(optional_enabled_key[0]):
            print_header(f"Ansible: Skip {label}")
            print(f"{optional_enabled_key[0]}=false; skipping {deploy_playbook}.")
            continue
        deploy_with_status(label, deploy_playbook, status_playbook)

    print_header("Ansible: Optional HTTPS Gateway")
    if args.yolo:
        print("Running optional HTTPS gateway playbook because --yolo was set.")
        print("The playbook should no-op when demo_https_gateway_enabled is false.")
        run_ansible_playbook("deploy_demo_https_gateway.yml", check=False)
    elif prompt_yes_no(
        "Run optional HTTPS gateway playbook now? Requires demo_https_gateway_enabled and Terraform-opened HTTPS ports",
        False,
    ):
        run_ansible_playbook("deploy_demo_https_gateway.yml")

    print_header("Ansible: Demo Outputs")
    run_ansible_playbook("show_demo_outputs.yml", check=False)


def run_appliance_ansible_deployments(args: argparse.Namespace, appliance_keys: list[str]) -> None:
    if not appliance_keys:
        return

    print_header("Ansible: Appliance Configuration")
    for appliance_key in appliance_keys:
        plan = APPLIANCE_ANSIBLE_PLANS[appliance_key]
        label = plan["label"]
        inventory = plan["inventory"]
        status_playbook = plan["status"]

        run_ansible_playbook_until_success(
            f"{label} API",
            status_playbook,
            inventory=inventory,
            delay_seconds=args.appliance_status_delay,
            max_attempts=args.appliance_status_retries,
        )

        for step_label, playbook in plan["configure"]:
            print_header(f"Ansible: {step_label}")
            run_ansible_playbook(playbook, inventory=inventory)

        print_header(f"Ansible: Status {label}")
        run_ansible_playbook(status_playbook, inventory=inventory, check=False)


def run_post_application_validations(appliance_keys: list[str]) -> None:
    if "fortiweb" not in appliance_keys:
        return

    print_header("Ansible: Validate Demo HTTP Paths")
    run_ansible_playbook("validate_demo_http_paths.yml", check=False)


def run_ansible_flow(args: argparse.Namespace, appliance_keys: list[str]) -> None:
    print_header("Ansible Deployment")
    if not args.yolo and not prompt_yes_no("Ready to start Ansible image publishing and deployment?", False):
        raise SystemExit("Stopped before Ansible execution.")

    faig_status_mode = args.faig_status_mode or "once"

    run_image_publishing(args)

    print_header("Ansible: Bootstrap k3s")
    run_ansible_playbook("bootstrap_gpu_k3s.yml")

    print_header("Ansible: Deploy FortiAIGate")
    run_ansible_playbook("deploy_fortiaigate.yml")
    if faig_status_mode == "wait":
        wait_for_fortiaigate_ready(
            args.faig_status_delay,
            args.faig_status_retries,
        )
    else:
        run_fortiaigate_status_once("Ansible: FortiAIGate Status After Deploy")

    run_appliance_ansible_deployments(args, appliance_keys)
    run_application_deployments(args)
    run_post_application_validations(appliance_keys)
    if faig_status_mode == "once":
        run_fortiaigate_status_once("Ansible: Final FortiAIGate Status")


def missing_user_profile_files() -> list[Path]:
    return [path for path in profile_tool.REQUIRED_PROFILE_FILES if not (REPO_ROOT / path).exists()]


def run_profile_init() -> str:
    profile_tool.init_profile(force=True)
    return "init"


def run_profile_import(path: str | None, *, yes: bool) -> str:
    profile_tool.import_profile(Path(path or profile_tool.DEFAULT_PROFILE_ARCHIVE), yes=yes)
    return "import"


def ensure_user_profile(args: argparse.Namespace) -> str:
    if args.export_profile is not None:
        profile_tool.export_profile(Path(args.export_profile or profile_tool.DEFAULT_PROFILE_ARCHIVE))
        return "export"

    action = ""
    if args.import_profile is not None:
        action = run_profile_import(args.import_profile, yes=args.yolo)

    if args.init_profile:
        if any((REPO_ROOT / path).exists() for path in profile_tool.REQUIRED_PROFILE_FILES):
            if args.yolo:
                raise SystemExit("--init with --yolo refuses to overwrite existing profile files.")
            if prompt_yes_no("Export the current user profile before reinitializing?", True):
                profile_tool.export_profile(profile_tool.DEFAULT_PROFILE_ARCHIVE)
        action = run_profile_init()

    missing = missing_user_profile_files()
    if not missing:
        profile_tool.ensure_instruction_slots()
        return action

    if args.yolo:
        missing_text = ", ".join(path.as_posix() for path in missing)
        raise SystemExit(
            "Missing required user profile files in --yolo mode: "
            f"{missing_text}. Run scripts/user_profile.py init or pass --import."
        )

    print_header("User Profile Required")
    print("Missing required user profile files:")
    for path in missing:
        print(f"- {path.as_posix()}")
    print("1. Import user profile")
    print("2. Initialize/onboard user profile")
    print("3. Exit")
    while True:
        choice = prompt_text("Choose profile action", "2").strip().lower()
        if choice in {"1", "import"}:
            import_path = prompt_text("Profile archive path", str(profile_tool.DEFAULT_PROFILE_ARCHIVE))
            return run_profile_import(import_path, yes=False)
        if choice in {"2", "init", "initialize", "onboard"}:
            return run_profile_init()
        if choice in {"3", "exit", "quit", "stop"}:
            raise SystemExit("Stopped before deployment.")
        print("Choose import, init, or exit.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guided Terraform bootstrap for the FortiAIGate demo.")
    parser.add_argument(
        "--yolo",
        action="store_true",
        help=(
            "Subsequent-run mode: use preconfigured vars, auto-approve Terraform, "
            "import missing ECR repository state, skip image publishing, and run Ansible without setup prompts."
        ),
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Pass -auto-approve to Terraform apply. Default is interactive Terraform approval.",
    )
    parser.add_argument(
        "--init",
        dest="init_profile",
        action="store_true",
        help="Initialize or reinitialize local user profile files before deployment.",
    )
    parser.add_argument(
        "--import",
        dest="import_profile",
        nargs="?",
        const=str(profile_tool.DEFAULT_PROFILE_ARCHIVE),
        default=None,
        help="Import a user profile archive before deployment. Default path: ../user_profile.tgz.",
    )
    parser.add_argument(
        "--export",
        dest="export_profile",
        nargs="?",
        const=str(profile_tool.DEFAULT_PROFILE_ARCHIVE),
        default=None,
        help="Export the current user profile archive and exit. Default path: ../user_profile.tgz.",
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
        "--include-fortigate",
        action="store_true",
        help="Ensure FortiGate local overrides are enabled, run terraform/aws-fortigate, and apply FortiGate Ansible configuration.",
    )
    parser.add_argument(
        "--include-fortiweb",
        action="store_true",
        help="Ensure FortiWeb local overrides are enabled, run terraform/aws-fortiweb, and apply FortiWeb Ansible configuration.",
    )
    parser.add_argument(
        "--include-appliances",
        action="store_true",
        help="Shortcut for --include-fortigate --include-fortiweb.",
    )
    parser.add_argument(
        "--ec2-status-delay",
        type=int,
        default=30,
        help="Seconds to wait between EC2 status checks before Ansible starts. Default: 30.",
    )
    parser.add_argument(
        "--ec2-status-retries",
        type=int,
        default=20,
        help="Maximum EC2 status checks before stopping. Default: 20.",
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
    parser.add_argument(
        "--faig-status-mode",
        choices=["wait", "once"],
        default=None,
        help=(
            "FortiAIGate post-deploy status behavior. wait polls until READY; once checks once, "
            "continues with other charts, then checks again at the end. Default: once."
        ),
    )
    parser.add_argument(
        "--appliance-status-delay",
        type=int,
        default=30,
        help="Seconds to wait between FortiGate/FortiWeb API readiness checks. Default: 30.",
    )
    parser.add_argument(
        "--appliance-status-retries",
        type=int,
        default=20,
        help="Maximum FortiGate/FortiWeb API readiness checks before stopping. Default: 20.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(REPO_ROOT)
    check_repo_root()
    terraform_auto_approve = args.auto_approve or args.yolo

    print("FortiAIGate automated quick start")
    print(f"Repo root: {REPO_ROOT}")
    print("This script can run Terraform, publish images, bootstrap k3s, and deploy the demo.")
    print("Existing local tfvars/YAML values are used as prompt defaults when present.")
    if args.yolo:
        print("\nYOLO mode is enabled.")
        print("- Terraform apply uses -auto-approve.")
        print("- ECR repositories missing from state are imported before apply when possible.")
        print("- Image publishing is skipped.")
        print("- FortiAIGate status is checked once after deploy, then again after app deployment.")
        print("- Terraform/Ansible execution prompts are skipped where safe.")
    requested_appliances = requested_appliance_keys(args)
    if requested_appliances:
        print("\nRequested optional appliance deployment:")
        for appliance_key in requested_appliances:
            print(f"- {appliance_key}")

    check_requirements()
    profile_action = ensure_user_profile(args)
    if profile_action == "export":
        return
    profile_tool.warn_legacy_files()

    current_user_tfvars = read_file(REPO_ROOT / "terraform/user.tfvars")
    default_profile = get_tf_string(current_user_tfvars, "aws_profile")
    profile_is_fresh = profile_action in {"init", "import"}
    if (args.yolo or profile_is_fresh) and default_profile:
        profile = default_profile
        print_header("AWS Profile")
        print(f"Using aws_profile from terraform/user.tfvars: {profile}")
    else:
        profile = choose_aws_profile(default_profile)
    ensure_aws_login(profile)

    if args.yolo:
        region = get_tf_string(current_user_tfvars, "aws_region")
        ssh_key_name = get_tf_string(current_user_tfvars, "ssh_key_name")
        if not region:
            region = quiet_command_output(["aws", "configure", "get", "region", "--profile", profile]) or "us-east-1"
        print_header("Shared Terraform Config")
        print("Using existing local Terraform and Ansible variable files because --yolo was set.")
        print(f"AWS region: {region}")
        if not ssh_key_name:
            raise SystemExit("ssh_key_name is missing from terraform/user.tfvars.")
    elif profile_is_fresh:
        region = get_tf_string(current_user_tfvars, "aws_region")
        ssh_key_name = get_tf_string(current_user_tfvars, "ssh_key_name")
        if not region:
            raise SystemExit("aws_region is missing from terraform/user.tfvars.")
        if not ssh_key_name:
            raise SystemExit("ssh_key_name is missing from terraform/user.tfvars.")
        print_header("Shared Terraform Config")
        print(f"Using user profile values from terraform/user.tfvars.")
        print(f"AWS region: {region}")
    else:
        profile, region, _name_prefix, _cidrs, ssh_key_name = configure_user_tfvars(profile)

    configure_ansible_env(profile, region)
    appliance_keys = selected_appliance_keys(args)
    if not args.yolo:
        configure_appliance_tfvars(appliance_keys)
    elif appliance_keys:
        configure_appliance_tfvars(appliance_keys)
    ensure_appliance_prep_tfvars(appliance_keys)
    ensure_appliance_collections(appliance_keys)

    configure_license_preflight(noninteractive=args.yolo or profile_action == "init")
    if not args.skip_terraform:
        configure_appliance_license_preflight(appliance_keys, noninteractive=args.yolo)
    if profile_action == "init":
        print_header("LiteLLM Credentials")
        print("Using LiteLLM credential values configured during profile initialization.")
    elif profile_action == "import":
        print_header("LiteLLM Credentials")
        print("Using LiteLLM credential values from the imported user profile.")
    else:
        configure_litellm_credentials(noninteractive=args.yolo)

    if not args.yolo:
        prompt_profile_review()
    if args.skip_terraform:
        print_header("Terraform")
        print("Skipped by --skip-terraform.")
    else:
        if not args.yolo and not prompt_yes_no("Ready to start Terraform execution?", True):
            raise SystemExit("Stopped before Terraform execution.")

        ecr_mode = "existing" if args.yolo else choose_ecr_mode()
        if args.yolo:
            print_header("ECR Mode")
            print("YOLO mode: importing missing existing ECR repositories, then applying.")
        run_terraform(ecr_mode, terraform_auto_approve, appliance_keys, profile, region, noninteractive_import=args.yolo)
    prompt_ec2_status(
        profile,
        region,
        wait_until_ready=True,
        delay_seconds=args.ec2_status_delay,
        max_attempts=args.ec2_status_retries,
    )
    show_appliance_ec2_statuses(profile, region, appliance_keys)

    print_header("Terraform Phase Complete")
    print("Generated files should now include:")
    print("- ansible/group_vars/terraform.generated.yml")
    print("- ansible/group_vars/ecr.generated.yml")
    print("- ansible/group_vars/ports.generated.yml")
    print("- ansible/inventory/aws.generated.ini")
    if "fortigate" in appliance_keys:
        print("- ansible/inventory/fortigate.generated.ini")
    if "fortiweb" in appliance_keys:
        print("- ansible/inventory/fortiweb.generated.ini")
        print("- ansible/group_vars/fortiweb.generated.yml")

    if args.skip_ansible:
        print("\nStopped before Ansible because --skip-ansible was set.")
        return

    run_ansible_flow(args, appliance_keys)

    print_header("Automated Quick Start Complete")
    print("Terraform and Ansible deployment steps completed.")


if __name__ == "__main__":
    main()
