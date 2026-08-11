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
    import scenario_local
except ModuleNotFoundError:
    from scripts import scenario_local


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_ARCHIVE = REPO_ROOT.parent / "user_profile.tgz"
PROFILE_VERSION = 1
MANIFEST_PATH = ".faig-user-profile.json"
SCENARIO_LOCAL_PATH = Path("chatbot/scenarios/local")
SCENARIO_STATE_PATH = SCENARIO_LOCAL_PATH / "installed-scenarios.json"
SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

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


def init_profile(*, force: bool, configure_aws: bool = True) -> None:
    copy_profile_examples(force=force)
    if configure_aws:
        configure_terraform_user_profile()
    else:
        print("Local profile initialization: skipped AWS/Terraform onboarding.")
    configure_ansible_user_profile()


def existing_profile_paths() -> list[Path]:
    return [path for path in ALLOWLIST if (REPO_ROOT / path).exists()]


def scenario_store() -> scenario_local.LocalScenarioStore:
    return scenario_local.LocalScenarioStore(
        repo_root=REPO_ROOT,
        local_root=REPO_ROOT / SCENARIO_LOCAL_PATH,
        raw_output_root=REPO_ROOT / "docs/raw-output/scenario-work-orders",
    )


def validate_scenario_id(scenario_id: str) -> str:
    if not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
        raise SystemExit(f"Refusing invalid installed scenario ID: {scenario_id}")
    return scenario_id


def installed_scenario_profile_paths() -> tuple[list[Path], list[str]]:
    store = scenario_store()
    try:
        state = store.load_state()
    except scenario_local.LocalScenarioError as exc:
        raise SystemExit(str(exc)) from exc
    entries = state["installed_scenarios"]
    if not entries:
        return [], []
    state_path = REPO_ROOT / SCENARIO_STATE_PATH
    if not state_path.is_file() or state_path.is_symlink():
        raise SystemExit(f"Installed scenario state must be a regular file: {state_path}")

    paths = [SCENARIO_STATE_PATH]
    scenario_ids: list[str] = []
    for entry in entries:
        scenario_id = validate_scenario_id(str(entry.get("scenario_id") or ""))
        package_root = store.scenario_path(scenario_id)
        try:
            package_paths = scenario_local.package_files(package_root)
        except scenario_local.LocalScenarioError as exc:
            raise SystemExit(str(exc)) from exc
        if not package_paths:
            raise SystemExit(f"Installed scenario package is empty: {package_root}")
        scenario_ids.append(scenario_id)
        paths.extend(path.relative_to(REPO_ROOT.resolve()) for path in package_paths)
    return sorted(paths), sorted(scenario_ids)


def export_profile_paths() -> tuple[list[Path], list[str]]:
    scenario_paths, scenario_ids = installed_scenario_profile_paths()
    return sorted(existing_profile_paths() + scenario_paths), scenario_ids


def export_profile(archive_path: Path) -> None:
    print_header("Export User Profile")
    missing = [path for path in REQUIRED_PROFILE_FILES if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit("Cannot export profile. Missing required files: " + ", ".join(path.as_posix() for path in missing))

    archive_path = archive_path.expanduser()
    if not archive_path.is_absolute():
        archive_path = (REPO_ROOT / archive_path).resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    files, scenario_ids = export_profile_paths()
    manifest = {
        "profile_version": PROFILE_VERSION,
        "created_at": int(time.time()),
        "files": [path.as_posix() for path in files],
        "installed_scenarios": scenario_ids,
    }
    for path in files:
        source = REPO_ROOT / path
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"Profile export accepts only regular files: {source}")

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
            source = REPO_ROOT / path
            archive.add(source, arcname=path.as_posix(), recursive=False)

    print(f"created: {archive_path}")
    print("included:")
    for path in files:
        print(f"- {path.as_posix()}")
    print("External files referenced by the profile were not embedded.")


def safe_member_path(member_name: str) -> Path:
    pure = PurePosixPath(member_name)
    if (
        not pure.parts
        or pure.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != member_name
    ):
        raise SystemExit(f"Refusing unsafe archive path: {member_name}")
    return Path(*pure.parts)


