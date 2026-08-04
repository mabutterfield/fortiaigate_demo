#!/usr/bin/env python3
"""Build simplified chatbot demo profiles from installed scenario metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import instruction_profiles
except ModuleNotFoundError:
    from scripts import instruction_profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "chatbot" / "scenarios" / "examples" / "catalog.json"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    return data if isinstance(data, dict) else {}


def scenario_profile_metadata(scenario_id: str) -> dict[str, Any]:
    if not scenario_id or not CATALOG_PATH.exists():
        return {}
    catalog = read_json(CATALOG_PATH)
    entry = catalog.get("scenarios", {}).get(scenario_id, {})
    profile_path = entry.get("path", "")
    if not profile_path:
        return {}
    path = CATALOG_PATH.parent / str(profile_path)
    if not path.exists():
        return {}
    return read_json(path)


def normalize_profiles(metadata: dict[str, Any], slot: str) -> list[dict[str, Any]]:
    raw_profiles = metadata.get("chatbot_demo_profiles", [])
    if not raw_profiles:
        raw_profiles = scenario_profile_metadata(str(metadata.get("scenario_id") or "")).get("chatbot_demo_profiles", [])
    if not isinstance(raw_profiles, list):
        return []

    scenario_id = str(metadata.get("scenario_id") or "").strip()
    normalized = []
    for index, item in enumerate(raw_profiles, start=1):
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id") or "").strip()
        if not profile_id:
            profile_id = f"{scenario_id or slot}-{index}"
        profile = dict(item)
        profile["id"] = profile_id
        profile.setdefault("scenario_id", scenario_id)
        profile.setdefault("source_slot", slot)
        profile.setdefault("label", profile_id.replace("-", " ").title())
        normalized.append(profile)
    return normalized


def build_profiles(slots: list[str]) -> dict[str, Any]:
    profiles_by_id: dict[str, dict[str, Any]] = {}
    installed_slots: list[dict[str, Any]] = []

    for slot in slots:
        slot_name = instruction_profiles.resolve_slot(slot)
        metadata = instruction_profiles.slot_metadata(slot_name)
        profiles = normalize_profiles(metadata, slot_name)
        installed_slots.append(
            {
                "slot": slot_name,
                "scenario_id": metadata.get("scenario_id", ""),
                "profiles": [profile["id"] for profile in profiles],
            }
        )
        for profile in profiles:
            profiles_by_id.setdefault(profile["id"], profile)

    profiles = list(profiles_by_id.values())
    return {
        "default_profile": profiles[0]["id"] if profiles else "",
        "profiles": profiles,
        "installed_slots": installed_slots,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build simplified chatbot demo profiles from installed scenario metadata."
    )
    parser.add_argument(
        "--slots",
        nargs="+",
        default=["demo-a", "demo-b", "frontend"],
        help="Instruction slots to inspect for installed scenario metadata.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(build_profiles(args.slots), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
