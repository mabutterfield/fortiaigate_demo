#!/usr/bin/env python3
"""Generate local-safe chatbot/MCP traffic for FortiAIGate demo recordings."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import ipaddress
import json
import math
import random
import re
import shlex
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import scenario_local
    import scenario_matrix
    import scenario_profiles
    import scenario_test_harness
except ModuleNotFoundError:
    from scripts import (
        scenario_local,
        scenario_matrix,
        scenario_profiles,
        scenario_test_harness,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_CATALOG = REPO_ROOT / "chatbot" / "scenarios" / "examples" / "catalog.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "docs" / "raw-output" / "traffic"
LOCAL_GENERATED_VARS = REPO_ROOT / "ansible" / "group_vars" / "local.generated.yml"
AWS_EC2_TERRAFORM_PATH = REPO_ROOT / "terraform" / "aws-ec2-k3s"
POD_PATH_TEST_BASE_URL = "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local"
PATH_TEST_CLIENT = r"""
import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
model = sys.argv[2]
prompt = sys.argv[3]
timeout = int(sys.argv[4])
payload = json.dumps(
    {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    },
    separators=(",", ":"),
).encode("utf-8")
request = urllib.request.Request(
    url,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
result = {"url": url, "model": model}
try:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
        result.update({"ok": 200 <= response.status < 300, "status": response.status, "body": body[:2000]})
except urllib.error.HTTPError as error:
    body = error.read().decode("utf-8", "replace")
    result.update({"ok": False, "status": error.code, "body": body[:2000]})
except Exception as error:
    result.update({"ok": False, "status": 0, "error": str(error)})
print(json.dumps(result, sort_keys=True))
"""

ROUTE_CONFIGS = {
    "direct": {
        "provider": "direct",
        "route": "demo-a",
        "mcp_path": None,
        "description": "Direct LiteLLM with selected MCP path",
    },
    "faig-scan": {
        "provider": "faig-static",
        "route": "demo-a",
        "mcp_path": None,
        "description": "FortiAIGate detect/scan route with selected MCP path",
    },
    "faig-protect": {
        "provider": "faig-static",
        "route": "demo-b",
        "mcp_path": None,
        "description": "FortiAIGate protect route with selected MCP path",
    },
    "fortiweb-mcp": {
        "provider": "direct",
        "route": "demo-a",
        "mcp_path": "fortiweb",
        "description": "Direct LiteLLM with FortiWeb-fronted MCP path",
    },
    "fortigate-litellm": {
        "provider": "fortigate-litellm",
        "route": "demo-a",
        "mcp_path": None,
        "description": "Chatbot to FortiGate HTTP listener forwarding to LiteLLM",
    },
    "fortigate-ollama": {
        "provider": "fortigate-ollama",
        "route": "demo-a",
        "mcp_path": None,
        "model": "gpt-oss:20b",
        "description": "Chatbot to FortiGate HTTP listener forwarding to Ollama",
    },
}

SLOT_METADATA_ROOT = REPO_ROOT / "chatbot" / "instructions" / "local"
ROUTE_SLOT_DEFAULTS = {
    "direct": "",
    "fortiweb-mcp": "",
    "fortigate-litellm": "",
    "fortigate-ollama": "demo-a",
    "faig-scan": "demo-a",
    "faig-protect": "demo-a",
}

BASELINE_SCENARIOS = [
    "fortistore-injection",
    "hr-tool-dlp",
]

SCENARIO_FAMILIES = {
    "baseline": BASELINE_SCENARIOS,
    "demo-recording": BASELINE_SCENARIOS,
    "documents": [],
    "hr": ["hr-tool-dlp"],
    "fastfood": ["fastfood-ordering", "menu-poisoning"],
    "support": [],
    "fortinet": ["fortistore-injection"],
    "all": [],
}

LEGACY_PATH_TEST_CASES = [
    {
        "name": "demo-a",
        "path": "/v1/demo-a",
        "model": "demo-a",
        "prompt": "Path test for /v1/demo-a. Reply with only: ok demo-a",
    },
    {
        "name": "demo-b",
        "path": "/v1/demo-b",
        "model": "demo-a",
        "prompt": "Path test for /v1/demo-b. Reply with only: ok demo-b",
    },
    {
        "name": "passthrough",
        "path": "/v1/passthrough",
        "model": "",
        "prompt": "Path test for /v1/passthrough. Reply with only: ok passthrough",
    },
]


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_label() -> str:
    return dt.datetime.now(dt.UTC).strftime("traffic-%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "value"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return data


def installed_runtime() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    store = scenario_local.LocalScenarioStore()
    try:
        scenario_profiles.validate_local_matrix(store)
        matrix = scenario_matrix.build_scenario_matrix(store.matrix_summary())
        profiles = {
            entry["scenario_id"]: load_json(
                store.scenario_path(entry["scenario_id"]) / "profile.json"
            )
            for entry in store.load_state()["installed_scenarios"]
        }
    except (
        OSError,
        scenario_local.LocalScenarioError,
        scenario_matrix.ScenarioMatrixError,
    ) as exc:
        raise SystemExit(str(exc)) from exc
    if not profiles:
        raise SystemExit(
            "No Phase 11 scenarios are installed. Run scenario_profiles.py add first."
        )
    return matrix, profiles


def selected_installed_scenarios(
    args: argparse.Namespace,
    profiles: dict[str, dict[str, Any]],
) -> list[str]:
    explicit = parse_csv_values(args.scenario)
    if explicit:
        unknown = [scenario for scenario in explicit if scenario not in profiles]
        if unknown:
            raise SystemExit(
                "Scenario(s) are not installed: " + ", ".join(unknown)
            )
        return explicit
    if args.scenario_family in {"baseline", "demo-recording", "all"}:
        return sorted(profiles)
    family = SCENARIO_FAMILIES[args.scenario_family]
    selected = [scenario for scenario in family if scenario in profiles]
    if not selected:
        raise SystemExit(
            f"Scenario family '{args.scenario_family}' has no installed scenarios."
        )
    return selected


def matrix_action_configs(
    args: argparse.Namespace,
    matrix: dict[str, Any],
    scenario_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    actions = parse_csv_values(args.action) or ["direct", "alert"]
    return {
        scenario_id: scenario_test_harness.scenario_action_configs(
            matrix,
            scenario_id,
            actions,
        )
        for scenario_id in scenario_ids
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True)
        handle.write("\n")


def catalog_entries() -> dict[str, dict[str, Any]]:
    catalog = load_json(SCENARIO_CATALOG)
    scenarios = catalog.get("scenarios", {})
    if not isinstance(scenarios, dict):
        raise SystemExit("Scenario catalog is missing a scenarios object")
    return {
        scenario_id: entry
        for scenario_id, entry in scenarios.items()
        if entry.get("active", True) is not False
    }


def load_profile(scenario_id: str, entries: dict[str, dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    if scenario_id not in entries:
        available = ", ".join(sorted(entries))
        raise SystemExit(f"Unknown scenario '{scenario_id}'. Available: {available}")
    profile_path = REPO_ROOT / "chatbot" / "scenarios" / "examples" / str(entries[scenario_id]["path"])
    return profile_path, load_json(profile_path)


def parse_csv_values(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in value.split(","):
            item = item.strip()
            if item:
                result.append(item)
    return result


def selected_family_scenarios(args: argparse.Namespace, entries: dict[str, dict[str, Any]]) -> list[str]:
    explicit = parse_csv_values(args.scenario)
    if explicit:
        unknown = [scenario for scenario in explicit if scenario not in entries]
        if unknown:
            raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
        return explicit
    family = args.scenario_family
    if family == "all":
        selected = sorted(entries)
    else:
        scenarios = SCENARIO_FAMILIES[family]
        selected = [scenario for scenario in scenarios if scenario in entries]
    if not selected:
        raise SystemExit(
            f"Scenario family '{family}' has no active scenarios. "
            "Reactivate a catalog entry or pass an active --scenario."
        )
    return selected


def slot_metadata(slot: str) -> dict[str, Any]:
    path = SLOT_METADATA_ROOT / slot / "metadata.json"
    if not path.exists():
        raise SystemExit(
            f"Missing local instruction metadata for slot {slot}: {path}. "
            "Install a scenario into that slot or pass --scenario explicitly."
        )
    data = load_json(path)
    scenario_id = str(data.get("scenario_id", "")).strip()
    if not scenario_id:
        raise SystemExit(
            f"Slot {slot} does not declare scenario_id in {path}. "
            "Install a scenario profile or pass --scenario explicitly."
        )
    return data


def slot_for_route(args: argparse.Namespace, route: str) -> str:
    configured = ROUTE_SLOT_DEFAULTS[route]
    if configured:
        return configured
    compatibility_model = args.model or "demo-a"
    if compatibility_model in {"demo-a", "demo-b"}:
        return compatibility_model
    raise SystemExit(
        f"Route {route} uses model/profile {args.model}, which is not a local scenario slot. "
        "Pass --scenario explicitly or use --model demo-a/demo-b."
    )


def active_slot_scenarios(args: argparse.Namespace, routes: list[str], entries: dict[str, dict[str, Any]]) -> dict[str, str]:
    route_scenarios: dict[str, str] = {}
    for route in routes:
        slot = slot_for_route(args, route)
        metadata = slot_metadata(slot)
        scenario_id = str(metadata["scenario_id"])
        if scenario_id not in entries:
            raise SystemExit(f"Slot {slot} references unknown scenario: {scenario_id}")
        route_scenarios[route] = scenario_id
    return route_scenarios


def prompt_choices(profile: dict[str, Any], traffic_profile: str) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    clean_prompts = [str(prompt) for prompt in profile.get("clean_prompts", [])]
    attack_prompts = [str(prompt) for prompt in profile.get("attack_prompts", [])]
    if traffic_profile in {"clean", "mixed"}:
        for index, prompt in enumerate(clean_prompts):
            weight = 7 if traffic_profile == "mixed" else 1
            choices.append({"kind": "clean", "index": index, "prompt": prompt, "weight": weight})
    if traffic_profile in {"attack", "mixed"}:
        for index, prompt in enumerate(attack_prompts):
            weight = 3 if traffic_profile == "mixed" else 1
            choices.append({"kind": "attack", "index": index, "prompt": prompt, "weight": weight})
    if not choices and traffic_profile == "mixed":
        for index, prompt in enumerate(clean_prompts or attack_prompts):
            kind = "clean" if clean_prompts else "attack"
            choices.append({"kind": kind, "index": index, "prompt": prompt, "weight": 1})
    if not choices:
        raise SystemExit(f"Scenario {profile.get('id')} has no prompts for traffic profile {traffic_profile}")
    return choices


def weighted_choice(rng: random.Random, choices: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(choice.get("weight", 1)) for choice in choices)
    pick = rng.uniform(0, total)
    seen = 0.0
    for choice in choices:
        seen += int(choice.get("weight", 1))
        if pick <= seen:
            return choice
    return choices[-1]


def request_count(duration_seconds: int, rate_per_minute: float) -> int:
    if duration_seconds < 1:
        raise SystemExit("--duration must be at least 1 second")
    if rate_per_minute <= 0:
        raise SystemExit("--rate must be greater than 0 requests per minute")
    return max(1, math.ceil(duration_seconds * rate_per_minute / 60.0))


def apply_use_case_defaults(args: argparse.Namespace) -> None:
    if args.use_case == "steady":
        args.duration = args.duration if args.duration is not None else 60
        args.rate = args.rate if args.rate is not None else 6.0
        args.concurrency = args.concurrency if args.concurrency is not None else 1
    elif args.use_case == "burst":
        args.duration = args.duration if args.duration is not None else 30
        args.rate = args.rate if args.rate is not None else 120.0
        args.concurrency = args.concurrency if args.concurrency is not None else 4
    else:
        raise SystemExit(f"Unknown --use-case {args.use_case}")


def selected_routes(args: argparse.Namespace) -> list[str]:
    routes = parse_csv_values(args.route) or ["faig-scan"]
    unknown_routes = [route for route in routes if route not in ROUTE_CONFIGS]
    if unknown_routes:
        raise SystemExit(f"Unknown route(s): {', '.join(unknown_routes)}")
    return routes


def build_plan(
    args: argparse.Namespace,
    profiles: dict[str, dict[str, Any]],
    route_scenarios: dict[str, str] | None = None,
    path_configs_by_scenario: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(args.seed)
    scenarios = list(profiles)
    routes = selected_routes(args) if path_configs_by_scenario is None else []
    choices_by_scenario = {
        scenario: prompt_choices(profile, args.traffic_profile)
        for scenario, profile in profiles.items()
    }
    total = request_count(args.duration, args.rate)
    lanes = [
        (scenario_id, path_config)
        for scenario_id, path_configs in (path_configs_by_scenario or {}).items()
        for path_config in path_configs
    ]
    plan: list[dict[str, Any]] = []
    for index in range(total):
        if lanes:
            scenario_id, path_config = rng.choice(lanes)
            route = path_config["action"]
        else:
            route = rng.choice(routes)
            scenario_id = route_scenarios[route] if route_scenarios else rng.choice(scenarios)
            legacy_route = ROUTE_CONFIGS[route]
            path_config = {
                "action": route,
                "provider": legacy_route["provider"],
                "route": legacy_route["route"],
                "model": str(legacy_route.get("model") or args.model or "demo-a"),
                "mcp_enabled": True,
                "mcp_path": legacy_route["mcp_path"] or args.mcp_path or "direct",
                "tool_profile": "",
                "max_tool_rounds": args.max_tool_rounds or 3,
                "frontend_instruction_profile": args.frontend_profile,
                "description": legacy_route["description"],
            }
        prompt_choice = weighted_choice(rng, choices_by_scenario[scenario_id])
        profile = profiles[scenario_id]
        tool_profile = (
            args.tool_profile
            or path_config["tool_profile"]
            or (
                str(profile.get("mcp", {}).get("tool_profile") or scenario_id)
                if path_config["mcp_enabled"]
                else ""
            )
        )
        plan.append(
            {
                "request_id": f"req-{index + 1:05d}",
                "scenario": scenario_id,
                "route": route,
                "path_config": path_config,
                "prompt_kind": prompt_choice["kind"],
                "prompt_index": prompt_choice["index"],
                "prompt_id": f"{prompt_choice['kind']}-{prompt_choice['index'] + 1:02d}",
                "prompt": prompt_choice["prompt"],
                "tool_profile": tool_profile,
            }
        )
    return plan


def parse_inventory(path: Path, host_alias: str = "") -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"Inventory does not exist: {path}")
    first_host: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        parts = shlex.split(line)
        if not parts:
            continue
        alias = parts[0]
        values: dict[str, str] = {"alias": alias}
        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            values[key] = value
        values.setdefault("ansible_host", alias)
        values.setdefault("ansible_user", "ubuntu")
        if host_alias and alias == host_alias:
            return values
        if first_host is None:
            first_host = values
    if host_alias:
        raise SystemExit(f"Host alias '{host_alias}' not found in {path}")
    if first_host:
        return first_host
    raise SystemExit(f"No inventory hosts found in {path}")


def ssh_base(inventory_host: dict[str, str]) -> list[str]:
    target = f"{inventory_host.get('ansible_user', 'ubuntu')}@{inventory_host['ansible_host']}"
    command = ["ssh", "-o", "StrictHostKeyChecking=no"]
    key_file = inventory_host.get("ansible_ssh_private_key_file", "").strip()
    if key_file:
        command.extend(["-i", str(Path(key_file).expanduser())])
    command.append(target)
    return command


def simple_yaml_scalar(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    pattern = re.compile(rf"^{re.escape(key)}:\s*['\"]?([^'\"#\n]+)")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(raw_line.strip())
        if match:
            return match.group(1).strip()
    return ""


def terraform_output_raw(terraform_path: Path, output_name: str) -> str:
    result = subprocess.run(
        ["terraform", f"-chdir={terraform_path}", "output", "-raw", output_name],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def remote_agent_command(args: argparse.Namespace, item: dict[str, Any]) -> list[str]:
    path_config = item["path_config"]
    mcp_path = args.mcp_path or path_config["mcp_path"]
    model = args.model or path_config["model"]
    remote_parts = [
        "sudo",
        "kubectl",
        "-n",
        args.chatbot_namespace,
        "exec",
        f"deployment/{args.chatbot_deployment}",
        "--",
        "python",
        "/app/agent_probe.py",
        "--prompt",
        item["prompt"],
        "--provider",
        path_config["provider"],
        "--model",
        model,
        "--mcp-path",
        mcp_path,
        "--max-tool-rounds",
        str(args.max_tool_rounds or path_config["max_tool_rounds"]),
        "--temperature",
        str(args.temperature),
        "--max-tokens",
        str(args.max_tokens),
    ]
    if path_config["route"]:
        remote_parts.extend(["--route", path_config["route"]])
    if not path_config["mcp_enabled"]:
        remote_parts.append("--no-mcp")
    if args.agent_probe_supports_tool_profile and item["tool_profile"]:
        remote_parts.extend(["--tool-profile", item["tool_profile"]])
    frontend_profile = (
        args.frontend_profile
        or path_config["frontend_instruction_profile"]
    )
    if frontend_profile:
        remote_parts.extend(["--frontend-profile", frontend_profile])
    return remote_parts


def agent_probe_supports_option(args: argparse.Namespace, inventory_host: dict[str, str], option: str) -> bool:
    remote_parts = [
        "sudo",
        "kubectl",
        "-n",
        args.chatbot_namespace,
        "exec",
        f"deployment/{args.chatbot_deployment}",
        "--",
        "python",
        "/app/agent_probe.py",
        "--help",
    ]
    remote = " ".join(shlex.quote(part) for part in remote_parts)
    result = subprocess.run(
        [*ssh_base(inventory_host), remote],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0 and option in f"{result.stdout}\n{result.stderr}"


def run_agent_probe(args: argparse.Namespace, inventory_host: dict[str, str], item: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    remote = " ".join(shlex.quote(part) for part in remote_agent_command(args, item))
    command = [*ssh_base(inventory_host), remote]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    if result.returncode != 0:
        return {
            "status": "error",
            "error_class": "agent_probe_failed",
            "returncode": result.returncode,
            "latency_ms": latency_ms,
            "response_length": 0,
            "tool_names": [],
            "tool_count": 0,
        }
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error_class": "agent_probe_non_json",
            "returncode": result.returncode,
            "latency_ms": latency_ms,
            "response_length": len(result.stdout or ""),
            "tool_names": [],
            "tool_count": 0,
        }
    reply = str(body.get("reply", ""))
    security_disposition = classify_security_disposition(reply)
    tool_events = body.get("tool_events", [])
    tool_names = [
        str(event.get("tool") or event.get("name"))
        for event in tool_events
        if isinstance(event, dict) and (event.get("tool") or event.get("name"))
    ]
    return {
        "status": "ok",
        "error_class": "",
        "returncode": 0,
        "latency_ms": latency_ms,
        "response_length": len(reply),
        "security_disposition": security_disposition,
        "agent_base_url": str(body.get("base_url", "")),
        "agent_mcp_base_url": str(body.get("mcp_base_url", "")),
        "agent_model": str(body.get("model", "")),
        "tool_names": tool_names,
        "tool_count": len(tool_names),
    }


def classify_security_disposition(reply: str) -> str:
    lower_reply = reply.lower()
    redacted_markers = [
        "<email>",
        "<ssn>",
        "<phone_number>",
        "<account_number>",
        "<date_of_birth>",
        "[redacted]",
        "redacted",
        "masked",
    ]
    blocked_markers = [
        "blocked",
        "denied",
        "security policy",
        "cannot process",
        "fortiaigate has detected",
        "request was rejected",
    ]
    if any(marker in lower_reply for marker in blocked_markers):
        return "blocked"
    if any(marker in lower_reply for marker in redacted_markers):
        return "redacted"
    return "allowed"


def endpoint_host(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"http://{value}")
    return parsed.hostname or ""


def host_is_public(host: str) -> bool:
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        lowered = host.lower()
        if lowered in {"localhost"} or lowered.endswith(".local") or lowered.endswith(".lan"):
            return False
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError:
            return True
        addresses = {info[4][0] for info in infos}
        return any(host_is_public(address) for address in addresses)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def cloud_guard(args: argparse.Namespace, plan: list[dict[str, Any]]) -> None:
    host = endpoint_host(args.endpoint)
    endpoint_public = host_is_public(host) if host else False
    cloud_target = args.target == "aws" or endpoint_public
    long_run = args.duration > 120 or args.rate > 10 or args.concurrency > 1 or len(plan) > 20
    if args.dry_run:
        if cloud_target and long_run and not args.allow_cloud_long_run:
            print("dry-run warning: this public/cloud plan would require --allow-cloud-long-run to execute")
        return
    if cloud_target and long_run and not args.allow_cloud_long_run:
        raise SystemExit(
            "Refusing a long or high-rate public/cloud traffic run. "
            "Use --allow-cloud-long-run only after confirming expected model/API cost and log volume."
        )
    interactive_long = args.duration >= 300 or len(plan) >= 50
    if interactive_long and not args.yes and not args.dry_run:
        if not sys.stdin.isatty():
            raise SystemExit("Long traffic run requires --yes in non-interactive shells.")
        response = input(f"Run {len(plan)} requests over {args.duration}s? Type 'yes' to continue: ")
        if response.strip().lower() != "yes":
            raise SystemExit("Traffic run cancelled.")


def print_plan(args: argparse.Namespace, plan: list[dict[str, Any]], profiles: dict[str, dict[str, Any]]) -> None:
    print(f"target: {args.target}")
    print(f"run_label: {args.run_label}")
    print(f"use_case: {args.use_case}")
    print(f"duration_seconds: {args.duration}")
    print(f"rate_per_minute: {args.rate}")
    print(f"concurrency: {args.concurrency}")
    print(f"estimated_requests: {len(plan)}")
    print(f"output: {display_path(args.output_dir)}")
    print(f"scenario_source: {args.scenario_source}")
    by_scenario = Counter(item["scenario"] for item in plan)
    by_route = Counter(item["route"] for item in plan)
    by_prompt_kind = Counter(item["prompt_kind"] for item in plan)
    print("scenario_mix:")
    for scenario, count in sorted(by_scenario.items()):
        display = profiles[scenario].get("display_name", scenario)
        print(f"  {scenario}: {count} ({display})")
    print("route_mix:")
    for route, count in sorted(by_route.items()):
        scenario_note = ""
        route_scenarios = sorted({item["scenario"] for item in plan if item["route"] == route})
        if route_scenarios:
            scenario_note = f" scenarios={','.join(route_scenarios)}"
        print(f"  {route}: {count}{scenario_note}")
    print("prompt_kind_mix:")
    for kind, count in sorted(by_prompt_kind.items()):
        print(f"  {kind}: {count}")
    if args.dry_run:
        print("planned_requests:")
        for item in plan[: min(25, len(plan))]:
            preview = item["prompt"].replace("\n", " ")[:100]
            print(
                f"  {item['request_id']} {item['scenario']} {item['route']} "
                f"{item['prompt_id']} tool_profile={item['tool_profile']} prompt={preview!r}"
            )
        if len(plan) > 25:
            print(f"  ... {len(plan) - 25} more")


def event_from_result(args: argparse.Namespace, item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    path_config = item["path_config"]
    mcp_path = args.mcp_path or path_config["mcp_path"]
    return {
        "timestamp": now_iso(),
        "request_id": item["request_id"],
        "run_label": args.run_label,
        "target": args.target,
        "use_case": args.use_case,
        "endpoint_type": "provided" if args.endpoint else "chatbot-pod-agent-probe",
        "endpoint": args.endpoint,
        "route": item["route"],
        "action": path_config["action"],
        "provider": path_config["provider"],
        "provider_route": path_config["route"],
        "traffic_profile": args.traffic_profile,
        "scenario_id": item["scenario"],
        "prompt_id": item["prompt_id"],
        "prompt_kind": item["prompt_kind"],
        "model_alias": args.model or path_config["model"],
        "agent_model": result.get("agent_model", ""),
        "agent_base_url": result.get("agent_base_url", ""),
        "mcp_enabled": path_config["mcp_enabled"],
        "mcp_path": mcp_path,
        "agent_mcp_base_url": result.get("agent_mcp_base_url", ""),
        "mcp_tool_profile": item["tool_profile"],
        "observed_tool_names": result["tool_names"],
        "observed_tool_count": result["tool_count"],
        "http_status": None,
        "completion_status": result["status"],
        "latency_ms": result["latency_ms"],
        "approx_response_length": result["response_length"],
        "error_class": result["error_class"],
        "security_disposition": result.get("security_disposition", "unknown"),
    }


def write_run_summary(
    args: argparse.Namespace,
    plan: list[dict[str, Any]],
    events: list[dict[str, Any]],
    started_at: str,
    status: str,
) -> None:
    completed = [event for event in events if event["completion_status"] == "ok"]
    errors = [event for event in events if event["completion_status"] != "ok"]
    latencies = [event["latency_ms"] for event in completed]
    summary = {
        "started_at": started_at,
        "completed_at": now_iso(),
        "status": status,
        "run_label": args.run_label,
        "target": args.target,
        "duration_seconds": args.duration,
        "rate_per_minute": args.rate,
        "concurrency": args.concurrency,
        "seed": args.seed,
        "traffic_profile": args.traffic_profile,
        "use_case": args.use_case,
        "actions": sorted({item["path_config"]["action"] for item in plan}),
        "model_alias": args.model,
        "mcp_path": args.mcp_path,
        "planned_requests": len(plan),
        "completed_requests": len(completed),
        "error_requests": len(errors),
        "latency_ms_min": min(latencies) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "latency_ms_avg": int(sum(latencies) / len(latencies)) if latencies else None,
        "scenario_counts": dict(Counter(item["scenario"] for item in plan)),
        "route_counts": dict(Counter(item["route"] for item in plan)),
        "prompt_kind_counts": dict(Counter(item["prompt_kind"] for item in plan)),
        "observed_tool_counts": dict(Counter(tool for event in events for tool in event["observed_tool_names"])),
        "security_disposition_counts": dict(Counter(event["security_disposition"] for event in events)),
        "error_counts": dict(Counter(event["error_class"] for event in errors)),
        "raw_prompt_response_saved": False,
        "events_file": None if args.summary_only else display_path(args.output_dir / "events.jsonl"),
    }
    write_json(args.output_dir / "summary.json", summary)


def run_traffic(args: argparse.Namespace, plan: list[dict[str, Any]], profiles: dict[str, dict[str, Any]]) -> None:
    started_at = now_iso()
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite_output:
        raise SystemExit(f"Output directory already exists and is not empty: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        args.output_dir / "plan.json",
        {
            "created_at": started_at,
            "run_label": args.run_label,
            "target": args.target,
            "duration_seconds": args.duration,
            "rate_per_minute": args.rate,
            "concurrency": args.concurrency,
            "seed": args.seed,
            "traffic_profile": args.traffic_profile,
            "use_case": args.use_case,
            "requests": [
                {
                    key: item[key]
                    for key in (
                        "request_id",
                        "scenario",
                        "route",
                        "prompt_kind",
                        "prompt_id",
                        "tool_profile",
                    )
                }
                | {
                    "provider": item["path_config"]["provider"],
                    "provider_route": item["path_config"]["route"],
                    "model": item["path_config"]["model"],
                    "mcp_enabled": item["path_config"]["mcp_enabled"],
                    "mcp_path": item["path_config"]["mcp_path"],
                    "frontend_instruction_profile": item["path_config"]["frontend_instruction_profile"],
                }
                for item in plan
            ],
        },
    )
    inventory_host = parse_inventory(args.inventory, args.host_alias)
    args.agent_probe_supports_tool_profile = agent_probe_supports_option(args, inventory_host, "--tool-profile")
    if not args.agent_probe_supports_tool_profile:
        print(
            "warning: deployed /app/agent_probe.py does not support --tool-profile; "
            "scenario prompts will run with the chatbot's default MCP tool profile. "
            "Rebuild/redeploy the chatbot image to enable per-scenario MCP tool selection.",
            file=sys.stderr,
        )
    interval = 60.0 / args.rate
    next_send = time.monotonic()
    events: list[dict[str, Any]] = []
    futures: list[concurrent.futures.Future[tuple[dict[str, Any], dict[str, Any]]]] = []
    interrupted = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        try:
            for item in plan:
                sleep_for = next_send - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                next_send += interval
                futures.append(executor.submit(lambda planned=item: (planned, run_agent_probe(args, inventory_host, planned))))
            for future in concurrent.futures.as_completed(futures):
                item, result = future.result()
                event = event_from_result(args, item, result)
                events.append(event)
                if not args.summary_only:
                    append_jsonl(args.output_dir / "events.jsonl", event)
                print(
                    f"{event['request_id'] if 'request_id' in event else item['request_id']} "
                    f"{event['scenario_id']} {event['route']} {event['completion_status']} "
                    f"tools={event['observed_tool_names']} latency_ms={event['latency_ms']}",
                    flush=True,
                )
        except KeyboardInterrupt:
            interrupted = True
            for future in futures:
                future.cancel()
            print("Interrupted; writing partial summary.", file=sys.stderr)
    write_run_summary(args, plan, events, started_at, "interrupted" if interrupted else "completed")
    print(f"summary: {display_path(args.output_dir / 'summary.json')}")


def path_test_passthrough_model(args: argparse.Namespace) -> str:
    if args.path_test_passthrough_model:
        return args.path_test_passthrough_model
    return "pass-model"


def inferred_path_test_base_url(args: argparse.Namespace) -> str:
    if args.path_test_execution == "chatbot-pod":
        return POD_PATH_TEST_BASE_URL
    if args.target == "local":
        host = simple_yaml_scalar(LOCAL_GENERATED_VARS, "k3s_public_ip")
        if not host:
            host = parse_inventory(args.inventory, args.host_alias).get("ansible_host", "")
        if host:
            return f"https://{host}"
    public_ip = terraform_output_raw(AWS_EC2_TERRAFORM_PATH, "public_ip")
    if public_ip:
        return f"https://{public_ip}"
    host = parse_inventory(args.inventory, args.host_alias).get("ansible_host", "")
    return f"https://{host}" if host else ""


def path_test_base_url(args: argparse.Namespace) -> str:
    value = args.path_test_base_url or args.endpoint or inferred_path_test_base_url(args)
    if not value:
        raise SystemExit("Unable to infer path_test base URL. Pass --path-test-base-url or --endpoint.")
    return value.rstrip("/")


def path_test_url(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if base_url.rstrip("/").endswith("/v1") and normalized_path.startswith("/v1/"):
        normalized_path = normalized_path[3:]
    return f"{base_url.rstrip('/')}{normalized_path.rstrip('/')}/chat/completions"


def path_test_cases(
    args: argparse.Namespace,
    matrix: dict[str, Any],
) -> list[dict[str, str]]:
    if args.legacy_routes:
        base_cases = LEGACY_PATH_TEST_CASES
    else:
        base_cases = [
            {
                "name": str(route["name"]),
                "path": str(route["base_path"]),
                "action": str(route.get("action") or route["name"]),
                "model": str(route.get("model") or "pass-model"),
                "prompt": (
                    f"Path test for {route['base_path']}. "
                    f"Reply with only: ok {route['name']}"
                ),
            }
            for route in matrix.get("chatbot_faig_static_routes", [])
        ]
    requested = parse_csv_values(args.path_test_path)
    cases = base_cases
    if requested:
        requested_names = {item.strip() for item in requested}
        cases = [
            case
            for case in base_cases
            if case["path"] in requested_names
            or case["name"] in requested_names
            or case.get("action") in requested_names
        ]
        matched = {
            requested_name
            for requested_name in requested_names
            if any(
                requested_name
                in {case["path"], case["name"], case.get("action")}
                for case in cases
            )
        }
        missing = sorted(requested_names - matched)
        if missing:
            raise SystemExit(f"Unknown path test path(s): {', '.join(missing)}")
    passthrough_model = path_test_passthrough_model(args)
    return [
        {
            **case,
            "model": case["model"] or passthrough_model,
            "url": path_test_url(path_test_base_url(args), case["path"]),
        }
        for case in cases
    ]


def split_http_status(stdout: str) -> tuple[str, int]:
    marker = "\n__HTTP_STATUS__:"
    if marker not in stdout:
        return stdout, 0
    body, status = stdout.rsplit(marker, 1)
    return body, int(status.strip()) if status.strip().isdigit() else 0


def run_path_test_case_direct(args: argparse.Namespace, case: dict[str, str]) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": case["model"],
            "messages": [{"role": "user", "content": case["prompt"]}],
        },
        separators=(",", ":"),
    )
    command = [
        "curl",
        "-sS",
        "--max-time",
        str(args.path_test_timeout),
        "-w",
        "\n__HTTP_STATUS__:%{http_code}",
        "-X",
        "POST",
        case["url"],
        "-H",
        "Content-Type: application/json",
        "--data-binary",
        payload,
    ]
    if not args.path_test_verify_tls:
        command.insert(1, "-k")
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "status": 0,
            "url": case["url"],
            "model": case["model"],
            "error": "curl is required for direct path_test execution",
        }
    body, status = split_http_status(result.stdout)
    return {
        "ok": result.returncode == 0 and 200 <= status < 300,
        "status": status,
        "url": case["url"],
        "model": case["model"],
        "body": body[:2000],
        "error": result.stderr.strip()[:1000],
    }


def run_path_test_case_in_pod(args: argparse.Namespace, inventory_host: dict[str, str], case: dict[str, str]) -> dict[str, Any]:
    remote_parts = [
        "sudo",
        "kubectl",
        "-n",
        args.chatbot_namespace,
        "exec",
        f"deployment/{args.chatbot_deployment}",
        "--",
        "python",
        "-c",
        PATH_TEST_CLIENT,
        case["url"],
        case["model"],
        case["prompt"],
        str(args.path_test_timeout),
    ]
    remote = " ".join(shlex.quote(part) for part in remote_parts)
    result = subprocess.run(
        [*ssh_base(inventory_host), remote],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "status": 0,
            "url": case["url"],
            "model": case["model"],
            "error": (result.stderr or result.stdout).strip()[:1000],
        }
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": 0,
            "url": case["url"],
            "model": case["model"],
            "error": f"non-json path test output: {(result.stdout or '').strip()[:1000]}",
        }
    return data


def run_path_test_case(args: argparse.Namespace, inventory_host: dict[str, str] | None, case: dict[str, str]) -> dict[str, Any]:
    if args.path_test_execution == "direct":
        return run_path_test_case_direct(args, case)
    if inventory_host is None:
        raise SystemExit("chatbot-pod path_test execution requires an inventory host")
    return run_path_test_case_in_pod(args, inventory_host, case)


def path_test_response_preview(result: dict[str, Any]) -> str:
    body = str(result.get("body", ""))
    if not body:
        return str(result.get("error", ""))[:160]
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:160]
    choices = data.get("choices") if isinstance(data, dict) else None
    if choices and isinstance(choices, list):
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"]).replace("\n", " ")[:160]
            if first.get("text"):
                return str(first["text"]).replace("\n", " ")[:160]
    if isinstance(data, dict) and data.get("error"):
        return json.dumps(data["error"], sort_keys=True)[:160]
    return json.dumps(data, sort_keys=True)[:160]


def print_path_test_header(args: argparse.Namespace, cases: list[dict[str, str]]) -> None:
    base_url = path_test_base_url(args)
    display_base = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    print(f"target: {args.target}")
    print(f"target base URL: {display_base.rstrip('/')}/")
    print("mode: path_test")
    if args.path_test_execution == "direct":
        print("execution: workstation curl")
    else:
        print(f"execution: {args.chatbot_namespace}/{args.chatbot_deployment} pod via {args.inventory}")
    print("paths: " + ", ".join(case["path"] for case in cases))


def run_path_tests(args: argparse.Namespace) -> int:
    matrix, _profiles = installed_runtime()
    inventory_host = None
    if args.path_test_execution == "chatbot-pod":
        inventory_host = parse_inventory(args.inventory, args.host_alias)
    cases = path_test_cases(args, matrix)
    print_path_test_header(args, cases)
    if args.dry_run:
        print("dry-run: no path requests sent")
        return 0
    print("Results:")
    failed = False
    for case in cases:
        result = run_path_test_case(args, inventory_host, case)
        ok = bool(result.get("ok"))
        failed = failed or not ok
        status = result.get("status", 0)
        preview = path_test_response_preview(result)
        state = "working" if ok else "fail"
        print(f"{case['path']}: {state} (HTTP {status}, model={case['model']})")
        if preview:
            print(f"  response: {preview}")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate FAIG paths and generate local-safe chatbot/MCP scenario traffic.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--mode", choices=["path_test", "traffic"], default="path_test")
    parser.add_argument("--target", choices=["local", "aws"], default="local")
    parser.add_argument("--endpoint", default="", help="Optional endpoint label/URL used for run metadata and public-cloud safeguards.")
    parser.add_argument(
        "--use-case",
        choices=["steady", "burst"],
        default="steady",
        help="Traffic intent. steady is persistent low-rate log/dashboard population; burst is short high-rate load/DoS-style testing.",
    )
    parser.add_argument("--duration", type=int, default=None, help="Run duration in seconds. Defaults by --use-case.")
    parser.add_argument("--rate", type=float, default=None, help="Request start rate per minute. Defaults by --use-case.")
    parser.add_argument("--concurrency", type=int, default=None, help="Concurrent agent probes. Defaults by --use-case.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", action="append", help="Scenario ID. Can be repeated or comma-separated.")
    parser.add_argument(
        "--scenario-source",
        choices=["installed", "active-slot", "family", "explicit"],
        default="installed",
        help="Scenario selection source. installed uses ignored Phase 11 local packages; active-slot is Phase 10 compatibility.",
    )
    parser.add_argument("--scenario-family", choices=sorted(SCENARIO_FAMILIES), default="baseline")
    parser.add_argument("--traffic-profile", choices=["clean", "attack", "mixed"], default="mixed")
    parser.add_argument("--action", action="append", help="Phase 11 action. Can be repeated or comma-separated; defaults to direct and alert.")
    parser.add_argument("--route", action="append", help="Phase 10 compatibility route label. Use --action for Phase 11.")
    parser.add_argument("--model", default="", help="Override the matrix-derived chatbot model alias.")
    parser.add_argument("--mcp-path", choices=["direct", "fortiweb"], default="", help="Override the matrix-derived MCP path.")
    parser.add_argument("--tool-profile", default="", help="Override the matrix-derived MCP tool profile for every request.")
    parser.add_argument("--frontend-profile", default="", help="Override the matrix-derived frontend instruction profile.")
    parser.add_argument("--max-tool-rounds", type=int, default=0, help="Override profile tool rounds; zero uses the matrix value.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--inventory", type=Path, default=None, help="Ansible inventory. Defaults by --target.")
    parser.add_argument("--host-alias", default="", help="Ansible host alias. Empty uses the first inventory host.")
    parser.add_argument("--chatbot-namespace", default="chatbot")
    parser.add_argument("--chatbot-deployment", default="chatbot")
    parser.add_argument("--path-test-base-url", default="", help="Base URL for path_test. Defaults to the target's inferred external FAIG HTTPS endpoint.")
    parser.add_argument("--path-test-execution", choices=["direct", "chatbot-pod"], default="direct")
    parser.add_argument("--path-test-path", action="append", help="Path to test. Can be repeated or comma-separated.")
    parser.add_argument("--legacy-routes", action="store_true", help="Use Phase 10 demo-a/demo-b path-test cases.")
    parser.add_argument("--path-test-timeout", type=int, default=60)
    parser.add_argument("--path-test-passthrough-model", default="", help="Override passthrough model for path_test.")
    parser.add_argument("--path-test-verify-tls", action="store_true", help="Verify TLS certificates for direct path_test curl requests.")
    parser.add_argument("--label", default="", help="Run label. Defaults to a UTC timestamp.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="Print path targets or planned request mix without sending traffic or writing output.")
    parser.add_argument("--summary-only", action="store_true", help="Write only summary.json and plan.json, not events.jsonl.")
    parser.add_argument("--allow-cloud-long-run", action="store_true", help="Explicitly allow long/high-rate public or AWS runs.")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation for long local runs.")
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()
    apply_use_case_defaults(args)
    if args.scenario:
        args.scenario_source = "explicit"
    if args.action and args.route:
        raise SystemExit("Use --action or Phase 10 --route, not both")
    if args.route and args.scenario_source != "active-slot":
        raise SystemExit("Phase 10 --route requires --scenario-source active-slot")
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")
    if args.concurrency > 4:
        raise SystemExit("--concurrency is intentionally capped at 4 for demo safety")
    args.output_root = args.output_root if args.output_root.is_absolute() else REPO_ROOT / args.output_root
    args.run_label = slugify(args.label) if args.label else timestamp_label()
    args.output_dir = args.output_root / args.run_label
    if args.inventory is None:
        inventory_name = "local.generated.ini" if args.target == "local" else "aws.generated.ini"
        args.inventory = REPO_ROOT / "ansible" / "inventory" / inventory_name
    elif not args.inventory.is_absolute():
        args.inventory = REPO_ROOT / args.inventory
    return args


def main() -> int:
    args = parse_args()
    if args.mode == "path_test":
        return run_path_tests(args)
    if args.scenario_source == "active-slot":
        entries = catalog_entries()
        routes = selected_routes(args)
        route_scenarios: dict[str, str] | None = active_slot_scenarios(
            args,
            routes,
            entries,
        )
        scenario_ids = sorted(set(route_scenarios.values()))
        profiles: dict[str, dict[str, Any]] = {}
        for scenario_id in scenario_ids:
            _path, profile = load_profile(scenario_id, entries)
            profiles[scenario_id] = profile
        plan = build_plan(args, profiles, route_scenarios)
    else:
        matrix, installed_profiles = installed_runtime()
        scenario_ids = selected_installed_scenarios(args, installed_profiles)
        profiles = {
            scenario_id: installed_profiles[scenario_id]
            for scenario_id in scenario_ids
        }
        path_configs_by_scenario = matrix_action_configs(
            args,
            matrix,
            scenario_ids,
        )
        plan = build_plan(
            args,
            profiles,
            path_configs_by_scenario=path_configs_by_scenario,
        )
    if not profiles:
        raise SystemExit("No scenarios selected")
    cloud_guard(args, plan)
    print_plan(args, plan, profiles)
    if args.dry_run:
        return 0
    run_traffic(args, plan, profiles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