def classify_profile_member(member_path: Path) -> tuple[str, str]:
    if member_path in ALLOWLIST:
        return "config", ""
    if member_path == SCENARIO_STATE_PATH:
        return "scenario-state", ""
    parts = member_path.parts
    scenario_prefix = SCENARIO_LOCAL_PATH.parts
    if parts[: len(scenario_prefix)] != scenario_prefix:
        raise SystemExit(f"Refusing unexpected profile file: {member_path.as_posix()}")
    if len(parts) <= len(scenario_prefix) + 1:
        raise SystemExit(f"Refusing incomplete scenario package path: {member_path.as_posix()}")
    scenario_id = validate_scenario_id(parts[len(scenario_prefix)])
    if scenario_id in {"_backups", "_removed"}:
        raise SystemExit(f"Refusing archived scenario history: {member_path.as_posix()}")
    return "scenario-file", scenario_id


def read_profile_archive(archive_path: Path) -> tuple[dict, dict[Path, bytes]]:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise SystemExit("Profile archive contains duplicate member names.")
            manifest_members = [member for member in members if member.name == MANIFEST_PATH]
            if len(manifest_members) != 1:
                raise SystemExit(f"Profile archive must contain exactly one {MANIFEST_PATH}.")
            manifest_member = manifest_members[0]
            if not manifest_member.isfile() or manifest_member.issym() or manifest_member.islnk():
                raise SystemExit(f"Profile archive has non-regular {MANIFEST_PATH}.")
            manifest_file = archive.extractfile(manifest_member)
            if manifest_file is None:
                raise SystemExit(f"Profile archive has unreadable {MANIFEST_PATH}.")
            try:
                manifest = json.loads(manifest_file.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SystemExit(f"Profile archive has invalid {MANIFEST_PATH}: {exc}") from exc
            if not isinstance(manifest, dict):
                raise SystemExit(f"Profile archive {MANIFEST_PATH} must be a JSON object.")
            if manifest.get("profile_version") != PROFILE_VERSION:
                raise SystemExit(f"Unsupported profile version: {manifest.get('profile_version')}")
            manifest_files = manifest.get("files")
            if not isinstance(manifest_files, list) or not all(
                isinstance(path, str) for path in manifest_files
            ):
                raise SystemExit("Profile archive manifest files must be a list of paths.")
            if len(manifest_files) != len(set(manifest_files)):
                raise SystemExit("Profile archive manifest contains duplicate file paths.")

            file_data: dict[Path, bytes] = {}
            archive_file_names: list[str] = []
            for member in members:
                if member.name == MANIFEST_PATH:
                    continue
                member_path = safe_member_path(member.name)
                classify_profile_member(member_path)
                if member.isdir() or member.issym() or member.islnk() or not member.isfile():
                    raise SystemExit(f"Refusing non-regular profile entry: {member.name}")
                source = archive.extractfile(member)
                if source is None:
                    raise SystemExit(f"Could not read profile file: {member.name}")
                file_data[member_path] = source.read()
                archive_file_names.append(member_path.as_posix())

            if sorted(manifest_files) != sorted(archive_file_names):
                raise SystemExit("Profile archive members do not match the manifest file list.")
            return manifest, file_data
    except (OSError, tarfile.TarError) as exc:
        raise SystemExit(f"Unable to read profile archive {archive_path}: {exc}") from exc


def validate_archived_scenarios(manifest: dict, file_data: dict[Path, bytes]) -> dict:
    package_files: dict[str, list[Path]] = {}
    for member_path in file_data:
        member_type, scenario_id = classify_profile_member(member_path)
        if member_type == "scenario-file":
            package_files.setdefault(scenario_id, []).append(member_path)

    state_bytes = file_data.get(SCENARIO_STATE_PATH)
    if package_files and state_bytes is None:
        raise SystemExit("Scenario package files require installed-scenarios.json.")
    if state_bytes is None:
        if manifest.get("installed_scenarios") not in (None, []):
            raise SystemExit("Profile manifest lists scenarios without installed scenario state.")
        return scenario_local.empty_state()

    try:
        state = json.loads(state_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid {SCENARIO_STATE_PATH.as_posix()}: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit(f"{SCENARIO_STATE_PATH.as_posix()} must contain a JSON object.")
    try:
        scenario_store().validate_state(state)
    except scenario_local.LocalScenarioError as exc:
        raise SystemExit(str(exc)) from exc

    state_ids = [
        validate_scenario_id(str(entry.get("scenario_id") or ""))
        for entry in state["installed_scenarios"]
    ]
    manifest_ids = manifest.get("installed_scenarios", state_ids)
    if not isinstance(manifest_ids, list) or not all(
        isinstance(scenario_id, str) for scenario_id in manifest_ids
    ):
        raise SystemExit("Profile archive manifest installed_scenarios must be a list of IDs.")
    if sorted(manifest_ids) != sorted(state_ids):
        raise SystemExit("Profile archive scenario state does not match its manifest.")
    if set(package_files) != set(state_ids):
        raise SystemExit("Profile archive scenario packages do not match installed scenario state.")

    for scenario_id in state_ids:
        profile_path = SCENARIO_LOCAL_PATH / scenario_id / "profile.json"
        if profile_path not in file_data:
            raise SystemExit(f"Scenario archive is missing {profile_path.as_posix()}.")
        try:
            profile = json.loads(file_data[profile_path].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Invalid archived scenario profile {profile_path}: {exc}") from exc
        if not isinstance(profile, dict) or profile.get("schema_version") != 2:
            raise SystemExit(f"Archived scenario {scenario_id} must use schema version 2.")
        if profile.get("id") != scenario_id:
            raise SystemExit(f"Archived scenario profile ID does not match directory {scenario_id}.")
    return state


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    except OSError as exc:
        raise SystemExit(f"Unable to write {path}: {exc}") from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def import_scenario_packages(
    file_data: dict[Path, bytes],
    incoming_state: dict,
    *,
    yes: bool,
) -> list[Path]:
    incoming_entries = {
        str(entry["scenario_id"]): entry
        for entry in incoming_state["installed_scenarios"]
    }
    if not incoming_entries:
        return []

    store = scenario_store()
    try:
        current_state = store.load_state()
    except scenario_local.LocalScenarioError as exc:
        raise SystemExit(str(exc)) from exc
    current_entries = {
        str(entry["scenario_id"]): entry
        for entry in current_state["installed_scenarios"]
    }
    selected_ids: list[str] = []
    for scenario_id in sorted(incoming_entries):
        destination = store.scenario_path(scenario_id)
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise SystemExit(
                f"Refusing non-directory installed scenario destination: {destination}"
            )
        collision = scenario_id in current_entries or destination.exists()
        if collision and not yes and not prompt_yes_no(
            f"Overwrite installed scenario {scenario_id}?",
            False,
        ):
            print(f"kept installed scenario: {scenario_id}")
            continue
        selected_ids.append(scenario_id)
    if not selected_ids:
        return []

    if store.state_path.is_symlink():
        raise SystemExit(f"Refusing symlinked installed scenario state: {store.state_path}")
    scenario_parent = store.local_root.parent
    scenario_parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".user-profile-import-", dir=scenario_parent)
    )
    staged_root = staging_root / "staged"
    backup_root = staging_root / "backup"
    imported_paths: list[Path] = []
    backed_up_ids: list[str] = []
    placed_ids: list[str] = []
    old_state_bytes = store.state_path.read_bytes() if store.state_path.is_file() else None
    try:
        for scenario_id in selected_ids:
            staged_package = staged_root / scenario_id
            for member_path, content in file_data.items():
                member_type, member_scenario_id = classify_profile_member(member_path)
                if member_type != "scenario-file" or member_scenario_id != scenario_id:
                    continue
                relative_package_path = member_path.relative_to(
                    SCENARIO_LOCAL_PATH / scenario_id
                )
                staged_path = staged_package / relative_package_path
                atomic_write_bytes(staged_path, content)
                imported_paths.append(member_path)

        store.local_root.mkdir(parents=True, exist_ok=True)
        for scenario_id in selected_ids:
            destination = store.scenario_path(scenario_id)
            staged_package = staged_root / scenario_id
            if destination.exists():
                backup_destination = backup_root / scenario_id
                backup_destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, backup_destination)
                backed_up_ids.append(scenario_id)
            os.replace(staged_package, destination)
            placed_ids.append(scenario_id)

        merged_entries = [
            entry
            for scenario_id, entry in current_entries.items()
            if scenario_id not in selected_ids
        ] + [incoming_entries[scenario_id] for scenario_id in selected_ids]
        merged_state = {
            "schema_version": scenario_local.STATE_SCHEMA_VERSION,
            "installed_scenarios": merged_entries,
        }
        store.write_state(merged_state)
        imported_paths.append(SCENARIO_STATE_PATH)
    except (OSError, scenario_local.LocalScenarioError, SystemExit) as exc:
        for scenario_id in reversed(placed_ids):
            destination = store.scenario_path(scenario_id)
            if destination.exists():
                shutil.rmtree(destination)
        for scenario_id in reversed(backed_up_ids):
            destination = store.scenario_path(scenario_id)
            backup_destination = backup_root / scenario_id
            if backup_destination.exists():
                os.replace(backup_destination, destination)
        if old_state_bytes is None:
            if store.state_path.exists():
                store.state_path.unlink()
        else:
            atomic_write_bytes(store.state_path, old_state_bytes)
        if isinstance(exc, SystemExit):
            raise
        raise SystemExit(f"Unable to import scenario packages: {exc}") from exc
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    return imported_paths


