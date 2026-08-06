#!/usr/bin/env python3
"""Build deterministic runtime objects from installed scenario metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MATRIX_SCHEMA_VERSION = 1


class ScenarioMatrixError(RuntimeError):
    """Raised when installed scenario metadata cannot form a valid matrix."""


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def frontend_profiles(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {
        "none": {
            "id": "none",
            "display_name": "No Frontend Instructions",
            "source_type": "none",
        }
    }
    for scenario in scenarios:
        local_profile = Path(str(scenario["local_profile"]))
        package_root = local_profile.parent
        for profile in scenario.get("frontend_instruction_profiles", []):
            profile_id = str(profile.get("id") or "")
            if profile_id == "none":
                continue
            if profile_id in profiles:
                raise ScenarioMatrixError(
                    f"Duplicate frontend instruction profile: {profile_id}"
                )
            rendered = dict(profile)
            source = str(profile.get("source") or "")
            rendered["source_path"] = str(package_root / source)
            rendered["scenario_id"] = scenario["scenario_id"]
            profiles[profile_id] = rendered
    return [profiles[profile_id] for profile_id in sorted(profiles)]


def mcp_profiles(
    scenarios: list[dict[str, Any]],
    *,
    include_debug_all_server_tools: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    profiles: list[dict[str, Any]] = []
    installed_tools: list[str] = []
    default_candidates: list[str] = []
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        mcp = scenario.get("mcp", {})
        if not isinstance(mcp, dict) or not mcp.get("enabled", False):
            continue
        required_tools = ordered_unique([str(tool) for tool in mcp.get("required_tools", [])])
        installed_tools.extend(required_tools)
        default_candidates.append(scenario_id)
        profiles.append(
            {
                "name": scenario_id,
                "label": f"{scenario['display_name']} - Scenario Tools",
                "kind": "scenario",
                "scenario_id": scenario_id,
                "tools": required_tools,
            }
        )
        for extended in mcp.get("extended_tool_sets", []):
            extended_id = str(extended.get("id") or "")
            profile_name = f"{scenario_id}-{extended_id}"
            profiles.append(
                {
                    "name": profile_name,
                    "label": str(extended.get("display_name") or profile_name),
                    "kind": "extended",
                    "scenario_id": scenario_id,
                    "tools": ordered_unique(required_tools + list(extended.get("tools", []))),
                }
            )

    installed_tools = ordered_unique(installed_tools)
    if installed_tools:
        profiles.append(
            {
                "name": "all-installed",
                "label": "All Installed Scenario Tools",
                "kind": "all-installed",
                "tools": installed_tools,
            }
        )
    if include_debug_all_server_tools:
        profiles.append(
            {
                "name": "all-server",
                "label": "Debug - All MCP Server Tools",
                "kind": "all-server",
                "tools": [],
                "allow_all": True,
            }
        )
    profile_names = [profile["name"] for profile in profiles]
    duplicates = sorted(name for name in set(profile_names) if profile_names.count(name) > 1)
    if duplicates:
        raise ScenarioMatrixError(f"Duplicate MCP tool profiles: {', '.join(duplicates)}")
    return sorted(profiles, key=lambda profile: profile["name"]), default_candidates


def mcp_paths(
    scenarios: list[dict[str, Any]],
    capabilities: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not any(scenario.get("mcp", {}).get("enabled", False) for scenario in scenarios):
        return [], []
    paths = [
        {
            "name": "direct",
            "label": "Direct MCP",
            "kind": "direct",
        }
    ]
    warnings: list[str] = []
    fortiweb_desired = bool(capabilities.get("fortiweb_mcp_desired", False))
    fortiweb_installed = bool(capabilities.get("fortiweb_installed", False))
    fortiweb_base_url = str(capabilities.get("fortiweb_mcp_base_url") or "").strip()
    if fortiweb_desired and fortiweb_installed and fortiweb_base_url:
        paths.append(
            {
                "name": "fortiweb",
                "label": "FortiWeb MCP",
                "kind": "fortiweb",
                "base_url": fortiweb_base_url,
            }
        )
    elif fortiweb_desired:
        warnings.append(
            "FortiWeb MCP was requested but was not generated because the appliance "
            "is not installed or its MCP base URL is missing."
        )
    return paths, warnings


def build_scenario_matrix(
    preview: dict[str, Any],
    *,
    capabilities: dict[str, Any] | None = None,
    include_debug_all_server_tools: bool = False,
) -> dict[str, Any]:
    capabilities = dict(capabilities or {})
    scenarios = sorted(
        list(preview.get("installed_scenarios", [])),
        key=lambda scenario: scenario["scenario_id"],
    )
    warnings: list[str] = []

    llm_targets = {"llm-default"}
    litellm_models = [
        {
            "name": "pass-model",
            "llm_target": "llm-default",
            "instruction_profile": "passthrough",
        }
    ]
    litellm_instruction_profiles = [
        {
            "name": "passthrough",
            "enabled": False,
            "position": "prepend",
            "instruction": "No backend instruction injection for passthrough model aliases.",
        }
    ]
    model_instruction_profiles = {"pass-model": "passthrough"}
    chatbot_model_options = ["pass-model"]
    chatbot_faig_routes = [
        {
            "name": "passthrough",
            "label": "FAIG Passthrough",
            "base_path": "/v1/passthrough",
            "model": "pass-model",
            "scenario_id": "",
            "action": "passthrough",
        }
    ]
    work_order: list[dict[str, Any]] = []

    rendered_frontend_profiles = frontend_profiles(scenarios)
    rendered_mcp_profiles, mcp_default_candidates = mcp_profiles(
        scenarios,
        include_debug_all_server_tools=include_debug_all_server_tools,
    )
    rendered_mcp_paths, mcp_warnings = mcp_paths(scenarios, capabilities)
    warnings.extend(mcp_warnings)
    available_mcp_paths = {path["name"] for path in rendered_mcp_paths}
    available_frontend_profiles = {
        profile["id"] for profile in rendered_frontend_profiles
    }
    simplified_profiles: list[dict[str, Any]] = []

    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        llm_target = str(scenario.get("llm_target") or "llm-default")
        instruction_profile = scenario.get("instruction_profile", {})
        llm_targets.add(llm_target)
        litellm_models.append(
            {
                "name": scenario_id,
                "llm_target": llm_target,
                "instruction_profile": scenario_id,
            }
        )
        litellm_instruction_profiles.append(
            {
                "name": scenario_id,
                "enabled": bool(instruction_profile.get("enabled", True)),
                "position": str(instruction_profile.get("position") or "prepend"),
                "source_path": scenario["instruction_file"],
                "content_hash": scenario["content_hash"],
            }
        )
        model_instruction_profiles[scenario_id] = scenario_id
        chatbot_model_options.append(scenario_id)

        entry_points = {
            entry_point["action"]: entry_point
            for entry_point in scenario.get("entry_points", [])
        }
        for entry_point in scenario.get("entry_points", []):
            route = {
                "name": entry_point["route"],
                "label": f"{scenario['display_name']} - {entry_point['display_name']}",
                "base_path": entry_point["uri"],
                "model": scenario_id,
                "scenario_id": scenario_id,
                "action": entry_point["action"],
            }
            chatbot_faig_routes.append(route)
            work_order.append(
                {
                    "scenario_id": scenario_id,
                    **entry_point,
                }
            )

        mcp = scenario.get("mcp", {})
        mcp_enabled = bool(mcp.get("enabled", False))
        default_mcp_path = str(mcp.get("default_transport") or "direct")
        if mcp_enabled and default_mcp_path not in available_mcp_paths:
            warnings.append(
                f"{scenario_id} requested unavailable MCP path {default_mcp_path}; "
                "simplified profiles use direct MCP."
            )
            default_mcp_path = "direct"
        for profile in scenario.get("chatbot_profiles", []):
            profile_id = str(profile["id"])
            provider_path = str(profile["provider_path"])
            rendered_profile = {
                "id": profile_id,
                "label": str(profile["display_name"]),
                "scenario_id": scenario_id,
                "provider_path": provider_path,
                "context_mode": profile["context_mode"],
                "context_window": profile["context_window"],
                "frontend_instruction_profile": profile["frontend_instruction_profile"],
                "mcp_enabled": mcp_enabled,
                "mcp_path": default_mcp_path,
                "mcp_tool_profile": scenario_id if mcp_enabled else "",
                "mcp_max_tool_rounds": int(mcp.get("max_tool_rounds", 3)),
            }
            frontend_profile = rendered_profile["frontend_instruction_profile"]
            if frontend_profile not in available_frontend_profiles:
                raise ScenarioMatrixError(
                    f"Chatbot profile {profile_id} references missing frontend profile "
                    f"{frontend_profile}"
                )
            if provider_path == "direct":
                rendered_profile["model"] = scenario_id
            elif provider_path == "faig-static":
                action = str(profile.get("entry_point_action") or "")
                if action not in entry_points:
                    raise ScenarioMatrixError(
                        f"Chatbot profile {profile_id} references missing entry point {action}"
                    )
                rendered_profile["route"] = entry_points[action]["route"]
                rendered_profile["model"] = scenario_id
            else:
                warnings.append(
                    f"Chatbot profile {profile_id} uses deferred provider path {provider_path} "
                    "and was not generated."
                )
                continue
            simplified_profiles.append(rendered_profile)

    if not scenarios:
        simplified_profiles = [
            {
                "id": "direct-passthrough",
                "label": "Direct Passthrough",
                "scenario_id": "",
                "provider_path": "direct",
                "model": "pass-model",
                "context_mode": "current",
                "context_window": 1,
                "frontend_instruction_profile": "none",
                "mcp_enabled": False,
                "mcp_path": "direct",
                "mcp_tool_profile": "",
                "mcp_max_tool_rounds": 3,
            },
            {
                "id": "faig-passthrough",
                "label": "FAIG Passthrough",
                "scenario_id": "",
                "provider_path": "faig-static",
                "route": "passthrough",
                "model": "pass-model",
                "context_mode": "current",
                "context_window": 1,
                "frontend_instruction_profile": "none",
                "mcp_enabled": False,
                "mcp_path": "direct",
                "mcp_tool_profile": "",
                "mcp_max_tool_rounds": 3,
            },
        ]

    if capabilities.get("fortigate_routes_desired", False):
        warnings.append(
            "FortiGate scenario routes are disabled during the initial Phase 11 matrix implementation."
        )

    matrix = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "global": {
            "passthrough_model_alias": "pass-model",
            "faig_passthrough_uri": "/v1/passthrough",
        },
        "capabilities": {
            "fortigate_routes_enabled": False,
            "fortiweb_mcp_enabled": any(
                path["name"] == "fortiweb" for path in rendered_mcp_paths
            ),
        },
        "llm_targets": [
            {"name": target}
            for target in sorted(llm_targets)
        ],
        "litellm_models": sorted(litellm_models, key=lambda model: model["name"]),
        "litellm_instruction_profiles": sorted(
            litellm_instruction_profiles,
            key=lambda profile: profile["name"],
        ),
        "litellm_model_instruction_profiles": dict(
            sorted(model_instruction_profiles.items())
        ),
        "chatbot_model_options": ordered_unique(chatbot_model_options),
        "chatbot_faig_static_routes": sorted(
            chatbot_faig_routes,
            key=lambda route: route["name"],
        ),
        "chatbot_fortigate_routes": [],
        "chatbot_mcp_paths": rendered_mcp_paths,
        "chatbot_frontend_instruction_profiles": rendered_frontend_profiles,
        "chatbot_advanced_controls": {
            "default_model": "pass-model" if not scenarios else scenarios[0]["scenario_id"],
            "default_faig_route": "passthrough",
            "default_mcp_path": "direct",
            "default_mcp_tool_profile": (
                mcp_default_candidates[0] if mcp_default_candidates else ""
            ),
        },
        "chatbot_simplified_profiles": sorted(
            simplified_profiles,
            key=lambda profile: profile["id"],
        ),
        "chatbot_mcp_tool_profiles": rendered_mcp_profiles,
        "faig_work_order": sorted(
            work_order,
            key=lambda entry: (entry["scenario_id"], entry["action"]),
        ),
        "source_scenarios": [
            {
                "scenario_id": scenario["scenario_id"],
                "local_profile": scenario["local_profile"],
                "content_hash": scenario["content_hash"],
                "source_hash": scenario["source_hash"],
                "source_update_available": scenario["source_update_available"],
            }
            for scenario in scenarios
        ],
        "warnings": sorted(set(warnings)),
    }
    return matrix


def render_work_order(matrix: dict[str, Any]) -> str:
    lines = [
        "# FAIG Scenario Work Order",
        "",
        "## Global Controls",
        "",
        "- LiteLLM passthrough alias: `pass-model`",
        "- FAIG passthrough configured URI: `/v1/passthrough/*`",
        "- Behavior: no scenario instructions",
        "",
        "## Installed Scenario Objects",
        "",
    ]
    work_order = matrix.get("faig_work_order", [])
    if not work_order:
        lines.extend(["No scenario-specific FAIG objects are required.", ""])
    else:
        lines.extend(
            [
                "| Scenario | Action | Suggested flow | Configured URI | Suggested guard | Next-hop model | Guard template | Required | Expected behavior |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for entry in work_order:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{entry['scenario_id']}`",
                        entry["display_name"],
                        f"`{entry['suggested_flow_name']}`",
                        f"`{entry['uri']}/*`",
                        f"`{entry['suggested_guard_name']}`",
                        f"`{entry['guard_next_hop_model']}`",
                        f"`{entry['guard_template']}`",
                        "yes" if entry["required_for_release"] else "no",
                        str(entry["expected_behavior"]).replace("|", "\\|"),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "Guard and flow names may differ, but each configured URI and guard next-hop",
                "LiteLLM model alias must match this work order.",
                "",
            ]
        )
    if matrix.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in matrix["warnings"])
        lines.append("")
    return "\n".join(lines)


def canonical_json(matrix: dict[str, Any]) -> str:
    return json.dumps(matrix, indent=2, sort_keys=True) + "\n"
