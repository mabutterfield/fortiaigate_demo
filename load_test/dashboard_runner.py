"""Run a bounded, resumable local workload for FAIG dashboard population."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import signal
import threading
import time
from pathlib import Path
from typing import Any

from load_test import gpu_monitor, statistics, traffic_generator, workload


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "load_test" / "output" / "runs"


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()


def checkpoint_value(
    *,
    status: str,
    next_request_index: int,
    plan: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "status": status,
        "next_request_index": next_request_index,
        "planned_requests": len(plan),
        "completed_request_ids": [event["request_id"] for event in events],
    }


def build_runtime_args(
    args: argparse.Namespace,
    profile: dict[str, Any],
    output_dir: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        target="local",
        endpoint="",
        use_case="dashboard",
        run_label=args.run_label,
        traffic_profile="attack",
        model="",
        mcp_path="",
        max_tool_rounds=0,
        temperature=0.0,
        max_tokens=int(profile["normal_traffic"]["max_tokens"]),
        request_timeout=int(profile["execution"]["request_timeout_seconds"]),
        frontend_profile="",
        inventory=args.inventory,
        host_alias=args.host_alias,
        chatbot_namespace=args.chatbot_namespace,
        chatbot_deployment=args.chatbot_deployment,
        output_dir=output_dir,
        summary_only=False,
        agent_probe_supports_tool_profile=False,
    )


def print_plan(
    args: argparse.Namespace,
    profile: dict[str, Any],
    plan: list[dict[str, Any]],
    hourly: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    print(f"run_label: {args.run_label}", flush=True)
    print(f"profile: {profile['id']}", flush=True)
    print(f"hours: {len(hourly)}", flush=True)
    print(f"planned_requests: {len(plan)}", flush=True)
    print(f"output: {output_dir.relative_to(REPO_ROOT)}", flush=True)
    for hour in hourly:
        print(
            f"hour {hour['hour_index'] + 1}: total={hour['total_requests']} "
            f"normal={hour['normal_requests']} suspicious={hour['suspicious_requests']} "
            f"actions={hour['action_counts']}",
            flush=True,
        )


def run(args: argparse.Namespace) -> int:
    profile_path, profile = workload.load_profile(args.profile)
    hours = args.hours or int(profile["duration_hours"])
    seed = int(profile["seed"] if args.seed is None else args.seed)
    if hours > 1 and not args.yes and not args.dry_run:
        raise SystemExit("Runs longer than one hour require --yes")
    matrix, installed_profiles = traffic_generator.installed_runtime()
    profiles = {
        scenario_id: installed_profiles[scenario_id]
        for scenario_id in traffic_generator.BASELINE_SCENARIOS
        if scenario_id in installed_profiles
    }
    if len(profiles) != len(traffic_generator.BASELINE_SCENARIOS):
        missing = sorted(set(traffic_generator.BASELINE_SCENARIOS) - set(profiles))
        raise SystemExit("Missing installed baseline scenarios: " + ", ".join(missing))
    plan, hourly = workload.build_plan(
        profile,
        matrix,
        profiles,
        traffic_generator.high_token_prompt_templates(),
        hours=hours,
        seed=seed,
    )
    output_dir = args.output_root / args.run_label
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite_output:
        raise SystemExit(f"Output directory already exists and is not empty: {output_dir}")
    print_plan(args, profile, plan, hourly, output_dir)
    if args.dry_run:
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_document = {
        "created_at": now_iso(),
        "profile_path": str(profile_path.relative_to(REPO_ROOT)),
        "profile": profile,
        "hours": hours,
        "seed": seed,
        "hourly": hourly,
        "requests": plan,
    }
    statistics.atomic_write_json(output_dir / "plan.json", plan_document)
    runtime_args = build_runtime_args(args, profile, output_dir)
    inventory_host = traffic_generator.parse_inventory(args.inventory, args.host_alias)
    runtime_args.agent_probe_supports_tool_profile = traffic_generator.agent_probe_supports_option(
        runtime_args, inventory_host, "--tool-profile"
    )
    stop_requested = threading.Event()
    signal_number = 0

    def request_stop(received: int, _frame: Any) -> None:
        nonlocal signal_number
        signal_number = received
        stop_requested.set()
        print(f"stop requested by signal {received}; draining active requests", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    monitor: gpu_monitor.NvidiaSmiMonitor | None = None
    if profile["gpu"]["enabled"]:
        monitor = gpu_monitor.NvidiaSmiMonitor(
            traffic_generator.ssh_base(inventory_host),
            output_dir / "gpu.jsonl",
            int(profile["gpu"]["sample_interval_seconds"]),
        )
        try:
            monitor.start()
        except OSError as exc:
            monitor.error = str(exc)
    events: list[dict[str, Any]] = []
    started_at = now_iso()
    started_monotonic = time.monotonic()
    next_index = 0
    futures: dict[
        concurrent.futures.Future[tuple[dict[str, Any], dict[str, Any]]],
        dict[str, Any],
    ] = {}
    statistics_interval = int(profile["statistics"]["update_interval_seconds"])
    checkpoint_interval = int(profile["statistics"]["checkpoint_interval_seconds"])
    next_statistics = time.monotonic()
    next_checkpoint = time.monotonic()
    status = "running"

    def write_statistics(current_status: str) -> None:
        samples = monitor.snapshot() if monitor else []
        value = statistics.live_statistics(
            run_label=args.run_label,
            status=current_status,
            started_at=started_at,
            plan=plan,
            events=events,
            submitted_requests=next_index,
            active_requests=len(futures),
            gpu_samples=samples,
            gpu_error=monitor.error if monitor else "disabled",
        )
        statistics.atomic_write_json(output_dir / "statistics.json", value)

    statistics.atomic_write_json(
        output_dir / "checkpoint.json",
        checkpoint_value(
            status=status,
            next_request_index=next_index,
            plan=plan,
            events=events,
        ),
    )
    write_statistics(status)
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=int(profile["execution"]["concurrency"])
    )
    shutdown_started: float | None = None
    try:
        while True:
            now = time.monotonic()
            elapsed = now - started_monotonic
            for future in list(futures):
                if not future.done():
                    continue
                item, result = future.result()
                del futures[future]
                event = traffic_generator.event_from_result(runtime_args, item, result)
                events.append(event)
                append_jsonl(output_dir / "events.jsonl", event)
                print(
                    f"{event['request_id']} {event['provider_route']} "
                    f"expected={event['expected_result']} actual={event['actual_result']} "
                    f"match={event['result_matches_expected']} latency_ms={event['latency_ms']}",
                    flush=True,
                )
            if stop_requested.is_set() and shutdown_started is None:
                status = "stopping"
                shutdown_started = now
            if not stop_requested.is_set():
                while (
                    next_index < len(plan)
                    and len(futures) < int(profile["execution"]["concurrency"])
                    and float(plan[next_index]["scheduled_offset_seconds"]) <= elapsed
                ):
                    item = plan[next_index]
                    next_index += 1
                    future = executor.submit(
                        lambda planned=item: (
                            planned,
                            traffic_generator.run_agent_probe(
                                runtime_args, inventory_host, planned
                            ),
                        )
                    )
                    futures[future] = item
            if now >= next_statistics:
                write_statistics(status)
                next_statistics = now + statistics_interval
            if now >= next_checkpoint:
                statistics.atomic_write_json(
                    output_dir / "checkpoint.json",
                    checkpoint_value(
                        status=status,
                        next_request_index=next_index,
                        plan=plan,
                        events=events,
                    ),
                )
                next_checkpoint = now + checkpoint_interval
            if stop_requested.is_set() and not futures:
                status = "interrupted"
                break
            if next_index >= len(plan) and not futures:
                status = "completed"
                break
            if shutdown_started is not None and now - shutdown_started > int(
                profile["execution"]["shutdown_grace_seconds"]
            ):
                status = "interrupted"
                break
            time.sleep(0.25)
    finally:
        executor.shutdown(wait=status == "completed", cancel_futures=True)
        if monitor:
            monitor.stop()
        write_statistics(status)
        final_statistics = json.loads((output_dir / "statistics.json").read_text(encoding="utf-8"))
        statistics.atomic_write_json(output_dir / "summary.json", final_statistics)
        statistics.atomic_write_json(
            output_dir / "checkpoint.json",
            checkpoint_value(
                status=status,
                next_request_index=next_index,
                plan=plan,
                events=events,
            ),
        )
        statistics.print_path_results(events)
        print(f"status: {status}", flush=True)
        print(f"summary: {output_dir / 'summary.json'}", flush=True)
    return 128 + signal_number if signal_number else (0 if status == "completed" else 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a profile-driven local workload for FAIG dashboard population.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--profile", default="dashboard-balanced-24h")
    parser.add_argument("--hours", type=int, default=0, help="Override profile duration.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--label", default="")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=REPO_ROOT / "ansible" / "inventory" / "local.generated.ini",
    )
    parser.add_argument("--host-alias", default="jarvis")
    parser.add_argument("--chatbot-namespace", default="chatbot")
    parser.add_argument("--chatbot-deployment", default="chatbot")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()
    if args.hours < 0:
        raise SystemExit("--hours cannot be negative")
    args.run_label = (
        traffic_generator.slugify(args.label)
        if args.label
        else dt.datetime.now(dt.UTC).strftime("dashboard-%Y%m%dT%H%M%SZ")
    )
    if not args.output_root.is_absolute():
        args.output_root = REPO_ROOT / args.output_root
    if not args.inventory.is_absolute():
        args.inventory = REPO_ROOT / args.inventory
    return args


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
