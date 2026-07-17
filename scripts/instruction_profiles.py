#!/usr/bin/env python3
"""Manage local operator-owned instruction profile slots."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION_ROOT = REPO_ROOT / "chatbot" / "instructions"
EXAMPLES_ROOT = INSTRUCTION_ROOT / "examples"
LOCAL_ROOT = INSTRUCTION_ROOT / "local"
CATALOG_PATH = EXAMPLES_ROOT / "catalog.json"

FALLBACK_CATALOG = {
    "slots": {
        "demo-a": {
            "display_name": "Demo A",
            "description": "Primary backend LiteLLM demo instruction slot.",
            "default_example": "HR-bot.instructions.txt",
            "local_path": "demo-a/instructions.txt",
        },
        "demo-b": {
            "display_name": "Demo B",
            "description": "Secondary backend LiteLLM demo instruction slot.",
            "default_example": "fastfood-bot.instructions.txt",
            "local_path": "demo-b/instructions.txt",
        },
        "frontend": {
            "display_name": "Frontend",
            "description": "Optional browser-layer chatbot instruction slot.",
            "default_example": "chatbot-frontend.instructions.txt",
            "local_path": "frontend/instructions.txt",
        },
    },
    "aliases": {"default": "demo-a", "alternate": "demo-b", "demo_a": "demo-a", "demo_b": "demo-b"},
    "examples": {},
}


def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return FALLBACK_CATALOG
    with CATALOG_PATH.open("r", encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    catalog.setdefault("slots", {})
    catalog.setdefault("aliases", {})
    catalog.setdefault("examples", {})
    return catalog


CATALOG = load_catalog()


def print_header(message: str) -> None:
    print(f"\n== {message} ==")


def resolve_slot(name: str) -> str:
    aliases = CATALOG.get("aliases", {})
    resolved = aliases.get(name, name)
    return resolved


def slot_path(name: str) -> Path:
    slot_name = resolve_slot(name)
    slot = CATALOG.get("slots", {}).get(slot_name)
    if slot:
        return LOCAL_ROOT / slot["local_path"]
    return LOCAL_ROOT / slot_name / "instructions.txt"


def metadata_path_for_instruction(path: Path) -> Path:
    return path.parent / "metadata.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as json_file:
            data = json.load(json_file)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, indent=2, sort_keys=True)
        json_file.write("\n")


def example_files() -> list[Path]:
    if not EXAMPLES_ROOT.exists():
        return []
    return sorted(EXAMPLES_ROOT.glob("*.instructions.txt"))


def resolve_example(source: str | None, slot_name: str | None = None) -> Path:
    if not source:
        slot = CATALOG.get("slots", {}).get(resolve_slot(slot_name or "demo-a"), {})
        source = slot.get("default_example", "HR-bot.instructions.txt")

    source_path = Path(source)
    if source_path.exists():
        return source_path

    if source in CATALOG.get("examples", {}):
        return EXAMPLES_ROOT / source

    candidate = EXAMPLES_ROOT / source
    if candidate.exists():
        return candidate

    if not source.endswith(".instructions.txt"):
        candidate = EXAMPLES_ROOT / f"{source}.instructions.txt"
        if candidate.exists():
            return candidate

    normalized = source.lower()
    for path in example_files():
        if path.stem.lower() == normalized or path.name.lower() == normalized:
            return path

    raise SystemExit(f"Instruction example does not exist: {source}")


def example_metadata(path: Path) -> dict:
    return dict(CATALOG.get("examples", {}).get(path.name, {}))


def slot_metadata(slot: str) -> dict:
    slot_name = resolve_slot(slot)
    path = slot_path(slot_name)
    metadata = read_json(metadata_path_for_instruction(path))
    if metadata:
        return metadata
    slot_info = CATALOG.get("slots", {}).get(slot_name, {})
    return {
        "display_name": slot_info.get("display_name", slot_name),
        "description": slot_info.get("description", ""),
        "slot": slot_name,
        "status": "missing" if not path.exists() else "local",
    }


def build_local_metadata(*, slot: str, source: Path, source_type: str, base_metadata: dict | None = None) -> dict:
    metadata = dict(base_metadata or {})
    metadata.setdefault("display_name", metadata.get("display_name") or source.stem)
    metadata.setdefault("description", metadata.get("description", ""))
    metadata.update(
        {
            "slot": resolve_slot(slot),
            "source_type": source_type,
            "source": str(source.relative_to(REPO_ROOT)) if source.is_relative_to(REPO_ROOT) else str(source),
            "updated_at": int(time.time()),
        }
    )
    return metadata


def ensure_slot_metadata(slot: str) -> Path | None:
    slot_name = resolve_slot(slot)
    path = slot_path(slot_name)
    metadata_path = metadata_path_for_instruction(path)
    if not path.exists() or metadata_path.exists():
        return None
    slot_info = CATALOG.get("slots", {}).get(slot_name, {})
    write_json(
        metadata_path,
        {
            "display_name": slot_info.get("display_name", slot_name),
            "description": "Existing local instruction; source example unknown.",
            "slot": slot_name,
            "source_type": "local-existing",
            "source": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
            "updated_at": int(time.time()),
        },
    )
    return metadata_path


def known_slot_names() -> list[str]:
    names = set(CATALOG.get("slots", {}))
    aliases = set(CATALOG.get("aliases", {}))
    if LOCAL_ROOT.exists():
        for path in LOCAL_ROOT.iterdir():
            if path.name not in aliases and path.is_dir() and (path / "instructions.txt").exists():
                names.add(path.name)
    return sorted(names)


def local_instruction_entries(*, include_slots: bool = False) -> list[dict]:
    entries = []
    slot_dirs = {
        slot_path(slot).parent.resolve()
        for slot in CATALOG.get("slots", {})
    }
    aliases = set(CATALOG.get("aliases", {}))
    if not LOCAL_ROOT.exists():
        return entries
    for path in sorted(LOCAL_ROOT.iterdir()):
        instruction_path = path / "instructions.txt"
        if not path.is_dir() or not instruction_path.exists():
            continue
        if path.name in aliases:
            continue
        if not include_slots and path.resolve() in slot_dirs:
            continue
        metadata = read_json(metadata_path_for_instruction(instruction_path))
        entries.append({"name": path.name, "path": instruction_path, "metadata": metadata})
    return entries


def write_slot(slot: str, *, source: str | None = None, force: bool = False, link: bool = False) -> Path:
    slot_name = resolve_slot(slot)
    dest = slot_path(slot_name)
    if dest.exists() and not force:
        return dest

    src = resolve_example(source, slot_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()

    if link:
        dest.symlink_to(src.resolve())
    else:
        shutil.copy2(src, dest)
    write_json(
        metadata_path_for_instruction(dest),
        build_local_metadata(slot=slot_name, source=src, source_type="example", base_metadata=example_metadata(src)),
    )
    return dest


def install_local_slot(slot: str, source_path: Path, *, force: bool = False, link: bool = False) -> Path:
    slot_name = resolve_slot(slot)
    dest = slot_path(slot_name)
    if dest.exists() and not force:
        return dest
    if not source_path.exists():
        raise SystemExit(f"Local instruction file does not exist: {source_path}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    if link:
        dest.symlink_to(source_path.resolve())
    else:
        shutil.copy2(source_path, dest)
    source_metadata = read_json(metadata_path_for_instruction(source_path))
    write_json(
        metadata_path_for_instruction(dest),
        build_local_metadata(slot=slot_name, source=source_path, source_type="local", base_metadata=source_metadata),
    )
    return dest


def deploy_command_for_slot(slot: str) -> tuple[str, str]:
    slot_name = resolve_slot(slot)
    if slot_name == "frontend":
        return "chatbot frontend", "ansible-playbook ansible/playbooks/deploy_chatbots.yml"
    return "LLM", "ansible-playbook ansible/playbooks/deploy_litellm.yml"


def print_deploy_hint(instruction_label: str, slot: str, path: Path) -> None:
    target, command = deploy_command_for_slot(slot)
    print(f"prepared: {instruction_label} -> {path}")
    print(f"READY for install to {target}")
    print(f"run: '{command}'")


def cmd_init(args: argparse.Namespace) -> None:
    print_header("Initialize Instruction Slots")
    slots = [resolve_slot(args.slot)] if args.slot else sorted(CATALOG.get("slots", {}))
    for slot in slots:
        existed = slot_path(slot).exists()
        path = write_slot(slot, source=args.from_example, force=args.force, link=args.link)
        ensure_slot_metadata(slot)
        action = "linked" if args.link and (args.force or path.is_symlink()) else "ready"
        if args.force and not args.link:
            action = "wrote"
        print(f"{action}: {slot} -> {path}")
        if args.force or not existed:
            print_deploy_hint(slot, slot, path)


def cmd_activate(args: argparse.Namespace) -> None:
    print_header("Activate Instruction Example")
    existed = slot_path(args.slot).exists()
    path = write_slot(args.slot, source=args.from_example, force=args.force, link=args.link)
    action = "linked" if args.link else "copied"
    print(f"{action}: {args.from_example} -> {resolve_slot(args.slot)} -> {path}")
    if args.force or not existed:
        print_deploy_hint(args.from_example, args.slot, path)
    else:
        print("No slot change made because the target already exists. Use --force to replace it.")


def cmd_create(args: argparse.Namespace) -> None:
    print_header("Create Instruction Slot")
    existed = slot_path(args.slot).exists()
    path = write_slot(args.slot, source=args.from_example, force=args.force, link=args.link)
    print(f"ready: {resolve_slot(args.slot)} -> {path}")
    if args.force or not existed:
        print_deploy_hint(resolve_slot(args.slot), args.slot, path)


def cmd_list(_args: argparse.Namespace) -> None:
    print_header("Instruction Slots")
    slots = CATALOG.get("slots", {})
    for slot in known_slot_names():
        slot_meta = slots.get(slot, {})
        path = slot_path(slot)
        status = "local" if path.exists() else "example-only"
        default_example = slot_meta.get("default_example", "")
        description = slot_meta.get("description", "Custom local instruction slot.")
        print(f"- {slot}: {status}")
        print(f"  local: {path}")
        if default_example:
            print(f"  default example: {default_example}")
        print(f"  description: {description}")


def cmd_examples(_args: argparse.Namespace) -> None:
    print_header("Instruction Examples")
    metadata = CATALOG.get("examples", {})
    for path in example_files():
        info = metadata.get(path.name, {})
        display_name = info.get("display_name", path.stem)
        description = info.get("description", "")
        print(f"- {path.name}: {display_name}")
        if description:
            print(f"  description: {description}")


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


def prompt_index(prompt: str, count: int, *, allow_quit: bool = True) -> int | None:
    while True:
        choice = input(f"{prompt}: ").strip().lower()
        if allow_quit and choice in {"", "q", "quit", "exit"}:
            return None
        try:
            index = int(choice)
        except ValueError:
            print("Enter a number" + (" or q to quit." if allow_quit else "."))
            continue
        if 1 <= index <= count:
            return index - 1
        print(f"Choose a number from 1 to {count}.")


def print_metadata(metadata: dict, *, indent: str = "  ") -> None:
    display_name = metadata.get("display_name", "")
    description = metadata.get("description", "")
    source = metadata.get("source", "")
    if display_name:
        print(f"{indent}name: {display_name}")
    if description:
        print(f"{indent}description: {description}")
    if source:
        print(f"{indent}source: {source}")


def editable_metadata(metadata: dict) -> dict:
    updated = dict(metadata)
    if not prompt_yes_no("Edit local metadata before install?", False):
        return updated
    updated["display_name"] = prompt_text("Display name", str(updated.get("display_name", "")))
    updated["description"] = prompt_text("Description", str(updated.get("description", "")))
    return updated


def write_slot_with_metadata(slot: str, source: Path, metadata: dict, *, force: bool, link: bool, source_type: str) -> Path:
    if source_type == "local":
        path = install_local_slot(slot, source, force=force, link=link)
    else:
        path = write_slot(slot, source=str(source), force=force, link=link)
    merged = build_local_metadata(slot=slot, source=source, source_type=source_type, base_metadata=metadata)
    write_json(metadata_path_for_instruction(path), merged)
    return path


def wizard_current_slots() -> list[str]:
    slots = sorted(CATALOG.get("slots", {}))
    print_header("Current Instruction Slots")
    for index, slot in enumerate(slots, start=1):
        path = slot_path(slot)
        status = "installed" if path.exists() else "missing"
        print(f"{index}. {slot} ({status})")
        print(f"   path: {path}")
        print_metadata(slot_metadata(slot), indent="   ")
    return slots


def wizard_select_example() -> tuple[Path, dict] | None:
    examples = example_files()
    if not examples:
        print("No tracked instruction examples found.")
        return None
    print_header("Tracked Instruction Examples")
    for index, path in enumerate(examples, start=1):
        metadata = example_metadata(path)
        print(f"{index}. {path.name}")
        print_metadata(metadata, indent="   ")
    selected = prompt_index("Select example number, or q to quit", len(examples))
    if selected is None:
        return None
    source = examples[selected]
    return source, editable_metadata(example_metadata(source))


def wizard_select_local() -> tuple[Path, dict] | None:
    entries = local_instruction_entries(include_slots=False)
    if not entries:
        print("No unused local instruction files found under chatbot/instructions/local/.")
        print("Create one with: python3 scripts/instruction_profiles.py create my-profile --from HR-bot")
        return None
    print_header("Unused Local Instruction Files")
    for index, entry in enumerate(entries, start=1):
        print(f"{index}. {entry['name']}")
        print(f"   path: {entry['path']}")
        print_metadata(entry["metadata"], indent="   ")
    selected = prompt_index("Select local instruction number, or q to quit", len(entries))
    if selected is None:
        return None
    entry = entries[selected]
    return entry["path"], editable_metadata(entry["metadata"])


def run_wizard() -> None:
    print_header("Instruction Profile Wizard")
    slots = wizard_current_slots()
    print("q. Quit")
    selected = prompt_index("Select slot to change/reload, or q to quit", len(slots))
    if selected is None:
        print("No changes made.")
        return

    slot = slots[selected]
    print_header(f"Change {slot}")
    print("1. Fresh copy from tracked example")
    print("2. Install an unused local instruction")
    source_choice = prompt_index("Choose source, or q to quit", 2)
    if source_choice is None:
        print("No changes made.")
        return

    if source_choice == 0:
        selected_source = wizard_select_example()
        source_type = "example"
    else:
        selected_source = wizard_select_local()
        source_type = "local"
    if selected_source is None:
        print("No changes made.")
        return

    source, metadata = selected_source
    print_header("Confirm Install")
    print(f"target: {slot}")
    print(f"source: {source}")
    metadata_to_print = metadata if metadata else {"display_name": source.stem}
    print_metadata(metadata_to_print)
    link = prompt_yes_no("Link instead of copy?", False)
    if not prompt_yes_no("Install this instruction into the selected slot?", True):
        print("No changes made.")
        return
    path = write_slot_with_metadata(slot, source, metadata, force=True, link=link, source_type=source_type)
    print(f"installed: {slot} -> {path}")
    print_deploy_hint(source.name, slot, path)


def editor_command(path: Path) -> list[str]:
    configured = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if configured:
        return configured.split() + [str(path)]

    if platform.system() == "Darwin":
        return ["open", "-e", str(path)]
    if shutil.which("code"):
        return ["code", str(path)]
    if shutil.which("xdg-open"):
        return ["xdg-open", str(path)]
    if shutil.which("nano"):
        return ["nano", str(path)]
    if shutil.which("vi"):
        return ["vi", str(path)]

    raise SystemExit(f"No editor found. Open this file manually: {path}")


def cmd_edit(args: argparse.Namespace) -> None:
    path = write_slot(args.slot, source=args.from_example)
    print(f"opening: {path}")
    result = subprocess.run(editor_command(path), cwd=str(REPO_ROOT), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def validate_slot(name: str) -> tuple[bool, str]:
    path = slot_path(name)
    if not path.exists():
        return False, f"missing local file: {path}"
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return False, f"empty local file: {path}"
    return True, f"ok: {path}"


def cmd_validate(args: argparse.Namespace) -> None:
    print_header("Validate Instruction Slots")
    slots = [resolve_slot(args.slot)] if args.slot else known_slot_names()
    failed = False
    for slot in slots:
        ok, message = validate_slot(slot)
        print(f"- {slot}: {message}")
        failed = failed or not ok
    if failed:
        raise SystemExit(1)


def cmd_show(args: argparse.Namespace) -> None:
    path = slot_path(args.slot)
    if not path.exists():
        raise SystemExit(f"Missing local instruction slot: {path}")
    print(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage local instruction profile slots.")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Create missing local slots from default examples.")
    init_parser.add_argument("slot", nargs="?", help="Optional slot name. Defaults to all built-in slots.")
    init_parser.add_argument("--from", dest="from_example", help="Example filename/name to use for every initialized slot.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing local slot files.")
    init_parser.add_argument("--link", action="store_true", help="Symlink the slot to the selected example instead of copying.")

    activate_parser = subparsers.add_parser("activate", help="Copy or link an example into a slot.")
    activate_parser.add_argument("slot", help="Slot name, such as demo-a, demo-b, or frontend.")
    activate_parser.add_argument("--from", dest="from_example", required=True, help="Example filename/name to activate.")
    activate_parser.add_argument("--force", action="store_true", help="Overwrite the slot if it exists.")
    activate_parser.add_argument("--link", action="store_true", help="Symlink the slot to the selected example instead of copying.")

    create_parser = subparsers.add_parser("create", help="Create a named local slot.")
    create_parser.add_argument("slot", help="Slot name to create.")
    create_parser.add_argument("--from", dest="from_example", default=None, help="Example filename/name to copy.")
    create_parser.add_argument("--force", action="store_true", help="Overwrite the slot if it exists.")
    create_parser.add_argument("--link", action="store_true", help="Symlink the slot to the selected example instead of copying.")

    subparsers.add_parser("list", help="List local slots.")
    subparsers.add_parser("examples", help="List tracked example prompts.")

    edit_parser = subparsers.add_parser("edit", help="Open a local slot in a workstation editor.")
    edit_parser.add_argument("slot", help="Slot name to edit.")
    edit_parser.add_argument("--from", dest="from_example", help="Example filename/name when creating the slot.")

    validate_parser = subparsers.add_parser("validate", help="Validate local slots.")
    validate_parser.add_argument("slot", nargs="?", help="Optional slot name. Defaults to all known slots.")

    show_parser = subparsers.add_parser("show", help="Print a local slot.")
    show_parser.add_argument("slot", help="Slot name to show.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command is None:
        run_wizard()
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "activate":
        cmd_activate(args)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "examples":
        cmd_examples(args)
    elif args.command == "edit":
        cmd_edit(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "show":
        cmd_show(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
