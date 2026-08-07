"""Profile loading and reproducible hourly workload planning."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from functional_test import validation as scenario_validation


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = REPO_ROOT / "load_test" / "profiles"
SCHEMA_PATH = REPO_ROOT / "load_test" / "schemas" / "dashboard-workload-v1.schema.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_profile(name_or_path: str) -> tuple[Path, dict[str, Any]]:
    path = Path(name_or_path)
    if not path.suffix:
        path = PROFILE_ROOT / f"{name_or_path}.json"
    elif not path.is_absolute():
        path = REPO_ROOT / path
    profile = load_json(path)
    validate_profile(profile)
    return path, profile


def validate_profile(profile: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "id",
        "duration_hours",
        "seed",
        "volume",
        "mix",
        "normal_traffic",
        "execution",
        "statistics",
        "gpu",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise ValueError("Workload profile is missing: " + ", ".join(missing))
    if profile["schema_version"] != 1:
        raise ValueError("Unsupported workload profile schema_version")
    if int(profile["duration_hours"]) < 1:
        raise ValueError("duration_hours must be at least one")
    volume = profile["volume"]
    mix = profile["mix"]
    normal = profile["normal_traffic"]
    if volume["minimum_requests_per_hour"] > volume["maximum_requests_per_hour"]:
        raise ValueError("minimum_requests_per_hour cannot exceed maximum_requests_per_hour")
    if mix["normal_ratio_minimum"] > mix["normal_ratio_maximum"]:
        raise ValueError("normal_ratio_minimum cannot exceed normal_ratio_maximum")
    if normal["minimum_output_words"] > normal["maximum_output_words"]:
        raise ValueError("minimum_output_words cannot exceed maximum_output_words")
    floor_total = sum(int(value) for value in mix["hourly_action_floor"].values())
    if volume["minimum_requests_per_hour"] <= floor_total:
        raise ValueError("minimum hourly volume must exceed the required action floor")
    if not 1 <= int(profile["execution"]["concurrency"]) <= 4:
        raise ValueError("concurrency must be between one and four")


def _choose_case(
    rng: random.Random,
    cases_by_action: dict[str, list[dict[str, Any]]],
    action: str,
    action_offsets: Counter[str],
) -> dict[str, Any]:
    cases = cases_by_action.get(action, [])
    if not cases:
        raise ValueError(f"No validation case declares required hourly action {action}")
    start = action_offsets[action] % len(cases)
    action_offsets[action] += 1
    if len(cases) == 1:
        return dict(cases[0])
    offset = (start + rng.randrange(len(cases))) % len(cases)
    return dict(cases[offset])


def build_plan(
    profile: dict[str, Any],
    matrix: dict[str, Any],
    scenario_profiles: dict[str, dict[str, Any]],
    prompt_templates: list[str],
    *,
    hours: int | None = None,
    seed: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    duration_hours = int(hours or profile["duration_hours"])
    rng = random.Random(profile["seed"] if seed is None else seed)
    scenario_ids = sorted(scenario_profiles)
    validation_items = scenario_validation.validation_plan_items(
        matrix, scenario_profiles, scenario_ids
    )
    cases_by_action: dict[str, list[dict[str, Any]]] = {}
    for item in validation_items:
        cases_by_action.setdefault(str(item["route"]), []).append(item)
    passthrough_config = scenario_validation.scenario_action_configs(
        matrix, scenario_ids[0], ["passthrough"]
    )[0]
    volume = profile["volume"]
    mix = profile["mix"]
    normal = profile["normal_traffic"]
    previous_total = rng.randint(
        int(volume["minimum_requests_per_hour"]),
        int(volume["maximum_requests_per_hour"]),
    )
    action_offsets: Counter[str] = Counter()
    plan: list[dict[str, Any]] = []
    hourly: list[dict[str, Any]] = []
    for hour in range(duration_hours):
        if hour:
            step = int(volume["hourly_step_limit"])
            previous_total = max(
                int(volume["minimum_requests_per_hour"]),
                min(
                    int(volume["maximum_requests_per_hour"]),
                    previous_total + rng.randint(-step, step),
                ),
            )
        total = previous_total
        normal_ratio = max(
            float(mix["normal_ratio_minimum"]),
            min(
                float(mix["normal_ratio_maximum"]),
                rng.gauss(
                    float(mix["normal_ratio_baseline"]),
                    float(mix["hourly_ratio_variance"]),
                ),
            ),
        )
        floor = {key: int(value) for key, value in mix["hourly_action_floor"].items()}
        suspicious_count = max(sum(floor.values()), round(total * (1.0 - normal_ratio)))
        suspicious_count = min(suspicious_count, total - 1)
        requests: list[dict[str, Any]] = []
        for action, count in floor.items():
            for _ in range(count):
                requests.append(_choose_case(rng, cases_by_action, action, action_offsets))
        all_cases = [item for cases in cases_by_action.values() for item in cases]
        while len(requests) < suspicious_count:
            requests.append(dict(rng.choice(all_cases)))
        while len(requests) < total:
            prompt_index = rng.randrange(len(prompt_templates))
            word_count = rng.randint(
                int(normal["minimum_output_words"]),
                int(normal["maximum_output_words"]),
            )
            requests.append(
                {
                    "scenario": "passthrough",
                    "route": "passthrough",
                    "path_config": passthrough_config,
                    "prompt_kind": "passthrough",
                    "prompt_index": prompt_index,
                    "prompt_id": f"passthrough-{prompt_index + 1:02d}",
                    "prompt": prompt_templates[prompt_index].format(word_count=word_count),
                    "requested_output_words": word_count,
                    "tool_profile": "",
                    "expected_result": "completed",
                    "required_tools": [],
                    "forbidden_tools": [],
                }
            )
        rng.shuffle(requests)
        offsets = sorted(rng.uniform(0, 3600) for _ in requests)
        offsets[0] = min(offsets[0], float(profile["execution"]["initial_request_within_seconds"]))
        for request, offset in zip(requests, offsets):
            request["scheduled_offset_seconds"] = hour * 3600 + offset
            request["hour_index"] = hour
            plan.append(request)
        hourly.append(
            {
                "hour_index": hour,
                "total_requests": total,
                "normal_requests": total - suspicious_count,
                "suspicious_requests": suspicious_count,
                "sampled_normal_ratio": round(normal_ratio, 4),
                "planned_normal_ratio": round((total - suspicious_count) / total, 4),
                "action_counts": dict(Counter(item["route"] for item in requests)),
            }
        )
    for index, item in enumerate(plan, start=1):
        item["request_id"] = f"req-{index:05d}"
    return plan, hourly
