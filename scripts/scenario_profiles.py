#!/usr/bin/env python3
"""Install repeatable demo scenario profiles into local instruction slots."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

try:
    import instruction_profiles
except ModuleNotFoundError:
    from scripts import instruction_profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = REPO_ROOT / "chatbot" / "scenarios"
EXAMPLES_ROOT = SCENARIO_ROOT / "examples"
CATALOG_PATH = EXAMPLES_ROOT / "catalog.json"
MCP_SERVER_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "server.py"


def print_header(message: str) -> None:
    print(f"\n== {message} ==")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return data


def catalog() -> dict:
    if not CATALOG_PATH.exists():
        return {"scenarios": {}}
    data = read_json(CATALOG_PATH)
    data.setdefault("scenarios", {})
    return data


def scenario_ids() -> list[str]:
    return sorted(catalog().get("scenarios", {}))


def scenario_path(scenario_id: str) -> Path:
    scenarios = catalog().get("scenarios", {})
    if scenario_id not in scenarios:
        raise SystemExit(f"Unknown scenario: {scenario_id}")
    return EXAMPLES_ROOT / scenarios[scenario_id]["path"]


def load_scenario(scenario_id: str) -> tuple[Path, dict]:
    path = scenario_path(scenario_id)
    profile = read_json(path)
    profile.setdefault("id", scenario_id)
    return path, profile


def instruction_path(profile_path: Path, profile: dict) -> Path:
    path = profile_path.parent / profile.get("instruction_file", "instructions.txt")
    if not path.exists():
        raise SystemExit(f"Missing scenario instruction file: {path}")
    return path


def print_list() -> None:
    print_header("Scenario Profiles")
    scenarios = catalog().get("scenarios", {})
    for scenario_id in scenario_ids():
        entry = scenarios[scenario_id]
        profile_path, profile = load_scenario(scenario_id)
        print(f"- {scenario_id}: {entry.get('display_name', profile.get('display_name', scenario_id))}")
        print(f"  path: {profile_path.relative_to(REPO_ROOT)}")
        description = profile.get("description", "")
        if description:
            print(f"  description: {description}")


def print_scenario(profile_path: Path, profile: dict) -> None:
    print_header(profile.get("display_name", profile.get("id", "Scenario")))
    print(f"id: {profile.get('id')}")
    print(f"description: {profile.get('description', '')}")
    print(f"instructions: {instruction_path(profile_path, profile).relative_to(REPO_ROOT)}")

    mcp = profile.get("mcp", {})
    tools = mcp.get("required_tools", [])
    if tools:
        print("required MCP tools:")
        for tool in tools:
            print(f"- {tool}")

    prompts = profile.get("clean_prompts", [])
    if prompts:
        print("clean prompts:")
        for prompt in prompts:
            print(f"- {prompt}")

    attacks = profile.get("attack_prompts", [])
    if attacks:
        print("attack prompts:")
        for prompt in attacks:
            print(f"- {prompt}")

    trace = profile.get("expected_trace", [])
    if trace:
        print("expected trace:")
        for item in trace:
            print(f"- {item}")


def install_scenario(scenario_id: str, *, slot: str | None, force: bool, link: bool) -> Path:
    profile_path, profile = load_scenario(scenario_id)
    if not slot:
        raise SystemExit("Choose the target instruction slot with --slot, for example: --slot demo-b")
    target_slot = slot
    source = instruction_path(profile_path, profile)
    destination = instruction_profiles.slot_path(target_slot)
    if destination.exists() and not force:
        raise SystemExit(f"Target slot already exists: {destination}. Use --force to replace it.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    if link:
        destination.symlink_to(source.resolve())
    else:
        shutil.copy2(source, destination)

    metadata = {
        "display_name": profile.get("display_name", scenario_id),
        "description": profile.get("description", ""),
        "slot": instruction_profiles.resolve_slot(target_slot),
        "source_type": "scenario",
        "scenario_id": scenario_id,
        "source": str(source.relative_to(REPO_ROOT)),
        "required_tools": profile.get("mcp", {}).get("required_tools", []),
        "updated_at": int(time.time()),
    }
    instruction_profiles.write_json(instruction_profiles.metadata_path_for_instruction(destination), metadata)

    print(f"installed: {scenario_id} -> {instruction_profiles.resolve_slot(target_slot)} -> {destination}")
    instruction_profiles.print_deploy_hint(scenario_id, target_slot, destination)
    return destination


def shared_mcp_tool_names() -> set[str]:
    spec = importlib.util.spec_from_file_location("faig_mcp_server", MCP_SERVER_PATH)
    if not spec or not spec.loader:
        raise ValueError(f"Unable to load MCP server module: {MCP_SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = set()
    for tool in getattr(module, "TOOLS", []):
        function = tool.get("function", {})
        if "name" in function:
            names.add(function["name"])
    return names


def validate_scenarios() -> None:
    print_header("Validate Scenario Profiles")
    failed = False
    available_tools = shared_mcp_tool_names()
    for scenario_id in scenario_ids():
        try:
            profile_path, profile = load_scenario(scenario_id)
            instruction = instruction_path(profile_path, profile)
            if not instruction.read_text(encoding="utf-8").strip():
                raise ValueError("instruction file is empty")
            required_tools = profile.get("mcp", {}).get("required_tools", [])
            if not required_tools:
                raise ValueError("required MCP tools are missing")
            missing_tools = sorted(set(required_tools) - available_tools)
            if missing_tools:
                raise ValueError(f"required MCP tools are not in shared MCP server: {', '.join(missing_tools)}")
            if not profile.get("clean_prompts"):
                raise ValueError("clean prompts are missing")
            print(f"- {scenario_id}: ok")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failed = True
            print(f"- {scenario_id}: failed: {exc}")
    if failed:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage tracked demo scenario profiles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python3 scripts/scenario_profiles.py list
  python3 scripts/scenario_profiles.py show fastfood-ordering
  python3 scripts/scenario_profiles.py install fastfood-ordering --slot demo-b --force
  python3 scripts/scenario_profiles.py validate

after install:
  ansible-playbook ansible/playbooks/deploy_litellm.yml
""",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="List tracked scenario profiles.")

    show_parser = subparsers.add_parser("show", help="Show one scenario profile.")
    show_parser.add_argument("scenario", help="Scenario ID.")

    install_parser = subparsers.add_parser(
        "install",
        help="Install a scenario into a local instruction slot.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python3 scripts/scenario_profiles.py install fastfood-ordering --slot demo-b --force
  python3 scripts/scenario_profiles.py install fortigate-operator --slot demo-a --force
  python3 scripts/scenario_profiles.py install hr-policy-risk --slot demo-a --force

then deploy the prepared instructions:
  ansible-playbook ansible/playbooks/deploy_litellm.yml
""",
    )
    install_parser.add_argument("scenario", help="Scenario ID.")
    install_parser.add_argument("--slot", required=True, help="Instruction slot to install into, such as demo-a or demo-b.")
    install_parser.add_argument("--force", action="store_true", help="Replace the target local slot if it exists.")
    install_parser.add_argument("--link", action="store_true", help="Symlink instead of copying scenario instructions.")

    subparsers.add_parser("validate", help="Validate tracked scenario profiles.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command in {None, "list"}:
        print_list()
    elif args.command == "show":
        profile_path, profile = load_scenario(args.scenario)
        print_scenario(profile_path, profile)
    elif args.command == "install":
        install_scenario(args.scenario, slot=args.slot, force=args.force, link=args.link)
    elif args.command == "validate":
        validate_scenarios()
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
