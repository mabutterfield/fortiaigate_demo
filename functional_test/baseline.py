"""FortiAIGate 8.0.2 baseline validation without the chatbot.

For each per-student, per-scenario-action virtual key (created by
experiments/faig-api-lab/scenario_lab.py), run the scenario's declared
validation case through FortiAIGate's `/ai/openai/v1` gateway with live tool
calls over the standards MCP endpoint, then check the expected result and
required/forbidden tools with the same contract as `validate`. With
`--admin-credentials`, also read the FAIG Traffic Log and require the verdict
that the action implies (alert -> Alert, deny -> Block, redact -> Redact,
passthrough -> Log).

The agent runs inside the cluster (`baseline_agent.py` in the mcp-standard
container) so it can reach the in-cluster FAIG ingress and MCP service.
Virtual keys are passed on stdin, never on a command line, and are not
written to the output.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import shlex
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from functional_test import validation
from scripts import scenario_local

REPO_ROOT = validation.REPO_ROOT
AGENT_PATH = Path(__file__).with_name("baseline_agent.py")
SHARED_AGENT_PATH = REPO_ROOT / "chatbot" / "agent" / "faig_agent.py"
REMOTE_DIR = "/tmp/faig-baseline"
REMOTE_AGENT_PATH = f"{REMOTE_DIR}/baseline_agent.py"
EXPECTED_LOG_VERDICT = {"alert": "Alert", "deny": "Block", "redact": "Redact", "passthrough": "Log"}
VERDICT_SEVERITY = {"Log": 0, "Alert": 1, "Redact": 2, "Block": 3}
PASSTHROUGH_PROMPT = "Reply with one short sentence confirming you are reachable."


# ------------------------------------------------------------------ planning

def key_files(directories: list[Path]) -> list[dict[str, Any]]:
    keys = []
    for directory in directories:
        if not directory.is_dir() or directory.stat().st_mode & 0o077:
            raise SystemExit(f"Key directory must exist and be owner-only (chmod 700): {directory}")
        for path in sorted(directory.glob("*.json")):
            if path.stat().st_mode & 0o077:
                raise SystemExit(f"Key file must be owner-only: {path}")
            keys.append({**json.loads(path.read_text(encoding="utf-8")), "_path": str(path)})
    return keys


def action_profile(matrix: dict[str, Any], scenario: str, action: str) -> dict[str, Any]:
    """The chatbot profile a user would pick for this scenario action."""
    candidates = [p for p in matrix.get("chatbot_simplified_profiles", [])
                  if p.get("scenario_id") == scenario and p.get("provider_path") == "faig-static"
                  and str(p.get("route", "")).endswith("-" + action)]
    candidates.sort(key=lambda p: (p.get("id") != f"{scenario}-{action}", p.get("id", "")))
    if not candidates:
        raise SystemExit(f"No chatbot profile for {scenario}/{action} in the installed scenario matrix")
    return candidates[0]


def tool_names(matrix: dict[str, Any], profile_name: str) -> list[str]:
    if not profile_name:
        return []
    for profile in matrix.get("chatbot_mcp_tool_profiles", []):
        if profile.get("name") == profile_name:
            return list(profile.get("tools", []))
    raise SystemExit(f"MCP tool profile not found in the installed matrix: {profile_name}")


def frontend_text(matrix: dict[str, Any], profile_id: str) -> str:
    if not profile_id or profile_id == "none":
        return ""
    for profile in matrix.get("chatbot_frontend_instruction_profiles", []):
        if profile.get("id") == profile_id and profile.get("source_type") == "file":
            return (REPO_ROOT / profile["source_path"]).read_text(encoding="utf-8")
    raise SystemExit(f"Frontend instruction profile not found: {profile_id}")


def plan_case(matrix: dict[str, Any], store: Any, key: dict[str, Any]) -> dict[str, Any]:
    scenario, action = key["scenario"], key["action"]
    base = {"key_name": key["keyName"], "student": key.get("student"), "scenario": scenario,
            "action": action, "model": key["model"]}
    if scenario == "passthrough":
        return {**base, "case_id": "passthrough", "prompt": PASSTHROUGH_PROMPT, "system_prompt": "",
                "tools": [], "max_rounds": 0, "expected_result": "completed",
                "required_tools": [], "forbidden_tools": []}
    _, runtime = validation.installed_scenario_entry(store, scenario)
    profile = validation.tracked_validation_profile(scenario, runtime)
    case = next((c for c in profile["validation"]["cases"] if c.get("action") == action), None)
    if case is None:
        raise SystemExit(f"No validation case for {scenario}/{action}")
    prompts = profile.get("attack_prompts" if case.get("prompt_kind") == "attack" else "clean_prompts", [])
    prompt = prompts[int(case.get("prompt_index", 0))]
    prompt = prompt if isinstance(prompt, str) else prompt.get("prompt") or prompt.get("text")
    chat_profile = action_profile(matrix, scenario, action)
    return {**base, "case_id": case["id"], "prompt": prompt,
            "system_prompt": frontend_text(matrix, chat_profile.get("frontend_instruction_profile", "none")),
            "tools": tool_names(matrix, chat_profile.get("mcp_tool_profile", "")) if chat_profile.get("mcp_enabled") else [],
            "max_rounds": int(chat_profile.get("mcp_max_tool_rounds") or 3),
            "expected_result": case.get("expected_result", "completed"),
            "required_tools": list(case.get("required_tools", [])),
            "forbidden_tools": list(case.get("forbidden_tools", []))}


# ------------------------------------------------------------------ execution

class FaigAdmin:
    """Minimal FAIG admin session for reading the Traffic Log."""

    def __init__(self, origin: str, credentials: dict[str, str], insecure: bool):
        self.origin = origin.rstrip("/")
        context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=context))
        body = json.dumps({"username": credentials["username"], "password": credentials["password"]}).encode()
        headers = {"Content-Type": "application/json", "Origin": self.origin, "Referer": self.origin + "/"}
        with self.opener.open(urllib.request.Request(self.origin + "/api/v1/login", data=body, headers=headers,
                                                     method="POST"), timeout=60) as response:
            self.csrf = json.loads(response.read())["csrf_token"]

    def get(self, path: str) -> Any:
        headers = {"X-CSRF-Token": self.csrf, "Origin": self.origin, "Referer": self.origin + "/"}
        with self.opener.open(urllib.request.Request(self.origin + path, headers=headers), timeout=60) as response:
            return json.loads(response.read())

    def verdicts(self, key_name: str, since_ms: int) -> list[str]:
        response = self.get("/api/v1/admin/traffic-logs?limit=100&offset=0")
        rows = response.get("items", response) if isinstance(response, dict) else response
        return [row.get("verdictLabel") for row in rows
                if row.get("keyAlias") == key_name and row.get("timeStamp", 0) >= since_ms]


def kubectl_exec(args: argparse.Namespace, host: dict[str, str], command: list[str], stdin: str) -> subprocess.CompletedProcess:
    remote = " ".join(shlex.quote(p) for p in [
        "sudo", "kubectl", "-n", args.mcp_namespace, "exec", "-i", f"deployment/{args.mcp_deployment}",
        "-c", args.mcp_container, "--", *command])
    return subprocess.run([*validation.ssh_base(host), remote], input=stdin, text=True,
                          capture_output=True, check=False)


def run_case(args: argparse.Namespace, host: dict[str, str], case: dict[str, Any], key: dict[str, Any]) -> dict[str, Any]:
    spec = {"base_url": args.faig_internal_url, "api_key": key["secretKey"], "model": case["model"],
            "prompt": case["prompt"], "system_prompt": case["system_prompt"], "mcp_url": args.mcp_url,
            "tools": case["tools"], "max_rounds": case["max_rounds"], "max_tokens": args.max_tokens,
            "temperature": args.temperature}
    result = kubectl_exec(args, host, ["python", REMOTE_AGENT_PATH], json.dumps(spec))
    if result.returncode != 0:
        return {"error": "agent_exec_failed", "stderr": result.stderr[-600:], "reply": "", "tool_events": []}
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "agent_output_not_json", "stdout": result.stdout[-600:], "reply": "", "tool_events": []}


def judge(case: dict[str, Any], raw: dict[str, Any], verdicts: list[str] | None) -> tuple[bool, list[str], dict]:
    normalized = validation.normalized_live_result(raw)
    item = {"scenario": case["scenario"], "required_tools": case["required_tools"],
            "forbidden_tools": case["forbidden_tools"]}
    ok = validation.result_matches_expected(case["expected_result"], item, normalized)
    details = [] if ok else validation.expectation_failure_details(case["expected_result"], item, normalized)
    if raw.get("error"):
        details.insert(0, f"{raw['error']}: {str(raw.get('detail') or raw.get('stderr') or raw.get('stdout'))[:300]}")
    if verdicts is not None:
        expected = EXPECTED_LOG_VERDICT[case["action"]]
        observed = max(verdicts, key=lambda v: VERDICT_SEVERITY.get(v, -1)) if verdicts else None
        if observed != expected:
            ok = False
            details.append(f"Traffic Log verdict {observed or 'missing'} (rows {verdicts}); expected {expected}")
    return ok, details, normalized


def default_faig_origin(host: dict[str, str]) -> str:
    return "https://" + host["ansible_host"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python3 -m functional_test baseline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inventory", default=os.environ.get("FAIG_INVENTORY", "cloud"))
    parser.add_argument("--host-alias", default=os.environ.get("FAIG_HOST_ALIAS", "faig-aws"))
    parser.add_argument("--key-dir", type=Path, action="append",
                        help="Owner-only studentNN-keys directory from scenario_lab.py (repeatable)")
    parser.add_argument("--scenario", action="append", help="Limit to scenario (repeatable; 'passthrough' allowed)")
    parser.add_argument("--action", action="append", help="Limit to action (repeatable)")
    parser.add_argument("--admin-credentials", type=Path,
                        default=Path(os.environ["FAIG_ENV_DIR"]) / "admin-login.json" if os.environ.get("FAIG_ENV_DIR") else None,
                        help="Owner-only FAIG admin login file; enables Traffic Log verdict checks")
    parser.add_argument("--faig-url", help="Public FAIG HTTPS origin for the admin API (default https://<host>)")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS verification for the admin API (lab only)")
    parser.add_argument("--faig-internal-url",
                        default="http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/ai/openai/v1")
    parser.add_argument("--mcp-url", default="http://mcp-demo.mcp.svc.cluster.local:8001/mcp")
    parser.add_argument("--mcp-namespace", default="mcp")
    parser.add_argument("--mcp-deployment", default="mcp-demo")
    parser.add_argument("--mcp-container", default="mcp-standard")
    parser.add_argument("--retries", type=int, default=1, help="Rerun a failed case this many times (model variance)")
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output-root", type=Path, default=validation.DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    if not args.key_dir:
        environment = os.environ.get("FAIG_ENV_DIR")
        if environment:
            args.key_dir = sorted((Path(environment) / "students").glob("student*-keys"))
        if not args.key_dir:
            parser.error("provide --key-dir or set FAIG_ENV_DIR to an environment with student key directories")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    inventory = REPO_ROOT / args.inventory if not Path(args.inventory).is_absolute() else Path(args.inventory)
    host = validation.parse_inventory(inventory, args.host_alias)
    store = scenario_local.LocalScenarioStore()
    matrix = validation.installed_matrix(store)
    keys = [k for k in key_files(args.key_dir)
            if (not args.scenario or k["scenario"] in args.scenario) and (not args.action or k["action"] in args.action)]
    if not keys:
        raise SystemExit("No key files matched the selection")
    cases = [(plan_case(matrix, store, key), key) for key in keys]
    admin = None
    if args.admin_credentials:
        if args.admin_credentials.stat().st_mode & 0o077:
            raise SystemExit("Admin credential file must be owner-only (chmod 600)")
        admin = FaigAdmin(args.faig_url or default_faig_origin(host),
                          json.loads(args.admin_credentials.read_text(encoding="utf-8")), args.insecure)
    for source, target in ((SHARED_AGENT_PATH, f"{REMOTE_DIR}/faig_agent.py"), (AGENT_PATH, REMOTE_AGENT_PATH)):
        copied = kubectl_exec(args, host, ["sh", "-c", f"mkdir -p {REMOTE_DIR} && cat > {target}"],
                              source.read_text(encoding="utf-8"))
        if copied.returncode != 0:
            raise SystemExit(f"Could not stage {source.name} in the MCP pod: {copied.stderr.strip()[-400:]}")

    output_dir = args.output_root / ("baseline-" + validation.timestamp_label())
    output_dir.mkdir(parents=True, exist_ok=True)
    records, passed = [], 0
    print(f"Baseline: {len(cases)} keys, FAIG {args.faig_internal_url}, MCP {args.mcp_url}"
          + ("" if admin else " (Traffic Log checks off; pass --admin-credentials)"), flush=True)
    for case, key in cases:
        for attempt in range(args.retries + 1):
            since = int(time.time() * 1000) - 2000
            raw = run_case(args, host, case, key)
            verdicts = None
            if admin:
                time.sleep(2)
                verdicts = admin.verdicts(case["key_name"], since)
            ok, details, normalized = judge(case, raw, verdicts)
            if ok:
                break
        passed += ok
        tools = ",".join(normalized["tool_names"]) or "-"
        log = "" if verdicts is None else f" log={'/'.join(verdicts) or 'none'}"
        print(f"{'PASS' if ok else 'FAIL'} {case['key_name']} [{case['case_id']}] expected={case['expected_result']} "
              f"observed={normalized['scenario_verdict']}/{normalized['security_disposition']} tools={tools}{log}"
              + (f" attempts={attempt + 1}" if attempt else ""), flush=True)
        for detail in details:
            print("     - " + detail, flush=True)
        records.append({"case": {k: v for k, v in case.items() if k != "system_prompt"},
                        "passed": ok, "attempts": attempt + 1, "details": details, "traffic_log": verdicts,
                        "normalized": normalized, "reply_preview": str(raw.get("reply", ""))[:800],
                        "tool_events": [{"tool": e.get("tool"), "is_error": e.get("is_error")}
                                        for e in raw.get("tool_events", [])],
                        "rounds": raw.get("rounds"), "error": raw.get("error")})
    validation.write_json(output_dir / "results.json", {"generated_at": validation.now_iso(), "results": records})
    status = "BASELINE READY" if passed == len(cases) else "BASELINE INCOMPLETE"
    print(f"{status}: {passed}/{len(cases)} expected results. Saved {validation.display_path(output_dir)}", flush=True)
    return 0 if passed == len(cases) else 1
