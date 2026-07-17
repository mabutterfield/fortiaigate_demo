#!/usr/bin/env python3
"""User profile init/import/export for the FortiAIGate demo."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

try:
    import instruction_profiles
except ModuleNotFoundError:
    from scripts import instruction_profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_ARCHIVE = REPO_ROOT.parent / "user_profile.tgz"
PROFILE_VERSION = 1
MANIFEST_PATH = ".faig-user-profile.json"

REQUIRED_PROFILE_FILES = [
    Path("terraform/user.tfvars"),
    Path("ansible/group_vars/user.yml"),
]

PROFILE_FILE_PAIRS = [
    (Path("terraform/user.tfvars.example"), Path("terraform/user.tfvars")),
    (Path("ansible/group_vars/user.yml.example"), Path("ansible/group_vars/user.yml")),
]

ALLOWLIST = [
    Path("terraform/user.tfvars"),
    Path("terraform/aws-ecr/99-local.auto.tfvars"),
    Path("terraform/aws-prep/99-local.auto.tfvars"),
    Path("terraform/aws-ec2-k3s/99-local.auto.tfvars"),
    Path("terraform/aws-fortigate/99-local.auto.tfvars"),
    Path("terraform/aws-fortiweb/99-local.auto.tfvars"),
    Path("ansible/group_vars/user.yml"),
    Path("chatbot/instructions/local/demo-a/instructions.txt"),
    Path("chatbot/instructions/local/demo-b/instructions.txt"),
    Path("chatbot/instructions/local/frontend/instructions.txt"),
]

LEGACY_LOCAL_FILES = [
    Path("terraform/common.tfvars"),
    Path("ansible/group_vars/all.yml"),
    Path("ansible/group_vars/env.yml"),
    Path("ansible/group_vars/images.yml"),
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


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_command(argv: list[str], *, capture: bool = False, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
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


def command_output(argv: list[str]) -> str:
    result = run_command(argv, capture=True)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise SystemExit(f"Missing required command: {command}")


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


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def get_tf_string(content: str, key: str, default: str = "") -> str:
    matches = re.findall(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"', content)
    return matches[-1] if matches else default


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


def set_yaml_list_strings(content: str, key: str, values: list[str]) -> str:
    rendered = "\n".join(f"  - {value}" for value in values)
    replacement = f"{key}:\n{rendered}\n"
    span = yaml_block_span(content, key)
    if span is None:
        return content.rstrip() + f"\n{replacement}"
    return content[: span[0]] + replacement + content[span[1] :]


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
        key, tag_value = entry.split("=", 1)
        key = key.strip()
        tag_value = tag_value.strip()
        if not key:
            raise SystemExit("Tag keys cannot be empty.")
        tags[key] = tag_value
    return tags


def render_tags_prompt_default(tags: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(tags.items()))


def normalize_cidr_value(value: str) -> str:
    if "/" not in value:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ValueError(f"Invalid CIDR value: {value}. Error: {error}") from error
        return f"{address}/{32 if address.version == 4 else 128}"
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError as error:
        raise ValueError(f"Invalid CIDR value: {value}. Error: {error}") from error


def prompt_cidr_list(default_values: list[str]) -> list[str]:
    default = ", ".join(default_values)
    while True:
        value = prompt_text("Trusted source CIDR list, comma-separated", default)
        cidrs = [entry.strip() for entry in value.split(",") if entry.strip()]
        if not cidrs:
            print("At least one trusted source CIDR is required.")
            continue
        try:
            return [normalize_cidr_value(cidr) for cidr in cidrs]
        except ValueError as error:
            print(error)


def list_aws_profiles() -> list[str]:
    output = command_output(["aws", "configure", "list-profiles"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def aws_profile_uses_sso(profile: str) -> bool:
    sso_keys = ["sso_session", "sso_start_url", "sso_account_id", "sso_role_name"]
    return any(command_output(["aws", "configure", "get", key, "--profile", profile]) for key in sso_keys)


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
    result = run_command(["aws", "sts", "get-caller-identity", "--profile", profile])
    if result.returncode == 0:
        return
    print("AWS caller identity check failed.")
    method = choose_aws_login_method(profile)
    if method == "skip":
        print("Continuing without AWS login. EC2 key pair discovery may be empty.")
        return

    if method == "sso":
        argv = ["aws", "sso", "login", "--profile", profile]
        if prompt_yes_no("Use device-code flow for aws sso login?", False):
            argv.append("--use-device-code")
    else:
        argv = ["aws", "login", "--profile", profile]
        if prompt_yes_no("Pass --use-device-code to aws login?", False):
            argv.append("--use-device-code")

    run_command(argv, check=True)
    run_command(["aws", "sts", "get-caller-identity", "--profile", profile], check=True)


def choose_aws_profile(default_profile: str) -> str:
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
        ]
    )
    return [key.strip() for key in re.split(r"\s+", output) if key.strip()]


def choose_ec2_key_pair(profile: str, region: str, default_key: str) -> str:
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
        if path.name.endswith(".pub") or path.name.startswith("known_hosts"):
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
    else:
        print("No likely private keys were found in ~/.ssh.")

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


def copy_profile_examples(*, force: bool) -> None:
    print_header("Profile Files")
    for source_rel, dest_rel in PROFILE_FILE_PAIRS:
        source = REPO_ROOT / source_rel
        dest = REPO_ROOT / dest_rel
        if dest.exists() and not force:
            print(f"exists: {dest_rel.as_posix()}")
            continue
        if dest.exists() and force and not prompt_yes_no(f"Overwrite {dest_rel.as_posix()}?", False):
            print(f"kept: {dest_rel.as_posix()}")
            continue
        shutil.copyfile(source, dest)
        print(f"created: {dest_rel.as_posix()} from {source_rel.as_posix()}")


def configure_terraform_user_profile() -> None:
    require_command("aws")
    path = REPO_ROOT / "terraform/user.tfvars"
    content = read_file(path)

    current_profile = get_tf_string(content, "aws_profile")
    profile = choose_aws_profile(current_profile)
    profile_region = command_output(["aws", "configure", "get", "region", "--profile", profile])
    current_region = get_tf_string(content, "aws_region", "us-east-1")
    region = prompt_text("AWS region", profile_region or current_region or "us-east-1")
    name_prefix = prompt_text("Deployment name prefix", get_tf_string(content, "name_prefix", "fortiaigate-demo"))
    ensure_aws_login(profile)
    key_name = choose_ec2_key_pair(profile, region, get_tf_string(content, "ssh_key_name"))
    private_key = choose_local_ssh_private_key(get_tf_string(content, "ssh_private_key_file"), key_name)
    cidrs = prompt_cidr_list(get_tf_list_strings(content, "allowed_ingress_cidr"))
    tags = parse_tags_text(prompt_text("Optional Terraform tags, comma-separated key=value", render_tags_prompt_default(get_tf_map_strings(content, "tags"))))

    content = set_tf_string(content, "aws_profile", profile)
    content = set_tf_string(content, "aws_region", region)
    content = set_tf_string(content, "name_prefix", name_prefix)
    content = set_tf_string(content, "ssh_key_name", key_name)
    content = set_tf_string(content, "ssh_private_key_file", private_key)
    content = set_tf_list_strings(content, "allowed_ingress_cidr", cidrs)
    content = set_tf_map_strings(content, "tags", tags)
    write_file(path, content)
    print(f"updated: {rel(path)}")


def configure_ansible_user_profile() -> None:
    print_header("Ansible User Profile")
    path = REPO_ROOT / "ansible/group_vars/user.yml"
    content = read_file(path)

    raw_source_dir = get_yaml_scalar(content, "license_source_dir", "{{ faig_workspace_root }}/licenses")
    source_dir = resolve_ansible_path(raw_source_dir)
    selected_source_dir = prompt_text("FortiAIGate license source directory", str(source_dir))
    source_dir = Path(selected_source_dir).expanduser()
    if not source_dir.is_absolute():
        source_dir = (REPO_ROOT / source_dir).resolve()

    existing_licenses = get_yaml_list_strings(content, "fortiaigate_license_files")
    selected_license = choose_license_file(source_dir, existing_licenses[0] if existing_licenses else "")
    content = set_yaml_scalar(content, "license_source_dir", render_license_source_dir_for_yaml(source_dir))
    content = set_yaml_list_strings(content, "fortiaigate_license_files", [selected_license])

    credential_fields = [
        ("litellm_master_key", "LiteLLM API/master key"),
        ("litellm_ui_username", "LiteLLM admin username"),
        ("litellm_ui_password", "LiteLLM admin password"),
        ("openwebui_enabled", "Enable OpenWebUI true/false"),
    ]
    print("Press Enter to keep the current value.")
    for key, label in credential_fields:
        current_value = get_yaml_scalar(content, key)
        value = prompt_text(label, current_value)
        content = set_yaml_scalar(content, key, value)

    write_file(path, content)
    print(f"updated: {rel(path)}")


def ensure_instruction_slots() -> list[Path]:
    print_header("Instruction Profiles")
    created = []
    for slot in sorted(instruction_profiles.CATALOG.get("slots", {})):
        path = instruction_profiles.slot_path(slot)
        if path.exists():
            metadata_path = instruction_profiles.ensure_slot_metadata(slot)
            print(f"exists: {rel(path)}")
            if metadata_path:
                print(f"created: {rel(metadata_path)}")
            continue
        instruction_profiles.write_slot(slot, force=False)
        created.append(path)
        print(f"created: {rel(path)}")
        instruction_profiles.print_deploy_hint(slot, slot, path)
    return created


def init_profile(*, force: bool) -> None:
    copy_profile_examples(force=force)
    ensure_instruction_slots()
    configure_terraform_user_profile()
    configure_ansible_user_profile()


def existing_profile_paths() -> list[Path]:
    return [path for path in ALLOWLIST if (REPO_ROOT / path).exists()]


def export_profile(archive_path: Path) -> None:
    print_header("Export User Profile")
    missing = [path for path in REQUIRED_PROFILE_FILES if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit("Cannot export profile. Missing required files: " + ", ".join(path.as_posix() for path in missing))

    archive_path = archive_path.expanduser()
    if not archive_path.is_absolute():
        archive_path = (REPO_ROOT / archive_path).resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    files = existing_profile_paths()
    manifest = {
        "profile_version": PROFILE_VERSION,
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
    print("included:")
    for path in files:
        print(f"- {path.as_posix()}")
    print("External files referenced by the profile were not embedded.")


def safe_member_path(member_name: str) -> Path:
    pure = PurePosixPath(member_name)
    if pure.is_absolute() or ".." in pure.parts:
        raise SystemExit(f"Refusing unsafe archive path: {member_name}")
    return Path(*pure.parts)


def import_profile(archive_path: Path, *, yes: bool) -> None:
    print_header("Import User Profile")
    archive_path = archive_path.expanduser()
    if not archive_path.is_absolute():
        archive_path = (REPO_ROOT / archive_path).resolve()
    if not archive_path.is_file():
        raise SystemExit(f"Profile archive does not exist: {archive_path}")

    allowlist = {path.as_posix(): path for path in ALLOWLIST}
    imported: list[Path] = []

    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        if MANIFEST_PATH not in names:
            raise SystemExit(f"Profile archive is missing {MANIFEST_PATH}.")
        manifest_file = archive.extractfile(MANIFEST_PATH)
        if manifest_file is None:
            raise SystemExit(f"Profile archive has unreadable {MANIFEST_PATH}.")
        manifest = json.loads(manifest_file.read().decode("utf-8"))
        if manifest.get("profile_version") != PROFILE_VERSION:
            raise SystemExit(f"Unsupported profile version: {manifest.get('profile_version')}")

        for member in members:
            if member.name == MANIFEST_PATH:
                continue
            member_path = safe_member_path(member.name)
            member_key = member_path.as_posix()
            if member_key not in allowlist:
                raise SystemExit(f"Refusing unexpected profile file: {member.name}")
            if member.isdir() or member.issym() or member.islnk() or not member.isfile():
                raise SystemExit(f"Refusing non-regular profile entry: {member.name}")

            dest = REPO_ROOT / member_path
            if dest.exists() and not yes and not prompt_yes_no(f"Overwrite {member_key}?", False):
                print(f"kept: {member_key}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise SystemExit(f"Could not read profile file: {member.name}")
            dest.write_bytes(source.read())
            imported.append(member_path)

    print(f"imported from: {archive_path}")
    for path in imported:
        print(f"- {path.as_posix()}")


def check_profile() -> None:
    print_header("User Profile Check")
    missing = [path for path in REQUIRED_PROFILE_FILES if not (REPO_ROOT / path).exists()]
    if missing:
        print("Missing required user profile files:")
        for path in missing:
            print(f"- {path.as_posix()}")
        raise SystemExit(1)
    print("Required user profile files exist.")
    for path in existing_profile_paths():
        print(f"- {path.as_posix()}")
    warn_legacy_files()


def find_legacy_files() -> list[Path]:
    files = [path for path in LEGACY_LOCAL_FILES if (REPO_ROOT / path).exists()]
    terraform_root = REPO_ROOT / "terraform"
    if terraform_root.exists():
        for path in terraform_root.glob("*/terraform.tfvars"):
            if path.is_file() or path.is_symlink():
                files.append(path.relative_to(REPO_ROOT))
    return sorted(set(files))


def warn_legacy_files() -> None:
    legacy_files = find_legacy_files()
    if not legacy_files:
        return
    print_header("Legacy Local Config Warning")
    print("These legacy local files still exist and may be loaded before the new profile files:")
    for path in legacy_files:
        print(f"- {path.as_posix()}")
    print("Move any needed user-owned values into terraform/user.tfvars, ansible/group_vars/user.yml,")
    print("or module 99-local.auto.tfvars files, then remove the legacy files.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage FortiAIGate local user profiles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create and configure local user profile files.")
    init_parser.add_argument("--force", action="store_true", help="Offer to overwrite existing user profile files from examples.")

    import_parser = subparsers.add_parser("import", help="Import a user profile .tgz archive.")
    import_parser.add_argument("path", nargs="?", default=str(DEFAULT_PROFILE_ARCHIVE), help="Profile archive path.")
    import_parser.add_argument("--yes", action="store_true", help="Overwrite existing allowlisted profile files without prompting.")

    export_parser = subparsers.add_parser("export", help="Export current user profile files to a .tgz archive.")
    export_parser.add_argument("path", nargs="?", default=str(DEFAULT_PROFILE_ARCHIVE), help="Profile archive path.")

    subparsers.add_parser("check", help="Verify required user profile files exist.")
    return parser.parse_args()


def main() -> None:
    os.chdir(REPO_ROOT)
    args = parse_args()
    if args.command == "init":
        init_profile(force=args.force)
    elif args.command == "import":
        import_profile(Path(args.path), yes=args.yes)
    elif args.command == "export":
        export_profile(Path(args.path))
    elif args.command == "check":
        check_profile()


if __name__ == "__main__":
    main()
