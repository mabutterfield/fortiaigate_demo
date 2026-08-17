"""Run one FAIG dashboard request at a time until a wall-clock deadline.

This runner complements ``dashboard_runner``. It deliberately avoids a fixed
request schedule: each request starts only after the previous request finishes
and a small randomized backoff expires. A timed-out probe trips a circuit
breaker by default because terminating the local SSH client does not prove that
the upstream Ollama request was cancelled.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import random
import signal
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from functional_test import validation as scenario_validation
from load_test import dashboard_runner, gpu_monitor, statistics, traffic_generator


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = REPO_ROOT / "load_test" / "profiles"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "load_test" / "output" / "runs"
PROTECTED_ACTIONS = ("alert", "deny", "redact")


def load_profile(name_or_path: str) -> tuple[Path, dict[str, Any]]:
    path = Path(name_or_path)
    if not path.suffix:
        path = PROFILE_ROOT / f"{name_or_path}.json"
    elif not path.is_absolute():
        path = REPO_ROOT / path
    with path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict):
        raise ValueError(f"Expected JSON object: {path}")
    validate_profile(profile)
    return path, profile


def validate_profile(profile: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "id",
        "duration_hours",
        "seed",
        "maximum_requests",
        "mix",
        "normal_traffic",
        "pacing",
        "execution",
        "statistics",
        "gpu",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise ValueError("Completion profile is missing: " + ", ".join(missing))
    if int(profile["schema_version"]) != 1:
        raise ValueError("Unsupported completion profile schema_version")
    if not 0 < float(profile["duration_hours"]) <= 168:
        raise ValueError("duration_hours must be greater than zero and no more than 168")
    if int(profile["maximum_requests"]) < 1:
        raise ValueError("maximum_requests must be at least one")

    mix = profile["mix"]
    normal_ratio = float(mix["normal_ratio"])
    if not 0 < normal_ratio < 1:
        raise ValueError("normal_ratio must be between zero and one")
    required_actions = set(mix["hourly_each_path_actions"])
    if required_actions != {"deny", "redact"}:
        raise ValueError("hourly_each_path_actions must contain deny and redact")
    if int(mix["hourly_alert_count"]) < 0:
        raise ValueError("hourly_alert_count cannot be negative")
    coverage_window = int(mix["coverage_within_requests"])
    if coverage_window < 1:
        raise ValueError("coverage_within_requests must be at least one")

    normal = profile["normal_traffic"]
    if int(normal["minimum_output_words"]) > int(normal["maximum_output_words"]):
        raise ValueError("minimum_output_words cannot exceed maximum_output_words")
    pacing = profile["pacing"]
    minimum = float(pacing["minimum_backoff_seconds"])
    mean = float(pacing["mean_backoff_seconds"])
    maximum = float(pacing["maximum_backoff_seconds"])
    if not 0 <= minimum <= mean <= maximum:
        raise ValueError("backoff values must satisfy 0 <= minimum <= mean <= maximum")
    execution = profile["execution"]
    if int(execution["request_timeout_seconds"]) < 30:
        raise ValueError("request_timeout_seconds must be at least 30")
    if int(execution["timeout_circuit_breaker_count"]) < 1:
        raise ValueError("timeout_circuit_breaker_count must be at least one")
    if int(execution["error_circuit_breaker_count"]) < 1:
        raise ValueError("error_circuit_breaker_count must be at least one")


def build_hourly_item_queue(
    rng: random.Random,
    *,
    cases_by_action: dict[str, list[dict[str, Any]]],
    each_path_actions: list[str],
    alert_count: int,
    coverage_within_requests: int,
) -> list[dict[str, Any] | None]:
    """Queue every configured deny/redact path once near the start of an hour."""
    required: list[dict[str, Any]] = []
    for action in each_path_actions:
        cases = cases_by_action.get(action, [])
        if not cases:
            raise ValueError(f"No validation cases declare required hourly action {action}")
        required.extend(dict(case) for case in cases)
    if alert_count:
        alert_cases = cases_by_action.get("alert", [])
        if not alert_cases:
            raise ValueError("No validation cases declare required hourly action alert")
        required.extend(dict(rng.choice(alert_cases)) for _ in range(alert_count))
    # Keep the hourly coverage queue clean-majority even as new protected paths
    # are added to scenario metadata.
    queue_size = max(coverage_within_requests, (len(required) * 2) + 1)
    queue: list[dict[str, Any] | None] = required + ([None] * (queue_size - len(required)))
    rng.shuffle(queue)
    return queue


def random_backoff_seconds(
    rng: random.Random,
    *,
    minimum: float,
    mean: float,
    maximum: float,
    consecutive_errors: int = 0,
) -> float:
    """Return a bounded exponential delay, stretched after transport errors."""
    if maximum <= minimum:
        return maximum
    exponential_mean = max(0.001, mean - minimum)
    sampled = minimum + rng.expovariate(1.0 / exponential_mean)
    multiplier = 2 ** min(max(0, consecutive_errors), 4)
    return round(min(maximum, sampled * multiplier), 3)


def choose_case(
    rng: random.Random,
    cases_by_action: dict[str, list[dict[str, Any]]],
    action: str,
    action_offsets: Counter[str],
) -> dict[str, Any]:
    cases = cases_by_action.get(action, [])
    if not cases:
        raise ValueError(f"No validation case declares required action {action}")
    offset = action_offsets[action] % len(cases)
    action_offsets[action] += 1
    if offset == 0 and len(cases) > 1:
        rng.shuffle(cases)
    return dict(cases[offset])


class RequestMixer:
    """Create completion-driven requests while preserving the configured mix."""

    def __init__(
        self,
        profile: dict[str, Any],
        matrix: dict[str, Any],
        scenario_profiles: dict[str, dict[str, Any]],
        prompt_templates: list[str],
        rng: random.Random,
    ) -> None:
        scenario_ids = sorted(scenario_profiles)
        validation_items = scenario_validation.validation_plan_items(
            matrix, scenario_profiles, scenario_ids
        )
        self.cases_by_action: dict[str, list[dict[str, Any]]] = {}
        for item in validation_items:
            self.cases_by_action.setdefault(str(item["route"]), []).append(dict(item))
        self.passthrough_config = scenario_validation.scenario_action_configs(
            matrix, scenario_ids[0], ["passthrough"]
        )[0]
        self.profile = profile
        self.prompt_templates = prompt_templates
        self.rng = rng
        self.action_offsets: Counter[str] = Counter()
        self.hour_index = -1
        self.hourly_items: list[dict[str, Any] | None] = []

    def _refill(self, hour_index: int) -> None:
        mix = self.profile["mix"]
        self.hourly_items = build_hourly_item_queue(
            self.rng,
            cases_by_action=self.cases_by_action,
            each_path_actions=[str(action) for action in mix["hourly_each_path_actions"]],
            alert_count=int(mix["hourly_alert_count"]),
            coverage_within_requests=int(mix["coverage_within_requests"]),
        )
        self.hour_index = hour_index

    def next_item(self, request_number: int, hour_index: int) -> dict[str, Any]:
        if hour_index != self.hour_index:
            self._refill(hour_index)
        if self.hourly_items:
            queued_item = self.hourly_items.pop(0)
            route = "passthrough" if queued_item is None else str(queued_item["route"])
        elif self.rng.random() < float(self.profile["mix"]["normal_ratio"]):
            queued_item = None
            route = "passthrough"
        else:
            queued_item = None
            route = self.rng.choice(PROTECTED_ACTIONS)
        if queued_item is not None:
            item = queued_item
        elif route != "passthrough":
            item = choose_case(self.rng, self.cases_by_action, route, self.action_offsets)
        else:
            normal = self.profile["normal_traffic"]
            prompt_index = self.rng.randrange(len(self.prompt_templates))
            word_count = self.rng.randint(
                int(normal["minimum_output_words"]),
                int(normal["maximum_output_words"]),
            )
            item = {
                "scenario": "passthrough",
                "route": "passthrough",
                "path_config": self.passthrough_config,
                "prompt_kind": "passthrough",
                "prompt_index": prompt_index,
                "prompt_id": f"passthrough-{prompt_index + 1:02d}",
                "prompt": self.prompt_templates[prompt_index].format(word_count=word_count),
                "requested_output_words": word_count,
                "tool_profile": "",
                "expected_result": "completed",
                "required_tools": [],
                "forbidden_tools": [],
            }
        item["request_id"] = f"req-{request_number:05d}"
        item["hour_index"] = hour_index
        return item


def path_for_display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def checkpoint_value(
    *,
    status: str,
    stop_reason: str,
    plan: list[dict[str, Any]],
    events: list[dict[str, Any]],
    deadline_at: str,
) -> dict[str, Any]:
    return {
        "updated_at": dashboard_runner.now_iso(),
        "status": status,
        "stop_reason": stop_reason,
        "deadline_at": deadline_at,
        "submitted_requests": len(plan),
        "completed_request_ids": [event["request_id"] for event in events],
        "next_request_number": len(plan) + 1,
    }


def plan_document(
    *,
    profile_path: Path,
    profile: dict[str, Any],
    hours: float,
    seed: int,
    started_at: str,
    deadline_at: str,
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "created_at": started_at,
        "updated_at": dashboard_runner.now_iso(),
        "mode": "completion-driven",
        "profile_path": path_for_display(profile_path),
        "profile": profile,
        "hours": hours,
        "seed": seed,
        "deadline_at": deadline_at,
        "requests": plan,
    }


def print_dry_run(
    args: argparse.Namespace,
    profile: dict[str, Any],
    mixer: RequestMixer,
    rng: random.Random,
    hours: float,
    seed: int,
    output_dir: Path,
) -> None:
    sample_items = [mixer.next_item(index, 0) for index in range(1, 25)]
    sample = [
        "passthrough"
        if item["route"] == "passthrough"
        else f"{item['scenario']}:{item['route']}"
        for item in sample_items
    ]
    pacing = profile["pacing"]
    backoffs = [
        random_backoff_seconds(
            rng,
            minimum=float(pacing["minimum_backoff_seconds"]),
            mean=float(pacing["mean_backoff_seconds"]),
            maximum=float(pacing["maximum_backoff_seconds"]),
        )
        for _ in range(8)
    ]
    print(f"run_label: {args.run_label}")
    print(f"profile: {profile['id']}")
    print("mode: completion-driven (one request in flight)")
    print(f"hours: {hours:g}")
    print(f"seed: {seed}")
    print(f"maximum_requests: {args.maximum_requests}")
    print(f"normal_ratio: {float(profile['mix']['normal_ratio']):.2%}")
    print(f"request_timeout_seconds: {args.request_timeout}")
    print(f"output: {path_for_display(output_dir)}")
    print("sample_lanes: " + ", ".join(sample))
    print("sample_backoff_seconds: " + ", ".join(f"{value:g}" for value in backoffs))
    print("dry-run: no requests sent and no output written")


def run(args: argparse.Namespace) -> int:
    profile_path, profile = load_profile(args.profile)
    hours = float(args.hours or profile["duration_hours"])
    seed = int(profile["seed"] if args.seed is None else args.seed)
    args.maximum_requests = int(args.maximum_requests or profile["maximum_requests"])
    args.request_timeout = int(
        args.request_timeout or profile["execution"]["request_timeout_seconds"]
    )
    if hours > 1 and not args.yes and not args.dry_run:
        raise SystemExit("Runs longer than one hour require --yes")

    matrix, installed_profiles = traffic_generator.installed_runtime()
    scenario_ids = traffic_generator.selected_installed_scenarios(args, installed_profiles)
    profiles = {
        scenario_id: installed_profiles[scenario_id]
        for scenario_id in scenario_ids
    }
    required_actions = {str(action) for action in profile["mix"]["hourly_each_path_actions"]}
    if int(profile["mix"]["hourly_alert_count"]):
        required_actions.add("alert")
    traffic_generator.require_validation_actions(
        matrix, profiles, scenario_ids, required_actions
    )

    output_dir = args.output_root / args.run_label
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"Output directory already exists and is not empty: {output_dir}")
    rng = random.Random(seed)
    mixer = RequestMixer(
        profile,
        matrix,
        profiles,
        traffic_generator.high_token_prompt_templates(),
        rng,
    )
    if args.dry_run:
        print_dry_run(args, profile, mixer, rng, hours, seed, output_dir)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_args = dashboard_runner.build_runtime_args(args, profile, output_dir)
    runtime_args.request_timeout = args.request_timeout
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
        print(f"stop requested by signal {received}; draining the active request", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    started_at = dashboard_runner.now_iso()
    started_datetime = dt.datetime.now(dt.UTC)
    started_monotonic = time.monotonic()
    duration_seconds = hours * 3600.0
    deadline_monotonic = started_monotonic + duration_seconds
    deadline_at = (started_datetime + dt.timedelta(seconds=duration_seconds)).isoformat().replace(
        "+00:00", "Z"
    )
    events: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    status = "running"
    stop_reason = ""
    consecutive_errors = 0
    consecutive_timeouts = 0
    next_submit_at = started_monotonic
    active: concurrent.futures.Future[tuple[dict[str, Any], dict[str, Any]]] | None = None

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

    statistics_interval = int(profile["statistics"]["update_interval_seconds"])
    checkpoint_interval = int(profile["statistics"]["checkpoint_interval_seconds"])
    next_statistics = started_monotonic
    next_checkpoint = started_monotonic

    def write_statistics(current_status: str) -> None:
        value = statistics.live_statistics(
            run_label=args.run_label,
            status=current_status,
            started_at=started_at,
            plan=plan,
            events=events,
            submitted_requests=len(plan),
            active_requests=int(active is not None),
            gpu_samples=monitor.snapshot() if monitor else [],
            gpu_error=monitor.error if monitor else "disabled",
        )
        value.update(
            {
                "mode": "completion-driven",
                "deadline_at": deadline_at,
                "target_normal_ratio": float(profile["mix"]["normal_ratio"]),
                "consecutive_errors": consecutive_errors,
                "consecutive_timeouts": consecutive_timeouts,
                "stop_reason": stop_reason,
            }
        )
        statistics.atomic_write_json(output_dir / "statistics.json", value)

    def write_checkpoint(current_status: str) -> None:
        statistics.atomic_write_json(
            output_dir / "checkpoint.json",
            checkpoint_value(
                status=current_status,
                stop_reason=stop_reason,
                plan=plan,
                events=events,
                deadline_at=deadline_at,
            ),
        )
        statistics.atomic_write_json(
            output_dir / "plan.json",
            plan_document(
                profile_path=profile_path,
                profile=profile,
                hours=hours,
                seed=seed,
                started_at=started_at,
                deadline_at=deadline_at,
                plan=plan,
            ),
        )

    pacing = profile["pacing"]
    execution = profile["execution"]
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    write_checkpoint(status)
    write_statistics(status)
    try:
        while True:
            now = time.monotonic()
            if active is not None and active.done():
                item, result = active.result()
                active = None
                event = traffic_generator.event_from_result(runtime_args, item, result)
                events.append(event)
                dashboard_runner.append_jsonl(output_dir / "events.jsonl", event)
                print(
                    f"{event['request_id']} {event['provider_route']} "
                    f"expected={event['expected_result']} actual={event['actual_result']} "
                    f"match={event['result_matches_expected']} latency_ms={event['latency_ms']}",
                    flush=True,
                )
                if event["completion_status"] == "ok":
                    consecutive_errors = 0
                    consecutive_timeouts = 0
                else:
                    consecutive_errors += 1
                    if event["error_class"] == "agent_probe_timeout":
                        consecutive_timeouts += 1
                    else:
                        consecutive_timeouts = 0
                if consecutive_timeouts >= int(execution["timeout_circuit_breaker_count"]):
                    status = "circuit_breaker"
                    stop_reason = "request timeout; upstream cancellation is not guaranteed"
                elif consecutive_errors >= int(execution["error_circuit_breaker_count"]):
                    status = "circuit_breaker"
                    stop_reason = "consecutive request error limit reached"
                else:
                    next_submit_at = time.monotonic() + random_backoff_seconds(
                        rng,
                        minimum=float(pacing["minimum_backoff_seconds"]),
                        mean=float(pacing["mean_backoff_seconds"]),
                        maximum=float(pacing["maximum_backoff_seconds"]),
                        consecutive_errors=consecutive_errors,
                    )

            if now >= next_statistics:
                write_statistics(status)
                next_statistics = now + statistics_interval
            if now >= next_checkpoint:
                write_checkpoint(status)
                next_checkpoint = now + checkpoint_interval

            if active is None:
                if status == "circuit_breaker":
                    break
                if stop_requested.is_set():
                    status = "interrupted"
                    stop_reason = f"signal {signal_number}"
                    break
                if now >= deadline_monotonic:
                    status = "completed"
                    stop_reason = "wall-clock deadline reached"
                    break
                if len(plan) >= args.maximum_requests:
                    status = "completed"
                    stop_reason = "maximum request limit reached"
                    break
                if now >= next_submit_at:
                    hour_index = int((now - started_monotonic) // 3600)
                    item = mixer.next_item(len(plan) + 1, hour_index)
                    item["submitted_offset_seconds"] = round(now - started_monotonic, 3)
                    plan.append(item)
                    active = executor.submit(
                        lambda planned=item: (
                            planned,
                            traffic_generator.run_agent_probe(runtime_args, inventory_host, planned),
                        )
                    )
            elif stop_requested.is_set():
                status = "stopping"
            elif now >= deadline_monotonic:
                status = "draining"

            time.sleep(0.25)
    finally:
        executor.shutdown(wait=True, cancel_futures=False)
        if monitor:
            monitor.stop()
        write_checkpoint(status)
        write_statistics(status)
        summary = json.loads((output_dir / "statistics.json").read_text(encoding="utf-8"))
        summary["completed_at"] = dashboard_runner.now_iso()
        summary["wall_elapsed_seconds"] = round(time.monotonic() - started_monotonic, 3)
        statistics.atomic_write_json(output_dir / "summary.json", summary)
        statistics.print_path_results(events)
        print(f"status: {status}")
        print(f"stop_reason: {stop_reason}")
        print(f"summary: {output_dir / 'summary.json'}")
    return 128 + signal_number if signal_number else (0 if status == "completed" else 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a completion-driven local workload with one request in flight.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--profile", default="dashboard-completion-driven-24h")
    parser.add_argument("--hours", type=float, default=0, help="Override profile duration.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--scenario", action="append", help="Installed scenario ID; repeat or use comma-separated values.")
    parser.add_argument("--include-candidates", action="store_true", help="Include installed candidate scenarios in the default selection.")
    parser.add_argument("--scenario-family", choices=traffic_generator.SCENARIO_SELECTIONS, default="active")
    parser.add_argument("--maximum-requests", type=int, default=0)
    parser.add_argument("--request-timeout", type=int, default=0)
    parser.add_argument("--label", default="")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=REPO_ROOT / "ansible" / "inventory" / "local.generated.ini",
    )
    parser.add_argument("--host-alias", default="", help="Empty selects the first inventory host.")
    parser.add_argument("--chatbot-namespace", default="chatbot")
    parser.add_argument("--chatbot-deployment", default="chatbot")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if args.hours < 0:
        raise SystemExit("--hours cannot be negative")
    if args.maximum_requests < 0:
        raise SystemExit("--maximum-requests cannot be negative")
    if args.request_timeout and args.request_timeout < 30:
        raise SystemExit("--request-timeout must be at least 30 seconds")
    args.run_label = (
        traffic_generator.slugify(args.label)
        if args.label
        else dt.datetime.now(dt.UTC).strftime("completion-%Y%m%dT%H%M%SZ")
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
