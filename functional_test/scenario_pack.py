"""Build the lab chatbot's scenario pack from installed scenarios and key files.

The pack is a secret-free JSON document that tells the student chatbot, for
each scenario and action a student has a key for: the model, system prompt,
MCP tools, sample prompts, and the single validation test (the same case the
`baseline` command runs). Key secrets are never read into the pack.

    python3 -m functional_test scenario-pack --key-dir ../.student-credentials/student01-keys \
        --output /tmp/lab-chatbot-pack.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from functional_test import baseline, validation
from scripts import scenario_local

PASSTHROUGH = {"title": "Passthrough (no policy)",
               "description": "Plain chat through FortiAIGate with a key that has no policy attached. Every request is logged.",
               "sample_prompts": {"attack": [], "clean": [baseline.PASSTHROUGH_PROMPT]}}


def prompt_text(prompt: Any) -> str:
    return prompt if isinstance(prompt, str) else (prompt.get("prompt") or prompt.get("text") or "")


def scenario_info(store: Any, scenario: str) -> dict[str, Any]:
    if scenario == "passthrough":
        return dict(PASSTHROUGH)
    _, runtime = validation.installed_scenario_entry(store, scenario)
    profile = validation.tracked_validation_profile(scenario, runtime)
    return {"title": profile.get("display_name") or scenario, "description": profile.get("description", ""),
            "sample_prompts": {"attack": [prompt_text(p) for p in profile.get("attack_prompts", [])],
                               "clean": [prompt_text(p) for p in profile.get("clean_prompts", [])]}}


def build_pack(matrix: dict[str, Any], store: Any, keys: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios: dict[str, Any] = {}
    for key in sorted(keys, key=lambda k: (k["scenario"] != "passthrough", k["scenario"], k["action"])):
        scenario, action = key["scenario"], key["action"]
        entry = scenarios.setdefault(scenario, {**scenario_info(store, scenario), "actions": {}})
        if action in entry["actions"]:
            continue
        case = baseline.plan_case(matrix, store, key)
        entry["actions"][action] = {
            "model": case["model"], "system_prompt": case["system_prompt"], "tools": case["tools"],
            "max_rounds": case["max_rounds"],
            "test": {"case_id": case["case_id"], "prompt": case["prompt"], "expected_result": case["expected_result"],
                     "required_tools": case["required_tools"], "forbidden_tools": case["forbidden_tools"],
                     "expected_log_verdict": baseline.EXPECTED_LOG_VERDICT.get(action, "")}}
    return {"version": 1, "scenarios": scenarios}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m functional_test scenario-pack", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key-dir", type=Path, action="append", required=True,
                        help="Owner-only studentNN-keys directory (repeatable); only scenario/action names are read")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    store = scenario_local.LocalScenarioStore()
    pack = build_pack(validation.installed_matrix(store), store, baseline.key_files(args.key_dir))
    args.output.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    actions = sum(len(s["actions"]) for s in pack["scenarios"].values())
    print(f"Wrote {args.output}: {len(pack['scenarios'])} scenarios, {actions} scenario actions")
    return 0
