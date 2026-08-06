"""Compact result aggregation shared by validation and workload runs."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any


def event_path(event: dict[str, Any]) -> str:
    return str(event["provider_route"] or f"direct:{event['scenario_id']}")


def path_result_rows(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    paths: dict[str, dict[str, Any]] = {}
    for event in events:
        path = event_path(event)
        row = paths.setdefault(
            path,
            {
                "expected_results": 0,
                "total_results": 0,
                "expected_result_counts": Counter(),
                "actual_result_counts": Counter(),
            },
        )
        row["total_results"] += 1
        row["expected_results"] += int(event["result_matches_expected"])
        row["expected_result_counts"][event["expected_result"]] += 1
        row["actual_result_counts"][event["actual_result"]] += 1
    return {
        path: {
            **row,
            "expected_result_counts": dict(row["expected_result_counts"]),
            "actual_result_counts": dict(row["actual_result_counts"]),
        }
        for path, row in sorted(paths.items())
    }


def print_path_results(events: list[dict[str, Any]]) -> None:
    print("path_results:")
    for path, row in path_result_rows(events).items():
        expected = ",".join(
            f"{name}={count}"
            for name, count in sorted(row["expected_result_counts"].items())
        )
        actual = ",".join(
            f"{name}={count}"
            for name, count in sorted(row["actual_result_counts"].items())
        )
        print(
            f"  {path}: {row['expected_results']}/{row['total_results']} expected "
            f"(expected: {expected}; actual: {actual})"
        )


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def gpu_statistics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        grouped.setdefault(str(sample["uuid"]), []).append(sample)
    result: dict[str, Any] = {}
    for uuid, values in grouped.items():
        values.sort(key=lambda item: float(item["received_epoch"]))
        numeric_fields = [
            "utilization_gpu_percent",
            "utilization_memory_percent",
            "memory_used_mib",
            "power_draw_watts",
            "temperature_c",
        ]
        aggregates: dict[str, Any] = {}
        for field in numeric_fields:
            numbers = [float(item[field]) for item in values if item.get(field) is not None]
            aggregates[f"{field}_average"] = (
                round(sum(numbers) / len(numbers), 3) if numbers else None
            )
            aggregates[f"{field}_maximum"] = max(numbers) if numbers else None
        energy_wh = 0.0
        for previous, current in zip(values, values[1:]):
            power = previous.get("power_draw_watts")
            if power is None:
                continue
            seconds = max(
                0.0,
                min(
                    300.0,
                    float(current["received_epoch"]) - float(previous["received_epoch"]),
                ),
            )
            energy_wh += float(power) * seconds / 3600.0
        result[uuid] = {
            "index": values[-1]["index"],
            "name": values[-1]["name"],
            "samples": len(values),
            "estimated_energy_wh": round(energy_wh, 3),
            **aggregates,
        }
    return result


def live_statistics(
    *,
    run_label: str,
    status: str,
    started_at: str,
    plan: list[dict[str, Any]],
    events: list[dict[str, Any]],
    submitted_requests: int,
    active_requests: int,
    gpu_samples: list[dict[str, Any]],
    gpu_error: str = "",
) -> dict[str, Any]:
    latencies = [
        int(event["latency_ms"])
        for event in events
        if event["completion_status"] == "ok"
    ]
    outcome_counts = Counter(
        event["outcome"] if event["completion_status"] == "ok" else "error"
        for event in events
    )
    approximate_input = sum(int(event.get("approx_input_tokens", 0)) for event in events)
    approximate_output = sum(
        math.ceil(int(event.get("approx_response_length", 0)) / 4) for event in events
    )
    return {
        "updated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "started_at": started_at,
        "run_label": run_label,
        "status": status,
        "planned_requests": len(plan),
        "submitted_requests": submitted_requests,
        "active_requests": active_requests,
        "completed_requests": len(events),
        "remaining_requests": max(0, len(plan) - submitted_requests),
        "outcome_counts": dict(outcome_counts),
        "suspicious_requests": sum(
            outcome_counts.get(action, 0) for action in ("alert", "deny", "redact")
        ),
        "normal_requests": outcome_counts.get("success", 0),
        "expected_results": sum(int(event["result_matches_expected"]) for event in events),
        "unexpected_results": sum(int(not event["result_matches_expected"]) for event in events),
        "approximate_input_tokens": approximate_input,
        "approximate_output_tokens": approximate_output,
        "approximate_total_tokens": approximate_input + approximate_output,
        "latency_ms": {
            "minimum": min(latencies) if latencies else None,
            "maximum": max(latencies) if latencies else None,
            "average": round(sum(latencies) / len(latencies), 3) if latencies else None,
        },
        "path_results": path_result_rows(events),
        "gpu": gpu_statistics(gpu_samples),
        "gpu_error": gpu_error,
    }