def import_profile(archive_path: Path, *, yes: bool) -> None:
    print_header("Import User Profile")
    archive_path = archive_path.expanduser()
    if not archive_path.is_absolute():
        archive_path = (REPO_ROOT / archive_path).resolve()
    if not archive_path.is_file():
        raise SystemExit(f"Profile archive does not exist: {archive_path}")

    imported: list[Path] = []
    manifest, file_data = read_profile_archive(archive_path)
    incoming_state = validate_archived_scenarios(manifest, file_data)

    for member_path in sorted(file_data):
        member_type, _scenario_id = classify_profile_member(member_path)
        if member_type != "config":
            continue
        member_key = member_path.as_posix()
        destination = REPO_ROOT / member_path
        if destination.exists() and not yes and not prompt_yes_no(
            f"Overwrite {member_key}?",
            False,
        ):
            print(f"kept: {member_key}")
            continue
        atomic_write_bytes(destination, file_data[member_path])
        imported.append(member_path)

    imported.extend(
        import_scenario_packages(file_data, incoming_state, yes=yes)
    )

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
    _scenario_paths, scenario_ids = installed_scenario_profile_paths()
    if scenario_ids:
        print("Registered installed scenarios included by export:")
        for scenario_id in scenario_ids:
            print(f"- {scenario_id}")
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
    init_parser.add_argument(
        "--local",
        action="store_true",
        help="Prepare local-deployment operator files without AWS/Terraform onboarding.",
    )

    import_parser = subparsers.add_parser("import", help="Import a user profile .tgz archive.")
    import_parser.add_argument("path", nargs="?", default=str(DEFAULT_PROFILE_ARCHIVE), help="Profile archive path.")
    import_parser.add_argument(
        "--yes",
        action="store_true",
        help="Replace existing configuration files and colliding installed scenarios without prompting.",
    )

    export_parser = subparsers.add_parser("export", help="Export current user profile files to a .tgz archive.")
    export_parser.add_argument("path", nargs="?", default=str(DEFAULT_PROFILE_ARCHIVE), help="Profile archive path.")

    subparsers.add_parser("check", help="Verify required user profile files exist.")
    return parser.parse_args()


def main() -> None:
    os.chdir(REPO_ROOT)
    args = parse_args()
    if args.command == "init":
        init_profile(force=args.force, configure_aws=not args.local)
    elif args.command == "import":
        import_profile(Path(args.path), yes=args.yes)
    elif args.command == "export":
        export_profile(Path(args.path))
    elif args.command == "check":
        check_profile()


if __name__ == "__main__":
    main()
