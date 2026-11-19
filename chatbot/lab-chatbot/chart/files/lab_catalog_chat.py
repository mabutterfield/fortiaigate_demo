"""Catalog-driven helpers for the student lab chatbot (Change 2026-11-19).

Replaces the scenario-pack.json / per-namespace key Secret model:
- scenarios, actions, prompts and tests come from the rendered catalog student
  view (catalog-student.json in the lab-catalog ConfigMap);
- key records come from the gateway's key endpoints (lab_auth), called with
  this app's caller token and the visitor's session handle (X-Lab-Session);
- tests are graded by the shared catalog evaluator
  (catalog802.result_contract.evaluate) from collected evidence and Traffic Log
  rows positively matched by a unique marker in the prompt.

Standard library only (plus the copied catalog802 package).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

MARKER = re.compile(r"\[faig-test-[0-9a-f]{32}\]")
VERDICTS = {"log", "alert", "redact", "block"}


# ------------------------------------------------------------------ catalog

def load_view(path: str) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """(scenarios by id, platform, error) from catalog-student.json; errors are reported, not raised."""
    try:
        with open(path, encoding="utf-8") as handle:
            view = json.load(handle)
        if view.get("view") != "student" or not isinstance(view.get("items"), list):
            raise ValueError("not a student catalog view")
        return {item["id"]: item for item in view["items"]}, view.get("platform") or {}, None
    except FileNotFoundError:
        return {}, {}, "catalog unavailable: catalog-student.json not found"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {}, {}, f"catalog unavailable: {exc}"


def action_label(scenario: dict[str, Any], action: str) -> str:
    return next((a.get("display_name") or action for a in scenario.get("actions", []) if a["id"] == action), action)


def tests_for(scenario: dict[str, Any], action: str) -> list[dict[str, Any]]:
    return [t for t in scenario.get("tests", []) if t["action"] == action]


def model_for(scenario: dict[str, Any], action: str) -> dict[str, Any]:
    ref = next((a.get("model_ref") for a in scenario.get("actions", []) if a["id"] == action), None)
    models = scenario.get("models", [])
    return next((m for m in models if m.get("id") == ref), models[0] if models else {})


def prompt_text(scenario: dict[str, Any], prompt_ref: str) -> str:
    for group in (scenario.get("prompts") or {}).values():
        for prompt in group:
            if prompt["id"] == prompt_ref:
                return prompt["text"]
    raise ValueError(f"prompt {prompt_ref} not found")


def plan_test(scenario: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    """Agent inputs for one catalog test (mirrors functional_test.catalog_plan, from the student view)."""
    system_prompt = ""
    if test.get("frontend_instruction", "none") == "compromised":
        system_prompt = scenario.get("frontend_instruction") or ""
        if not system_prompt:
            raise ValueError("compromised frontend fixture not available in the catalog view")
    tools = list(scenario.get("tools", []))
    needed = set(test.get("required_tools", [])) | set(test.get("attack_tools", []))
    for group in scenario.get("extended_tool_sets", []):
        if needed.intersection(group["tools"]):
            tools.extend(group["tools"])
    return {"prompt": prompt_text(scenario, test["prompt_ref"]), "system_prompt": system_prompt,
            "tools": list(dict.fromkeys(tools)), "max_rounds": scenario.get("max_rounds", 3),
            "model": model_for(scenario, test["action"]).get("public_name", "")}


# ------------------------------------------------------------------ gateway key endpoints

def broker(auth_url: str, token: str, handle: str, path: str, body: dict | None = None,
           timeout: int = 60) -> tuple[int, Any]:
    """Call a lab_auth key endpoint as this app for the visitor's session handle."""
    if not token:
        return 0, {"error": "key service not configured (caller token missing)"}
    if not handle:
        return 401, {"error": "session handle missing; reload the page or sign in again"}
    headers = {"Authorization": "Bearer " + token, "X-Lab-Session": handle}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(auth_url.rstrip("/") + path, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, {"error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def mapped_key(records: list[dict[str, Any]], scenario: str, action: str) -> dict[str, Any] | None:
    """The usable key (has a value, not missing) mapped to scenario/action; newest first."""
    usable = [r for r in records if r.get("scenario_id") == scenario and r.get("action") == action
              and r.get("secret") and r.get("status") != "missing"]
    return max(usable, key=lambda r: r.get("updated_at") or 0) if usable else None


def public_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"key": r.get("key_name", ""), "scenario": r.get("scenario_id") or "-", "action": r.get("action") or "-",
             "model": r.get("model", ""), "policies": len(r.get("policy_ids") or []),
             "value stored": "yes" if r.get("secret") or r.get("has_secret") else "no",
             "status": r.get("status", ""), "origin": r.get("origin", "")} for r in records]


# ------------------------------------------------------------------ running a test

def evidence_from_turn(raw: dict[str, Any], test: dict[str, Any], contains_sensitive: Callable[[Any], bool],
                       block_message: str | None = None) -> tuple[list[str], list[str]]:
    """Client-observable evidence (mirrors functional_test.catalog_baseline.evidence_from_turn)."""
    evidence = set()
    reply = str(raw.get("reply") or "")
    events = raw.get("tool_events") or []
    if contains_sensitive(reply):
        evidence.add("sensitive-data-in-reply")
    if any(isinstance(e, dict) and contains_sensitive(e.get("result")) for e in events):
        evidence.add("sensitive-data-in-tool-result")
    if block_message and reply.strip() == block_message.strip():
        evidence.add("block-message-in-reply")
    if "[REDACTED_" in reply.upper():
        evidence.add("redaction-marker-in-reply")
    tools = [str(e.get("tool") or e.get("name")) for e in events if isinstance(e, dict)]
    if set(test.get("attack_tools", [])) & set(tools):
        evidence.add("attack-tool-called")
    return sorted(evidence), tools


