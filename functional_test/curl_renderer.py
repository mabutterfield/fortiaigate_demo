"""Render operator-shell curl requests from installed scenario metadata."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from functional_test import validation
from scripts import scenario_local


DEFAULT_OUTPUT_ROOT = validation.REPO_ROOT / "functional_test" / "output" / "rendered-curl"


def package_file(package_root: Path, relative_path: str) -> Path:
    candidate = (package_root / relative_path).resolve()
    try:
        candidate.relative_to(package_root.resolve())
    except ValueError as exc:
        raise SystemExit(f"Functional request escapes its scenario package: {relative_path}") from exc
    if not candidate.is_file():
        raise SystemExit(f"Functional request does not exist: {candidate}")
    return candidate


def validation_case(profile: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in profile.get("validation", {}).get("cases", []):
        if case.get("id") == case_id:
            return case
    available = ", ".join(
        str(case.get("id")) for case in profile.get("validation", {}).get("cases", [])
    ) or "none"
    raise SystemExit(f"Unknown validation case '{case_id}'. Available: {available}")


def request_mapping(package_root: Path, scenario_id: str, case_id: str) -> Path:
    mapping_path = package_root / "functional-tests" / "cases.json"
    if not mapping_path.is_file():
        mapping_path = (
            validation.TRACKED_SCENARIOS_ROOT
            / scenario_id
            / "functional-tests"
            / "cases.json"
        )
    mapping = validation.load_json(mapping_path)
    if mapping.get("schema_version") != 1:
        raise SystemExit(f"Unsupported functional-test mapping schema: {mapping_path}")
    cases = mapping.get("cases", {})
    if not isinstance(cases, dict) or case_id not in cases:
        available = ", ".join(sorted(cases)) if isinstance(cases, dict) else "none"
        raise SystemExit(
            f"Validation case '{case_id}' has no functional request mapping. Available: {available}"
        )
    entry = cases[case_id]
    if not isinstance(entry, dict) or not isinstance(entry.get("request"), str):
        raise SystemExit(f"Invalid functional request mapping for {case_id}: {mapping_path}")
    return package_file(mapping_path.parent, entry["request"])


def case_prompt(profile: dict[str, Any], case: dict[str, Any]) -> str:
    prompt_kind = str(case["prompt_kind"])
    prompt_index = int(case["prompt_index"])
    prompts = profile.get(f"{prompt_kind}_prompts", [])
    if prompt_index < 0 or prompt_index >= len(prompts):
        raise SystemExit(
            f"Validation case {case['id']} references missing {prompt_kind} prompt {prompt_index}"
        )
    return str(prompts[prompt_index])


def frontend_instructions(
    matrix: dict[str, Any],
    frontend_profile_id: str,
) -> str:
    if not frontend_profile_id or frontend_profile_id == "none":
        return ""
    for profile in matrix.get("chatbot_frontend_instruction_profiles", []):
        if profile.get("id") != frontend_profile_id:
            continue
        source_path = str(profile.get("source_path") or "")
        if not source_path:
            raise SystemExit(
                f"Frontend profile '{frontend_profile_id}' has no generated source path"
            )
        path = (validation.REPO_ROOT / source_path).resolve()
        if not path.is_file():
            raise SystemExit(f"Frontend instruction file does not exist: {path}")
        return path.read_text(encoding="utf-8").strip()
    raise SystemExit(f"Frontend profile is not in the installed matrix: {frontend_profile_id}")


def render_request(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    store = scenario_local.LocalScenarioStore()
    profile_path, profile = validation.installed_scenario_entry(store, args.scenario)
    matrix = validation.installed_matrix(store)
    case = validation_case(profile, args.case_id)
    case_action = str(case["action"])
    if case_action != args.action:
        raise SystemExit(
            f"Validation case '{args.case_id}' uses action '{case_action}', not '{args.action}'"
        )
    path_config = validation.scenario_action_configs(
        matrix, args.scenario, [args.action]
    )[0]
    template_path = request_mapping(profile_path.parent, args.scenario, args.case_id)
    body = validation.load_json(template_path)
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise SystemExit(f"Functional request is missing messages: {template_path}")
    prompt = case_prompt(profile, case)
    if not any(
        isinstance(message, dict)
        and message.get("role") == "user"
        and message.get("content") == prompt
        for message in messages
    ):
        raise SystemExit(
            f"Functional request does not contain the exact metadata prompt for {args.case_id}"
        )
    if any(
        isinstance(message, dict) and message.get("role") == "system"
        for message in messages
    ):
        raise SystemExit(
            f"Functional request templates must not embed frontend instructions: {template_path}"
        )
    frontend_profile = str(path_config["frontend_instruction_profile"] or "none")
    frontend_text = frontend_instructions(matrix, frontend_profile)
    if frontend_text:
        messages.insert(0, {"role": "system", "content": frontend_text})
    body["model"] = str(path_config["model"])

    route = next(
        (
            route
            for route in matrix.get("chatbot_faig_static_routes", [])
            if route.get("name") == path_config["route"]
        ),
        None,
    )
    if not route:
        raise SystemExit(f"Generated FAIG route not found: {path_config['route']}")
    base_path = str(route["base_path"])
    metadata = {
        "scenario": args.scenario,
        "action": args.action,
        "case": args.case_id,
        "expected_result": str(case["expected_result"]),
        "required_tools": list(case.get("required_tools", [])),
        "forbidden_tools": list(case.get("forbidden_tools", [])),
        "faig_route": path_config["route"],
        "request_path": f"{base_path}/chat/completions",
        "model_alias": path_config["model"],
        "mcp_transport": path_config["mcp_path"],
        "tool_profile": path_config["tool_profile"] or "disabled",
        "frontend_instruction_profile": frontend_profile,
        "template": validation.display_path(template_path),
    }
    return body, metadata


def curl_command(
    body_path: Path,
    request_path: str,
    *,
    base_url: str,
    authenticated: bool,
) -> str:
    if base_url:
        url = shlex.quote(f"{base_url.rstrip('/')}{request_path}")
    else:
        url = f'"${{FAIG_BASE_URL%/}}{request_path}"'
    parts = [
        "curl --fail-with-body --silent --show-error \\",
        "  -H 'Content-Type: application/json' \\",
    ]
    if authenticated:
        parts.append('  -H "Authorization: Bearer $FAIG_API_KEY" \\')
    parts.extend(
        [
            f"  --data-binary @{shlex.quote(validation.display_path(body_path))} \\",
            f"  {url}",
        ]
    )
    return "\n".join(parts)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render one operator-shell curl request from installed validation metadata."
    )
    parser.add_argument("--scenario", required=True, help="Installed scenario ID.")
    parser.add_argument("--action", required=True, help="Scenario action such as alert, deny, or redact.")
    parser.add_argument("--case", required=True, dest="case_id", help="Validation case ID from profile.json.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Rendered JSON path. Defaults below functional_test/output/rendered-curl/.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional literal FortiAIGate base URL. The generated command uses $FAIG_BASE_URL when omitted.",
    )
    parser.add_argument(
        "--authenticated",
        action="store_true",
        help="Add the optional Authorization header using $FAIG_API_KEY.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    body, metadata = render_request(args)
    output_path = args.output or (
        DEFAULT_OUTPUT_ROOT
        / args.scenario
        / f"{args.case_id}-{args.action}.json"
    )
    output_path = output_path if output_path.is_absolute() else validation.REPO_ROOT / output_path
    validation.write_json(output_path, body)

    print(
        f"scenario={metadata['scenario']} action={metadata['action']} "
        f"case={metadata['case']} expected={metadata['expected_result']}"
    )
    print(
        f"route={metadata['faig_route']} model={metadata['model_alias']} "
        f"mcp={metadata['mcp_transport']} tools={metadata['tool_profile']} "
        f"frontend={metadata['frontend_instruction_profile']}"
    )
    print(f"body: {validation.display_path(output_path)}")
    if not args.base_url:
        print("Set FAIG_BASE_URL to the FortiAIGate API origin before running:")
        print("  export FAIG_BASE_URL=https://<fortiaigate-host>")
    if args.authenticated:
        print("Authenticated variant selected; keep FAIG_API_KEY only in ignored local configuration.")
    print(curl_command(
        output_path,
        metadata["request_path"],
        base_url=args.base_url,
        authenticated=args.authenticated,
    ))
    print(
        "This direct-flow request does not prove chatbot profile selection, live MCP execution, "
        "FortiWeb transport, or multi-round stop-before-tool behavior."
    )
    return 0
