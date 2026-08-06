#!/usr/bin/env python3
"""Install repeatable demo scenario profiles into local instruction slots."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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
SCHEMA_PATH = SCENARIO_ROOT / "scenario-profile-v2.schema.json"
MCP_SERVER_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "server.py"
SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATALOG_LIFECYCLES = {"baseline", "candidate", "archived"}


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


def scenario_lifecycle(entry: dict) -> str:
    lifecycle = str(entry.get("lifecycle") or "").strip().lower()
    if lifecycle:
        return lifecycle
    status = str(entry.get("status") or "").strip().lower()
    if "archived" in status or entry.get("active") is False:
        return "archived"
    return "baseline"


def scenario_is_active(entry: dict) -> bool:
    return scenario_lifecycle(entry) == "baseline"


def scenario_entries(
    *,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> dict:
    scenarios = catalog().get("scenarios", {})
    if include_inactive:
        return scenarios
    allowed_lifecycles = {"baseline", "candidate"} if include_candidates else {"baseline"}
    return {
        scenario_id: entry
        for scenario_id, entry in scenarios.items()
        if scenario_lifecycle(entry) in allowed_lifecycles
    }


def scenario_ids(
    *,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> list[str]:
    return sorted(
        scenario_entries(
            include_inactive=include_inactive,
            include_candidates=include_candidates,
        )
    )


def scenario_path(
    scenario_id: str,
    *,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> Path:
    scenarios = scenario_entries(
        include_inactive=include_inactive,
        include_candidates=include_candidates,
    )
    if scenario_id not in scenarios:
        available = ", ".join(sorted(scenarios))
        raise SystemExit(f"Unknown selectable scenario: {scenario_id}. Available: {available}")
    return (EXAMPLES_ROOT / scenarios[scenario_id]["path"]).resolve()


def load_scenario(
    scenario_id: str,
    *,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> tuple[Path, dict]:
    path = scenario_path(
        scenario_id,
        include_inactive=include_inactive,
        include_candidates=include_candidates,
    )
    profile = read_json(path)
    profile.setdefault("id", scenario_id)
    return path, profile


def resolve_package_file(profile_path: Path, relative_path: str, *, label: str) -> Path:
    package_root = profile_path.parent.resolve()
    path = (package_root / relative_path).resolve()
    if path != package_root and package_root not in path.parents:
        raise ValueError(f"{label} must stay inside the scenario package: {relative_path}")
    return path


def instruction_path(profile_path: Path, profile: dict, *, slot: str | None = None) -> Path:
    instruction_key = "instruction_file"
    if slot and instruction_profiles.resolve_slot(slot) == "frontend" and profile.get("frontend_instruction_file"):
        instruction_key = "frontend_instruction_file"
    try:
        path = resolve_package_file(
            profile_path,
            str(profile.get(instruction_key, "instructions.txt")),
            label=instruction_key,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not path.exists():
        raise SystemExit(f"Missing scenario instruction file: {path}")
    return path


def print_list(
    *,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> None:
    print_header("Scenario Profiles")
    scenarios = catalog().get("scenarios", {})
    for scenario_id in scenario_ids(
        include_inactive=include_inactive,
        include_candidates=include_candidates,
    ):
        entry = scenarios[scenario_id]
        profile_path, profile = load_scenario(scenario_id, include_inactive=True)
        print(f"- {scenario_id}: {entry.get('display_name', profile.get('display_name', scenario_id))}")
        print(f"  path: {profile_path.relative_to(REPO_ROOT)}")
        print(f"  lifecycle: {scenario_lifecycle(entry)}")
        status = entry.get("status", profile.get("status", ""))
        if status:
            print(f"  status: {status}")
        description = profile.get("description", "")
        if description:
            print(f"  description: {description}")


def print_scenario(profile_path: Path, profile: dict) -> None:
    print_header(profile.get("display_name", profile.get("id", "Scenario")))
    print(f"id: {profile.get('id')}")
    status = profile.get("status", "")
    if status:
        print(f"status: {status}")
    print(f"description: {profile.get('description', '')}")
    print(f"instructions: {instruction_path(profile_path, profile).relative_to(REPO_ROOT)}")
    if profile.get("frontend_instruction_file"):
        print(f"frontend instructions: {instruction_path(profile_path, profile, slot='frontend').relative_to(REPO_ROOT)}")

    mcp = profile.get("mcp", {})
    if mcp.get("enabled") is False:
        print("MCP tools: disabled")
    tool_profile = mcp.get("tool_profile", "")
    if tool_profile:
        print(f"MCP tool profile: {tool_profile}")
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

    payloads = sorted((profile_path.parent / "curl-payloads").glob("*.json"))
    if payloads:
        print("curl payloads:")
        for payload in payloads:
            print(f"- {payload.relative_to(REPO_ROOT)}")


def install_scenario(
    scenario_id: str,
    *,
    slot: str | None,
    force: bool,
    link: bool,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> Path:
    profile_path, profile = load_scenario(
        scenario_id,
        include_inactive=include_inactive,
        include_candidates=include_candidates,
    )
    if not slot:
        raise SystemExit("Choose the target instruction slot with --slot, for example: --slot demo-b")
    target_slot = slot
    source = instruction_path(profile_path, profile, slot=target_slot)
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

    mcp = dict(profile.get("mcp", {}))
    mcp.setdefault("enabled", bool(mcp.get("tool_profile") or mcp.get("required_tools")))
    metadata = {
        "display_name": profile.get("display_name", scenario_id),
        "description": profile.get("description", ""),
        "slot": instruction_profiles.resolve_slot(target_slot),
        "source_type": "scenario",
        "scenario_id": scenario_id,
        "source": str(source.relative_to(REPO_ROOT)),
        "mcp": mcp,
        "tool_profile": profile.get("mcp", {}).get("tool_profile", ""),
        "required_tools": profile.get("mcp", {}).get("required_tools", []),
        "chatbot_demo_profiles": profile.get("chatbot_demo_profiles", []),
        "updated_at": int(time.time()),
    }
    instruction_profiles.write_json(instruction_profiles.metadata_path_for_instruction(destination), metadata)

    print(f"installed: {scenario_id} -> {instruction_profiles.resolve_slot(target_slot)} -> {destination}")
    if metadata["tool_profile"]:
        print(f"chatbot MCP tool profile: {metadata['tool_profile']}")
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


def path_is_within(path: Path, root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def unexpected_key_errors(value: object, allowed_keys: set[str], *, field_name: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    unexpected = sorted(set(value) - allowed_keys)
    if not unexpected:
        return []
    return [f"{field_name} contains unsupported fields: {', '.join(unexpected)}"]


def catalog_validation_errors(catalog_data: dict) -> list[str]:
    errors: list[str] = []
    if catalog_data.get("schema_version") != 1:
        errors.append("catalog schema_version must be 1")
    scenarios = catalog_data.get("scenarios")
    if not isinstance(scenarios, dict):
        return errors + ["catalog scenarios must be an object"]

    for scenario_id, entry in sorted(scenarios.items()):
        prefix = f"catalog scenario {scenario_id}"
        if not SCENARIO_ID_PATTERN.fullmatch(str(scenario_id)):
            errors.append(f"{prefix}: ID must be lowercase kebab-case")
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be an object")
            continue
        lifecycle = scenario_lifecycle(entry)
        if lifecycle not in CATALOG_LIFECYCLES:
            errors.append(f"{prefix}: lifecycle must be baseline, candidate, or archived")
        expected_active = lifecycle == "baseline"
        if entry.get("active") is not expected_active:
            errors.append(f"{prefix}: active must be {str(expected_active).lower()} for lifecycle {lifecycle}")
        relative_path = entry.get("path")
        if not isinstance(relative_path, str) or not relative_path.strip():
            errors.append(f"{prefix}: path must be a non-empty string")
            continue
        profile_path = (EXAMPLES_ROOT / relative_path).resolve()
        if not path_is_within(profile_path, REPO_ROOT):
            errors.append(f"{prefix}: path resolves outside the repository")
        elif not profile_path.is_file():
            errors.append(f"{prefix}: profile does not exist: {relative_path}")
        else:
            try:
                profile = read_json(profile_path)
                if profile.get("id") != scenario_id:
                    errors.append(f"{prefix}: catalog key must equal profile id")
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{prefix}: cannot read profile: {exc}")
    return errors


def validate_relative_file(
    profile_path: Path,
    relative_path: object,
    *,
    field_name: str,
) -> list[str]:
    if not isinstance(relative_path, str) or not relative_path.strip():
        return [f"{field_name} must be a non-empty relative path"]
    try:
        path = resolve_package_file(profile_path, relative_path, label=field_name)
    except ValueError as exc:
        return [str(exc)]
    if not path.is_file():
        return [f"{field_name} does not exist: {relative_path}"]
    try:
        if not path.read_text(encoding="utf-8").strip():
            return [f"{field_name} is empty: {relative_path}"]
    except OSError as exc:
        return [f"cannot read {field_name}: {exc}"]
    return []


def payload_validation_errors(profile_path: Path) -> list[str]:
    errors: list[str] = []
    payload_dir = profile_path.parent / "curl-payloads"
    for payload_path in sorted(payload_dir.glob("*.json")):
        try:
            payload = read_json(payload_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{payload_path.name}: cannot read payload: {exc}")
            continue
        if not payload.get("model"):
            errors.append(f"{payload_path.name}: missing model")
        messages = payload.get("messages", [])
        if not isinstance(messages, list) or not messages:
            errors.append(f"{payload_path.name}: missing messages list")
        elif not any(
            message.get("role") == "tool"
            for message in messages
            if isinstance(message, dict)
        ):
            errors.append(f"{payload_path.name}: missing tool result message")
    return errors


def baseline_profile_validation(
    scenario_id: str,
    profile_path: Path,
    profile: dict,
    available_tools: set[str],
) -> tuple[list[str], dict[str, list[str]]]:
    errors: list[str] = []
    symbols: dict[str, list[str]] = {
        "model_alias": [],
        "route_uri": [],
        "guard_name": [],
        "chatbot_profile": [],
        "frontend_profile": [],
    }
    errors.extend(
        unexpected_key_errors(
            profile,
            {
                "schema_version",
                "id",
                "display_name",
                "description",
                "instruction_file",
                "frontend_instruction_file",
                "status",
                "mcp",
                "matrix",
                "chatbot_demo_profiles",
                "clean_prompts",
                "attack_prompts",
                "expected_trace",
                "route_matrix",
                "walkthrough",
            },
            field_name="profile",
        )
    )

    if profile.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if profile.get("id") != scenario_id:
        errors.append("profile id must equal the catalog scenario ID")
    if not SCENARIO_ID_PATTERN.fullmatch(str(profile.get("id") or "")):
        errors.append("profile id must be lowercase kebab-case")
    if profile.get("status") != "phase11-baseline":
        errors.append("status must be phase11-baseline")
    for field_name in ("display_name", "description"):
        if not isinstance(profile.get(field_name), str) or not profile[field_name].strip():
            errors.append(f"{field_name} must be a non-empty string")
    errors.extend(
        validate_relative_file(
            profile_path,
            profile.get("instruction_file"),
            field_name="instruction_file",
        )
    )

    mcp = profile.get("mcp")
    if not isinstance(mcp, dict):
        errors.append("mcp must be an object")
        mcp = {}
    errors.extend(
        unexpected_key_errors(
            mcp,
            {
                "enabled",
                "default_transport",
                "default_tool_set",
                "tool_profile",
                "required_tools",
                "extended_tool_sets",
                "max_tool_rounds",
                "data_sources",
            },
            field_name="mcp",
        )
    )
    mcp_enabled = mcp.get("enabled")
    if not isinstance(mcp_enabled, bool):
        errors.append("mcp.enabled must be a boolean")
    if mcp.get("default_transport") not in {"direct", "fortiweb"}:
        errors.append("mcp.default_transport must be direct or fortiweb")
    required_tools = mcp.get("required_tools")
    if not isinstance(required_tools, list) or any(not isinstance(tool, str) or not tool for tool in required_tools):
        errors.append("mcp.required_tools must be a string list")
        required_tools = []
    duplicates = duplicate_values(required_tools)
    if duplicates:
        errors.append(f"mcp.required_tools contains duplicates: {', '.join(duplicates)}")
    if mcp_enabled is True and not required_tools:
        errors.append("mcp.required_tools cannot be empty when MCP is enabled")
    if mcp_enabled is False and required_tools:
        errors.append("mcp.required_tools must be empty when MCP is disabled")
    missing_tools = sorted(set(required_tools) - available_tools)
    if missing_tools:
        errors.append(f"required MCP tools are not in shared MCP server: {', '.join(missing_tools)}")
    if not isinstance(mcp.get("tool_profile"), str):
        errors.append("mcp.tool_profile must be a string")
    max_tool_rounds = mcp.get("max_tool_rounds")
    if not isinstance(max_tool_rounds, int) or isinstance(max_tool_rounds, bool) or not 1 <= max_tool_rounds <= 8:
        errors.append("mcp.max_tool_rounds must be an integer from 1 through 8")
    extended_tool_sets = mcp.get("extended_tool_sets")
    if not isinstance(extended_tool_sets, list):
        errors.append("mcp.extended_tool_sets must be a list")
        extended_tool_sets = []
    extended_ids: list[str] = []
    for index, tool_set in enumerate(extended_tool_sets):
        if not isinstance(tool_set, dict):
            errors.append(f"mcp.extended_tool_sets[{index}] must be an object")
            continue
        errors.extend(
            unexpected_key_errors(
                tool_set,
                {"id", "display_name", "tools"},
                field_name=f"mcp.extended_tool_sets[{index}]",
            )
        )
        tool_set_id = str(tool_set.get("id") or "")
        extended_ids.append(tool_set_id)
        if not SCENARIO_ID_PATTERN.fullmatch(tool_set_id):
            errors.append(f"mcp.extended_tool_sets[{index}].id must be lowercase kebab-case")
        if not isinstance(tool_set.get("display_name"), str) or not tool_set["display_name"].strip():
            errors.append(f"mcp.extended_tool_sets[{index}].display_name must be non-empty")
        tools = tool_set.get("tools")
        if not isinstance(tools, list) or not tools:
            errors.append(f"mcp.extended_tool_sets[{index}].tools must be a non-empty list")
        else:
            missing_extended = sorted(set(tools) - available_tools)
            if missing_extended:
                errors.append(
                    f"mcp.extended_tool_sets[{index}] tools are not in shared MCP server: "
                    + ", ".join(missing_extended)
                )
    duplicate_extended = duplicate_values(extended_ids)
    if duplicate_extended:
        errors.append(f"mcp.extended_tool_sets contains duplicate IDs: {', '.join(duplicate_extended)}")
    allowed_tool_sets = {"scenario", *extended_ids}
    if mcp.get("default_tool_set") not in allowed_tool_sets:
        errors.append("mcp.default_tool_set must be scenario or a declared extended tool set")

    matrix = profile.get("matrix")
    if not isinstance(matrix, dict):
        errors.append("matrix must be an object")
        matrix = {}
    errors.extend(
        unexpected_key_errors(
            matrix,
            {
                "llm_target",
                "instruction_profile",
                "entry_points",
                "frontend_instruction_profiles",
                "chatbot_profiles",
                "faig_chain",
            },
            field_name="matrix",
        )
    )
    if not SCENARIO_ID_PATTERN.fullmatch(str(matrix.get("llm_target") or "")):
        errors.append("matrix.llm_target must be lowercase kebab-case")
    instruction_profile = matrix.get("instruction_profile")
    if not isinstance(instruction_profile, dict):
        errors.append("matrix.instruction_profile must be an object")
    else:
        errors.extend(
            unexpected_key_errors(
                instruction_profile,
                {"source", "position", "enabled"},
                field_name="matrix.instruction_profile",
            )
        )
        if instruction_profile.get("source") not in {
            "scenario_instruction",
            "inline",
            "path",
            "disabled",
        }:
            errors.append("matrix.instruction_profile.source is invalid")
        if instruction_profile.get("position") not in {"prepend", "append"}:
            errors.append("matrix.instruction_profile.position must be prepend or append")
        if not isinstance(instruction_profile.get("enabled"), bool):
            errors.append("matrix.instruction_profile.enabled must be a boolean")

    entry_points = matrix.get("entry_points")
    if not isinstance(entry_points, list) or not entry_points:
        errors.append("matrix.entry_points must be a non-empty list")
        entry_points = []
    entry_roles: list[str] = []
    entry_templates: dict[str, str] = {}
    valid_guard_templates = {
        "detect_only",
        "protect_input",
        "output_dlp_redact",
        "output_dlp_deny",
        "input_dlp",
    }
    for index, entry_point in enumerate(entry_points):
        if not isinstance(entry_point, dict):
            errors.append(f"matrix.entry_points[{index}] must be an object")
            continue
        errors.extend(
            unexpected_key_errors(
                entry_point,
                {
                    "role",
                    "display_name",
                    "guard_template",
                    "expected_behavior",
                    "required_for_release",
                },
                field_name=f"matrix.entry_points[{index}]",
            )
        )
        role = str(entry_point.get("role") or "")
        entry_roles.append(role)
        entry_templates[role] = str(entry_point.get("guard_template") or "")
        if not SCENARIO_ID_PATTERN.fullmatch(role):
            errors.append(f"matrix.entry_points[{index}].role must be lowercase kebab-case")
        if not isinstance(entry_point.get("display_name"), str) or not entry_point["display_name"].strip():
            errors.append(f"matrix.entry_points[{index}].display_name must be non-empty")
        if entry_point.get("guard_template") not in valid_guard_templates:
            errors.append(f"matrix.entry_points[{index}].guard_template is invalid")
        if not isinstance(entry_point.get("expected_behavior"), str) or not entry_point["expected_behavior"].strip():
            errors.append(f"matrix.entry_points[{index}].expected_behavior must be non-empty")
        if not isinstance(entry_point.get("required_for_release"), bool):
            errors.append(f"matrix.entry_points[{index}].required_for_release must be a boolean")
        symbols["route_uri"].append(f"/v1/{scenario_id}/{role}")
        symbols["guard_name"].append(f"{scenario_id}_{role}".replace("-", "_"))
    duplicate_roles = duplicate_values(entry_roles)
    if duplicate_roles:
        errors.append(f"matrix.entry_points contains duplicate roles: {', '.join(duplicate_roles)}")
    if entry_roles.count("detect") != 1:
        errors.append("matrix.entry_points must contain exactly one detect role")
    elif entry_templates.get("detect") != "detect_only":
        errors.append("the detect entry point must use guard_template detect_only")

    frontend_profiles = matrix.get("frontend_instruction_profiles")
    if not isinstance(frontend_profiles, list) or not frontend_profiles:
        errors.append("matrix.frontend_instruction_profiles must be a non-empty list")
        frontend_profiles = []
    frontend_ids: list[str] = []
    for index, frontend_profile in enumerate(frontend_profiles):
        if not isinstance(frontend_profile, dict):
            errors.append(f"matrix.frontend_instruction_profiles[{index}] must be an object")
            continue
        profile_id = str(frontend_profile.get("id") or "")
        frontend_ids.append(profile_id)
        source_type = frontend_profile.get("source_type")
        allowed_frontend_keys = (
            {"id", "display_name", "source_type"}
            if profile_id == "none"
            else {"id", "display_name", "source_type", "source"}
        )
        errors.extend(
            unexpected_key_errors(
                frontend_profile,
                allowed_frontend_keys,
                field_name=f"matrix.frontend_instruction_profiles[{index}]",
            )
        )
        if not SCENARIO_ID_PATTERN.fullmatch(profile_id):
            errors.append(f"matrix.frontend_instruction_profiles[{index}].id must be lowercase kebab-case")
        if not isinstance(frontend_profile.get("display_name"), str) or not frontend_profile["display_name"].strip():
            errors.append(f"matrix.frontend_instruction_profiles[{index}].display_name must be non-empty")
        if profile_id == "none":
            if source_type != "none" or "source" in frontend_profile:
                errors.append("frontend profile none must use source_type none without source")
        elif source_type == "file":
            errors.extend(
                validate_relative_file(
                    profile_path,
                    frontend_profile.get("source"),
                    field_name=f"matrix.frontend_instruction_profiles[{index}].source",
                )
            )
            symbols["frontend_profile"].append(profile_id)
        else:
            errors.append(f"matrix.frontend_instruction_profiles[{index}].source_type must be file")
    duplicate_frontend = duplicate_values(frontend_ids)
    if duplicate_frontend:
        errors.append(
            "matrix.frontend_instruction_profiles contains duplicate IDs: "
            + ", ".join(duplicate_frontend)
        )
    if frontend_ids.count("none") != 1:
        errors.append("matrix.frontend_instruction_profiles must contain exactly one none profile")

    chatbot_profiles = matrix.get("chatbot_profiles")
    if not isinstance(chatbot_profiles, list) or not chatbot_profiles:
        errors.append("matrix.chatbot_profiles must be a non-empty list")
        chatbot_profiles = []
    chatbot_ids: list[str] = []
    for index, chatbot_profile in enumerate(chatbot_profiles):
        if not isinstance(chatbot_profile, dict):
            errors.append(f"matrix.chatbot_profiles[{index}] must be an object")
            continue
        errors.extend(
            unexpected_key_errors(
                chatbot_profile,
                {
                    "id",
                    "display_name",
                    "provider_path",
                    "entry_point_role",
                    "context_mode",
                    "context_window",
                    "frontend_instruction_profile",
                },
                field_name=f"matrix.chatbot_profiles[{index}]",
            )
        )
        profile_id = str(chatbot_profile.get("id") or "")
        chatbot_ids.append(profile_id)
        if not SCENARIO_ID_PATTERN.fullmatch(profile_id):
            errors.append(f"matrix.chatbot_profiles[{index}].id must be lowercase kebab-case")
        if not isinstance(chatbot_profile.get("display_name"), str) or not chatbot_profile["display_name"].strip():
            errors.append(f"matrix.chatbot_profiles[{index}].display_name must be non-empty")
        provider_path = chatbot_profile.get("provider_path")
        if provider_path not in {"direct", "faig-static", "fortigate-litellm"}:
            errors.append(f"matrix.chatbot_profiles[{index}].provider_path is invalid")
        entry_role = chatbot_profile.get("entry_point_role")
        if provider_path == "direct" and entry_role is not None:
            errors.append(f"matrix.chatbot_profiles[{index}] direct profile cannot set entry_point_role")
        if provider_path != "direct" and entry_role not in entry_roles:
            errors.append(f"matrix.chatbot_profiles[{index}] references unknown entry_point_role")
        if chatbot_profile.get("frontend_instruction_profile") not in frontend_ids:
            errors.append(f"matrix.chatbot_profiles[{index}] references unknown frontend instruction profile")
        if chatbot_profile.get("context_mode") not in {"current", "recent", "consolidated"}:
            errors.append(f"matrix.chatbot_profiles[{index}].context_mode is invalid")
        context_window = chatbot_profile.get("context_window")
        if not isinstance(context_window, int) or isinstance(context_window, bool) or not 1 <= context_window <= 24:
            errors.append(f"matrix.chatbot_profiles[{index}].context_window must be from 1 through 24")
    duplicate_chatbot = duplicate_values(chatbot_ids)
    if duplicate_chatbot:
        errors.append(f"matrix.chatbot_profiles contains duplicate IDs: {', '.join(duplicate_chatbot)}")
    symbols["chatbot_profile"].extend(chatbot_ids)
    symbols["model_alias"].append(scenario_id)

    faig_chain = matrix.get("faig_chain")
    if not isinstance(faig_chain, dict) or faig_chain.get("enabled") is not False:
        errors.append("matrix.faig_chain.enabled must be false for the Phase 11 baseline")
    else:
        errors.extend(
            unexpected_key_errors(
                faig_chain,
                {"enabled"},
                field_name="matrix.faig_chain",
            )
        )
    clean_prompts = profile.get("clean_prompts")
    if not isinstance(clean_prompts, list) or not clean_prompts:
        errors.append("clean_prompts must be a non-empty list")
    errors.extend(payload_validation_errors(profile_path))
    return errors, symbols


def legacy_profile_validation(
    profile_path: Path,
    profile: dict,
    available_tools: set[str],
) -> list[str]:
    errors = validate_relative_file(
        profile_path,
        profile.get("instruction_file", "instructions.txt"),
        field_name="instruction_file",
    )
    mcp = profile.get("mcp", {})
    required_tools = mcp.get("required_tools", []) if isinstance(mcp, dict) else []
    if bool(mcp.get("enabled", True)) and not required_tools:
        errors.append("required MCP tools are missing")
    missing_tools = sorted(set(required_tools) - available_tools)
    if missing_tools:
        errors.append(f"required MCP tools are not in shared MCP server: {', '.join(missing_tools)}")
    if profile.get("frontend_instruction_file"):
        errors.extend(
            validate_relative_file(
                profile_path,
                profile.get("frontend_instruction_file"),
                field_name="frontend_instruction_file",
            )
        )
    if not profile.get("clean_prompts"):
        errors.append("clean prompts are missing")
    errors.extend(payload_validation_errors(profile_path))
    return errors


def register_generated_symbols(
    global_symbols: dict[str, dict[str, str]],
    scenario_id: str,
    symbols: dict[str, list[str]],
) -> list[str]:
    errors: list[str] = []
    for symbol_type, values in symbols.items():
        owners = global_symbols.setdefault(symbol_type, {})
        for value in values:
            owner = owners.get(value)
            if owner and owner != scenario_id:
                errors.append(f"generated {symbol_type} {value} collides with scenario {owner}")
            else:
                owners[value] = scenario_id
    return errors


def validate_scenarios(
    *,
    include_inactive: bool = False,
    include_candidates: bool = False,
) -> None:
    print_header("Validate Scenario Profiles")
    failed = False
    try:
        schema = read_json(SCHEMA_PATH)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError("scenario profile schema must use JSON Schema draft 2020-12")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"- schema: failed: {exc}")
        failed = True

    catalog_data = catalog()
    catalog_errors = catalog_validation_errors(catalog_data)
    for error in catalog_errors:
        print(f"- catalog: failed: {error}")
    failed = failed or bool(catalog_errors)

    available_tools = shared_mcp_tool_names()
    global_symbols: dict[str, dict[str, str]] = {
        "model_alias": {},
        "route_uri": {},
        "guard_name": {},
        "chatbot_profile": {},
        "frontend_profile": {},
    }
    for scenario_id in scenario_ids(
        include_inactive=include_inactive,
        include_candidates=include_candidates,
    ):
        try:
            profile_path, profile = load_scenario(scenario_id, include_inactive=True)
            lifecycle = scenario_lifecycle(catalog_data["scenarios"][scenario_id])
            if lifecycle == "baseline":
                errors, symbols = baseline_profile_validation(
                    scenario_id,
                    profile_path,
                    profile,
                    available_tools,
                )
                errors.extend(register_generated_symbols(global_symbols, scenario_id, symbols))
            else:
                errors = legacy_profile_validation(profile_path, profile, available_tools)
            if errors:
                failed = True
                for error in errors:
                    print(f"- {scenario_id}: failed: {error}")
            else:
                print(f"- {scenario_id}: ok ({lifecycle})")
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
  python3 scripts/scenario_profiles.py show fortistore-injection
  python3 scripts/scenario_profiles.py install fortistore-injection --slot demo-a --force
  python3 scripts/scenario_profiles.py list --include-inactive
  python3 scripts/scenario_profiles.py validate

after install:
  ansible-playbook ansible/playbooks/deploy_litellm.yml
""",
    )
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List Phase 11 baseline scenario profiles.")
    list_parser.add_argument("--include-candidates", action="store_true", help="Also show future candidate profiles.")
    list_parser.add_argument("--include-inactive", action="store_true", help="Show baseline, candidate, and archived profiles.")

    show_parser = subparsers.add_parser("show", help="Show one scenario profile.")
    show_parser.add_argument("scenario", help="Scenario ID.")
    show_parser.add_argument("--include-candidates", action="store_true", help="Allow showing a future candidate profile.")
    show_parser.add_argument("--include-inactive", action="store_true", help="Allow showing a candidate or archived profile.")

    install_parser = subparsers.add_parser(
        "install",
        help="Install a scenario into a local instruction slot.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python3 scripts/scenario_profiles.py install fortistore-injection --slot demo-a --force
  python3 scripts/scenario_profiles.py install hr-tool-dlp --slot demo-a --force

then deploy the prepared instructions:
  ansible-playbook ansible/playbooks/deploy_litellm.yml
""",
    )
    install_parser.add_argument("scenario", help="Scenario ID.")
    install_parser.add_argument("--slot", required=True, help="Instruction slot to install into, such as demo-a or demo-b.")
    install_parser.add_argument("--force", action="store_true", help="Replace the target local slot if it exists.")
    install_parser.add_argument("--link", action="store_true", help="Symlink instead of copying scenario instructions.")
    install_parser.add_argument("--include-candidates", action="store_true", help="Allow installing a future candidate profile for testing.")
    install_parser.add_argument("--include-inactive", action="store_true", help="Allow installing a candidate or archived profile for testing.")

    validate_parser = subparsers.add_parser("validate", help="Validate Phase 11 baseline scenario profiles.")
    validate_parser.add_argument("--include-candidates", action="store_true", help="Also validate future candidate profiles with the legacy checks.")
    validate_parser.add_argument("--include-inactive", action="store_true", help="Also validate candidate and archived profiles with the legacy checks.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command in {None, "list"}:
        print_list(
            include_inactive=getattr(args, "include_inactive", False),
            include_candidates=getattr(args, "include_candidates", False),
        )
    elif args.command == "show":
        profile_path, profile = load_scenario(
            args.scenario,
            include_inactive=args.include_inactive,
            include_candidates=args.include_candidates,
        )
        print_scenario(profile_path, profile)
    elif args.command == "install":
        install_scenario(
            args.scenario,
            slot=args.slot,
            force=args.force,
            link=args.link,
            include_inactive=args.include_inactive,
            include_candidates=args.include_candidates,
        )
    elif args.command == "validate":
        validate_scenarios(
            include_inactive=args.include_inactive,
            include_candidates=args.include_candidates,
        )
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