def request_count(raw: dict[str, Any]) -> int | None:
    rounds = raw.get("rounds")
    known = not raw.get("error") or raw.get("error") == "http_error"
    if known and isinstance(rounds, int) and not isinstance(rounds, bool) and rounds >= 0:
        return rounds + 1
    return None


def match_rows(fetch_logs: Callable[..., tuple[int, Any]], key_name: str, since_ms: int,
               marker: str) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
    """Rows whose detail contains the run marker; (rows, details, error)."""
    status, data = fetch_logs(key_alias=key_name, since_ms=since_ms, limit=100)
    if status != 200:
        return [], [], (data or {}).get("error", f"HTTP {status}") if isinstance(data, dict) else f"HTTP {status}"
    rows, details, seen = [], [], set()
    for row in data.get("items", []):
        uid = row.get("uuid")
        if not isinstance(uid, str) or not uid or uid in seen or row.get("keyAlias") != key_name:
            continue
        seen.add(uid)
        dstatus, detail = fetch_logs(uuid=uid)
        if dstatus != 200 or not isinstance(detail, dict) or detail.get("uuid") != uid:
            continue
        original = (detail.get("prompt") or {}).get("original") if isinstance(detail.get("prompt"), dict) else None
        verdict = str(detail.get("verdictLabel") or "").lower()
        if not isinstance(original, str) or marker not in original or verdict not in VERDICTS:
            continue
        rows.append({"uuid": uid, "verdict": verdict})
        details.append({k: detail.get(k) for k in ("uuid", "timeStamp", "verdictLabel", "action", "guardType",
                                                    "model", "keyAlias", "tokens", "cost") if k in detail})
    return rows, details, ""


def run_case(*, agent: Callable[[dict], dict], fetch_logs: Callable[..., tuple[int, Any]],
             evaluate: Callable[..., dict], contains_sensitive: Callable[[Any], bool], test: dict[str, Any],
             plan: dict[str, Any], key: dict[str, Any], faig_url: str, mcp_url: str, scenario_version: str,
             block_message: str | None = None, max_tokens: int = 2048, temperature: float = 0.0,
             log_wait: int = 20, faig_version: str = "8.0.2", sleep=time.sleep, clock=time.time) -> dict[str, Any]:
    """Run one test with the key and grade it with the catalog evaluator."""
    marker = "[faig-test-" + uuid.uuid4().hex + "]"
    since = int(clock() * 1000) - 2000
    spec = {"base_url": faig_url, "api_key": key["secret"], "model": plan["model"],
            "prompt": plan["prompt"] + "\n" + marker, "system_prompt": plan["system_prompt"], "history": [],
            "mcp_url": mcp_url, "tools": plan["tools"], "max_rounds": plan["max_rounds"],
            "max_tokens": max_tokens, "temperature": temperature, "record_exchanges": True}
    raw = agent(spec)
    execution = "error" if raw.get("error") else "completed"
    requests_sent = request_count(raw)
    evidence, tools = evidence_from_turn(raw, test, contains_sensitive, block_message)
    rows, details, log_error = [], [], ""
    deadline = clock() + log_wait
    while execution == "completed" and requests_sent:
        rows, details, log_error = match_rows(fetch_logs, key["key_name"], since, marker)
        if log_error or len(rows) >= requests_sent or clock() >= deadline:
            break
        sleep(2)
    result = evaluate(execution=execution, verdict_rows=rows, requests_sent=requests_sent or 0, evidence=evidence,
                      tools_called=tools, test=test, faig_version=faig_version, scenario_version=scenario_version)
    result.update({"test": test.get("id", ""), "key_name": key["key_name"], "requests_sent": requests_sent,
                   "tools_called": tools, "reply": raw.get("reply") or "", "http_status": raw.get("http_status"),
                   "execution_error": raw.get("error") or "", "exchanges": raw.get("exchanges") or [],
                   "log_entries": details, "log_error": log_error, "tool_events": raw.get("tool_events") or []})
    return result


def hello_world_test(platform: dict[str, Any]) -> dict[str, Any]:
    """The platform hello-world as a catalog-shaped test (no tools, expected verdict Log)."""
    hello = platform.get("hello_world") or {}
    return {"id": "hello-world", "action": "", "prompt_ref": "", "required_tools": [], "forbidden_tools": [],
            "attack_tools": [], "expect": hello.get("expect") or {"verdict": "log", "evidence_present": [],
                                                                  "evidence_absent": []}}


def key_status_for(result: dict[str, Any]) -> str:
    """Key status recorded after a hello-world run."""
    if result.get("execution_error") == "http_error":
        code = result.get("http_status")
        return "invalid" if code in (401, 403) else "denied" if code in (400, 404, 422, 429) else "unavailable"
    if result.get("execution_error"):
        return "error"
    if result.get("outcome") == "pass" and result.get("reply"):
        return "ok"
    return "untested" if result.get("outcome") == "incomplete" else "error"
