#!/usr/bin/env python3
"""Migrate local v0.3 Terraform config defaults for the v0.4 appliance baseline."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

COMMON_TFVARS = REPO_ROOT / "terraform/common.tfvars"
COMMON_EXAMPLE = REPO_ROOT / "terraform/common.tfvars.example"
AWS_PREP_TFVARS = REPO_ROOT / "terraform/aws-prep/terraform.tfvars"
AWS_EC2_K3S_TFVARS = REPO_ROOT / "terraform/aws-ec2-k3s/terraform.tfvars"
ANSIBLE_USER_EXAMPLE = REPO_ROOT / "ansible/group_vars/user.yml.example"
ANSIBLE_USER_YML = REPO_ROOT / "ansible/group_vars/user.yml"
ANSIBLE_ENV_YML = REPO_ROOT / "ansible/group_vars/env.yml"
ANSIBLE_ALL_YML = REPO_ROOT / "ansible/group_vars/all.yml"

APPLIANCE_PAIRS = [
    (
        "fortigate",
        REPO_ROOT / "terraform/aws-fortigate/terraform.tfvars.example",
        REPO_ROOT / "terraform/aws-fortigate/terraform.tfvars",
    ),
    (
        "fortiweb",
        REPO_ROOT / "terraform/aws-fortiweb/terraform.tfvars.example",
        REPO_ROOT / "terraform/aws-fortiweb/terraform.tfvars",
    ),
]

SSH_KEY_NAME_LEGACY_TARGETS = [
    REPO_ROOT / "terraform/aws-ec2-k3s/terraform.tfvars",
    REPO_ROOT / "terraform/aws-fortigate/terraform.tfvars",
    REPO_ROOT / "terraform/aws-fortiweb/terraform.tfvars",
]

ANSIBLE_ENV_USER_KEYS = [
    "faig_workspace_root",
]

ANSIBLE_ALL_USER_KEYS = [
    "license_source_dir",
    "fortiaigate_license_files",
    "fortiaigate_licenses",
    "litellm_master_key",
    "litellm_ui_username",
    "litellm_ui_password",
    "direct_model_provider",
    "direct_model_bedrock_model",
    "direct_model_bedrock_region",
    "ollama_base_url",
    "ollama_model",
    "openwebui_enabled",
    "fortiaigate_ssl_cert_path",
    "fortiaigate_ssl_key_path",
    "chatbot_frontend_system_prompt_source_path",
    "demo_https_gateway_cert_local_path",
    "demo_https_gateway_key_local_path",
]


@dataclass
class PendingWrite:
    path: Path
    before: str
    after: str
    action: str


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def get_hcl_string(content: str, key: str) -> str:
    match = re.search(rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"([^"]*)"', content)
    return match.group(1) if match else ""


def set_hcl_string(content: str, key: str, value: str) -> str:
    replacement = f'{key} = "{value}"'
    pattern = rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"[^"]*"'
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def get_hcl_bool(content: str, key: str) -> bool | None:
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(true|false)\b", content)
    if not match:
        return None
    return match.group(1) == "true"


def set_hcl_bool(content: str, key: str, value: bool) -> str:
    replacement = f"{key} = {str(value).lower()}"
    pattern = rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(true|false)\b"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content, count=1)
    return content.rstrip() + f"\n{replacement}\n"


def set_hcl_object_bool(content: str, object_key: str, item_key: str, value: bool) -> str:
    value_text = str(value).lower()
    pattern = rf"(?ms)^([ \t]*{re.escape(object_key)}[ \t]*=[ \t]*\{{\n)(.*?)(^[ \t]*\}})"
    match = re.search(pattern, content)
    if not match:
        block = f"{object_key} = {{\n  {item_key} = {value_text}\n}}\n"
        return content.rstrip() + f"\n{block}"

    prefix, body, suffix = match.group(1), match.group(2), match.group(3)
    item_pattern = rf"(?m)^([ \t]*{re.escape(item_key)}[ \t]*=[ \t]*)(true|false)\b"
    if re.search(item_pattern, body):
        updated_body = re.sub(item_pattern, rf"\g<1>{value_text}", body, count=1)
    else:
        updated_body = body
        if updated_body and not updated_body.endswith("\n"):
            updated_body += "\n"
        updated_body += f"  {item_key} = {value_text}\n"
    return content[: match.start()] + prefix + updated_body + suffix + content[match.end() :]


def yaml_top_level_blocks(content: str) -> dict[str, str]:
    lines = content.splitlines(keepends=True)
    indexes: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
        if match:
            indexes.append((index, match.group(1)))

    blocks: dict[str, str] = {}
    for position, (start, key) in enumerate(indexes):
        end = indexes[position + 1][0] if position + 1 < len(indexes) else len(lines)
        blocks[key] = "".join(lines[start:end])
    return blocks


def replace_or_append_yaml_block(content: str, key: str, block: str) -> str:
    blocks = yaml_top_level_blocks(content)
    if key not in blocks:
        separator = "\n" if content and not content.endswith("\n") else ""
        return content.rstrip() + separator + "\n" + block.rstrip() + "\n"

    old = blocks[key]
    return content.replace(old, block if block.endswith("\n") else block + "\n", 1)


def comment_legacy_ssh_key_name(content: str) -> str:
    return re.sub(
        r'(?m)^([ \t]*)ssh_key_name[ \t]*=[ \t]*"([^"]*)"',
        r'\1# migrated to terraform/common.tfvars: ssh_key_name = "\2"',
        content,
    )


def queue_write(writes: list[PendingWrite], path: Path, before: str, after: str, action: str) -> None:
    if before != after:
        writes.append(PendingWrite(path=path, before=before, after=after, action=action))


def ensure_file_from_example(writes: list[PendingWrite], example: Path, target: Path, action: str) -> None:
    if target.exists():
        return
    if not example.exists():
        raise SystemExit(f"Cannot create {relative_path(target)}; missing {relative_path(example)}.")
    queue_write(writes, target, "", read_text(example), action)


def migrate_ssh_key_name(writes: list[PendingWrite]) -> None:
    if not COMMON_TFVARS.exists():
        ensure_file_from_example(writes, COMMON_EXAMPLE, COMMON_TFVARS, "create common tfvars")

    common_content = read_text(COMMON_TFVARS) if COMMON_TFVARS.exists() else read_text(COMMON_EXAMPLE)
    common_ssh_key_name = get_hcl_string(common_content, "ssh_key_name")

    legacy_value = ""
    legacy_source = None
    legacy_paths_with_key: list[Path] = []
    for target_path in SSH_KEY_NAME_LEGACY_TARGETS:
        if not target_path.exists():
            continue
        value = get_hcl_string(read_text(target_path), "ssh_key_name")
        if value:
            legacy_paths_with_key.append(target_path)
        if value and not legacy_value:
            legacy_value = value
            legacy_source = target_path

    if common_ssh_key_name:
        legacy_value = common_ssh_key_name

    if not legacy_value:
        return

    if not common_ssh_key_name:
        updated_common = set_hcl_string(common_content, "ssh_key_name", legacy_value)
        source_text = f" from {relative_path(legacy_source)}" if legacy_source else ""
        queue_write(writes, COMMON_TFVARS, common_content, updated_common, f"migrate ssh_key_name{source_text}")

    for legacy_path in legacy_paths_with_key:
        legacy_content = read_text(legacy_path)
        updated_legacy = comment_legacy_ssh_key_name(legacy_content)
        queue_write(writes, legacy_path, legacy_content, updated_legacy, "comment legacy ssh_key_name")


def create_appliance_tfvars(writes: list[PendingWrite]) -> None:
    for _name, example, target in APPLIANCE_PAIRS:
        ensure_file_from_example(writes, example, target, "create appliance tfvars")


def enable_appliance_tfvars(writes: list[PendingWrite]) -> None:
    for name, _example, target in APPLIANCE_PAIRS:
        if target.exists():
            content = read_text(target)
        else:
            pending = next((write for write in writes if write.path == target), None)
            if pending is None:
                continue
            content = pending.after

        enabled_key = f"{name}_enabled"
        updated = set_hcl_bool(content, enabled_key, True)

        pending = next((write for write in writes if write.path == target), None)
        if pending:
            pending.after = updated
        else:
            queue_write(writes, target, content, updated, f"set {enabled_key}=true")


def enable_prep_appliance_defaults(writes: list[PendingWrite]) -> None:
    if not AWS_PREP_TFVARS.exists():
        return

    content = read_text(AWS_PREP_TFVARS)
    updated = content
    updated = set_hcl_object_bool(updated, "allocate_eips", "fortigate", True)
    updated = set_hcl_object_bool(updated, "allocate_eips", "fortiweb", True)
    updated = set_hcl_bool(updated, "fortiweb_enabled", True)
    queue_write(writes, AWS_PREP_TFVARS, content, updated, "enable appliance prep defaults")


def migrate_ingress_routing_strategy(writes: list[PendingWrite]) -> None:
    if not AWS_EC2_K3S_TFVARS.exists():
        return

    content = read_text(AWS_EC2_K3S_TFVARS)
    if get_hcl_string(content, "ingress_routing_strategy") != "path_based":
        return

    updated = set_hcl_string(content, "ingress_routing_strategy", "port_based")
    queue_write(writes, AWS_EC2_K3S_TFVARS, content, updated, "set ingress_routing_strategy=port_based")


def migrate_ansible_user_yml(writes: list[PendingWrite]) -> None:
    if ANSIBLE_USER_YML.exists():
        before = read_text(ANSIBLE_USER_YML)
        user_content = read_text(ANSIBLE_USER_YML)
    else:
        if not ANSIBLE_USER_EXAMPLE.exists():
            raise SystemExit(f"Cannot create {relative_path(ANSIBLE_USER_YML)}; missing {relative_path(ANSIBLE_USER_EXAMPLE)}.")
        before = ""
        user_content = read_text(ANSIBLE_USER_EXAMPLE)

    updated = user_content
    for source_path, keys in (
        (ANSIBLE_ENV_YML, ANSIBLE_ENV_USER_KEYS),
        (ANSIBLE_ALL_YML, ANSIBLE_ALL_USER_KEYS),
    ):
        if not source_path.exists():
            continue
        source_blocks = yaml_top_level_blocks(read_text(source_path))
        for key in keys:
            if key in source_blocks:
                updated = replace_or_append_yaml_block(updated, key, source_blocks[key])

    queue_write(writes, ANSIBLE_USER_YML, before, updated, "migrate Ansible user vars")


def render_diff(write: PendingWrite) -> str:
    diff = difflib.unified_diff(
        write.before.splitlines(keepends=True),
        write.after.splitlines(keepends=True),
        fromfile=relative_path(write.path),
        tofile=relative_path(write.path) + " (upgraded)",
    )
    return "".join(diff)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upgrade local v0.3 ignored Terraform config files for the v0.4 FortiGate/FortiWeb baseline."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report whether local config still needs the v0.3-to-v0.4 migration.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diffs without writing local config files.",
    )
    parser.add_argument(
        "--skip-appliances",
        action="store_true",
        help="Only migrate shared variable moves; do not create/enable FortiGate/FortiWeb local tfvars or prep defaults.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    writes: list[PendingWrite] = []

    migrate_ssh_key_name(writes)
    migrate_ingress_routing_strategy(writes)
    migrate_ansible_user_yml(writes)
    if not args.skip_appliances:
        create_appliance_tfvars(writes)
        enable_appliance_tfvars(writes)
        enable_prep_appliance_defaults(writes)

    if not writes:
        print("No v0.3-to-v0.4 local config migration changes are needed.")
        return

    for write in writes:
        print(f"{write.action}: {relative_path(write.path)}")

    if args.check:
        raise SystemExit(1)

    if args.dry_run:
        for write in writes:
            sys.stdout.write(render_diff(write))
        return

    for write in writes:
        write.path.parent.mkdir(parents=True, exist_ok=True)
        write.path.write_text(write.after, encoding="utf-8")
        print(f"updated: {relative_path(write.path)}")


if __name__ == "__main__":
    main()
