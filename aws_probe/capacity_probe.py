#!/usr/bin/env python3
"""Safely probe point-in-time EC2 On-Demand capacity in isolated VPCs.

This deliberately uses the AWS CLI rather than Terraform or an SDK dependency.
It is not a deployment tool and never creates FortiAIGate resources.  A successful
RunInstances response only proves that AWS allocated capacity at that instant.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "reports"
DEFAULT_HISTORY_PATH = SCRIPT_DIR / "capacity_history.md"
QUOTA_ERROR_CODES = {"VcpuLimitExceeded", "InstanceLimitExceeded", "MaxSpotInstanceCountExceeded"}
CAPACITY_ERROR_CODES = {
    "InsufficientInstanceCapacity",
    "InsufficientHostCapacity",
    "InsufficientReservedInstanceCapacity",
    "UnfulfillableCapacity",
}


@dataclass
class AwsError(Exception):
    command: list[str]
    returncode: int
    stderr: str
    code: str = "UnknownAwsError"

    def __str__(self) -> str:
        return self.stderr.strip() or "AWS CLI command failed"


@dataclass
class ProbeResult:
    region: str
    instance_type: str
    availability_zone: str
    zone_id: str | None
    outcome: str
    detail: str
    elapsed_seconds: float
    instance_id: str | None = None


@dataclass
class RegionResources:
    vpc_id: str | None = None
    security_group_id: str | None = None
    subnet_ids: list[str] = field(default_factory=list)
    instance_ids: list[str] = field(default_factory=list)


class AwsCli:
    def __init__(self, profile: str | None, region: str, *, verbose: bool = False) -> None:
        self.profile = profile
        self.region = region
        self.verbose = verbose

    def call(self, *args: str, json_output: bool = True) -> Any:
        command = ["aws", "--no-cli-pager"]
        if self.profile:
            command.extend(["--profile", self.profile])
        command.extend(["--region", self.region, *args])
        if json_output:
            command.extend(["--output", "json"])
        if self.verbose:
            print("+", " ".join(command), file=sys.stderr)
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise AwsError(command, completed.returncode, completed.stderr, aws_error_code(completed.stderr))
        if not json_output or not completed.stdout.strip():
            return None
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"AWS CLI did not return JSON: {completed.stdout}") from exc


def aws_error_code(stderr: str) -> str:
    match = re.search(r"An error occurred \(([^)]+)\)", stderr)
    return match.group(1) if match else "UnknownAwsError"


def classify_error(error: AwsError) -> str:
    if error.code in QUOTA_ERROR_CODES:
        return "quota_error"
    if error.code in CAPACITY_ERROR_CODES:
        return "capacity_unavailable"
    return "aws_error"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tag_spec(resource_type: str, tags: dict[str, str]) -> str:
    rendered = ",".join(f"{{Key={key},Value={value}}}" for key, value in tags.items())
    return f"ResourceType={resource_type},Tags=[{rendered}]"


def cleanup_tags(run_id: str) -> dict[str, str]:
    return {
        "Name": f"faig-capacity-probe-{run_id}",
        "Project": "FortiAIGate",
        "Purpose": "temporary-ec2-capacity-probe",
        "RunId": run_id,
        "ExpiresAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).replace(microsecond=0).isoformat(),
    }


def get_account_identity(aws: AwsCli) -> dict[str, str]:
    return aws.call("sts", "get-caller-identity")


def get_candidate_zones(aws: AwsCli, instance_type: str) -> list[dict[str, str]]:
    zones = aws.call(
        "ec2",
        "describe-availability-zones",
        "--all-availability-zones",
        "--filters",
        "Name=state,Values=available",
    ).get("AvailabilityZones", [])
    zone_ids = {
        zone["ZoneName"]: zone.get("ZoneId")
        for zone in zones
        if zone.get("ZoneType", "availability-zone") == "availability-zone"
    }
    offerings = aws.call(
        "ec2",
        "describe-instance-type-offerings",
        "--location-type",
        "availability-zone",
        "--filters",
        f"Name=instance-type,Values={instance_type}",
    ).get("InstanceTypeOfferings", [])
    offered = {entry["Location"] for entry in offerings}
    return [
        {"name": zone_name, "id": zone_ids[zone_name]}
        for zone_name in sorted(offered)
        if zone_name in zone_ids
    ]


def get_g_vt_quota(aws: AwsCli) -> dict[str, Any]:
    """Read the standard EC2 G/VT On-Demand vCPU quota when permitted.

    The API does not provide a per-family instantaneous usage calculation, so the
    value is advisory only and must not be treated as a capacity result.
    """
    try:
        quota = aws.call(
            "service-quotas",
            "get-service-quota",
            "--service-code",
            "ec2",
            "--quota-code",
            "L-DB2E81BA",
        ).get("Quota", {})
        return {"status": "available", "name": quota.get("QuotaName"), "value": quota.get("Value")}
    except AwsError as error:
        return {"status": "unavailable", "error_code": error.code, "detail": str(error)}


def create_resources(aws: AwsCli, run_id: str, zones: list[dict[str, str]]) -> RegionResources:
    tags = cleanup_tags(run_id)
    resources = RegionResources()
    try:
        vpc = aws.call("ec2", "create-vpc", "--cidr-block", "10.254.0.0/16", "--tag-specifications", tag_spec("vpc", tags))
        resources.vpc_id = vpc["Vpc"]["VpcId"]
        group = aws.call(
            "ec2",
            "create-security-group",
            "--group-name",
            f"faig-capacity-probe-{run_id}",
            "--description",
            "Temporary FortiAIGate EC2 capacity probe; no ingress rules.",
            "--vpc-id",
            resources.vpc_id,
            "--tag-specifications",
            tag_spec("security-group", tags),
        )
        resources.security_group_id = group["GroupId"]
        for index, zone in enumerate(zones):
            cidr = f"10.254.{index * 16}.0/20"
            subnet = aws.call(
                "ec2",
                "create-subnet",
                "--vpc-id",
                resources.vpc_id,
                "--availability-zone",
                zone["name"],
                "--cidr-block",
                cidr,
                "--tag-specifications",
                tag_spec("subnet", tags),
            )
            zone["subnet_id"] = subnet["Subnet"]["SubnetId"]
            resources.subnet_ids.append(zone["subnet_id"])
    except Exception:
        cleanup_resources(aws, resources)
        raise
    return resources


def resolve_ami(aws: AwsCli) -> str:
    parameter = aws.call(
        "ssm",
        "get-parameter",
        "--name",
        "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
    )
    return parameter["Parameter"]["Value"]


def probe_zone(
    aws: AwsCli,
    resources: RegionResources,
    run_id: str,
    instance_type: str,
    zone: dict[str, str],
    image_id: str,
) -> ProbeResult:
    started = time.monotonic()
    try:
        response = aws.call(
            "ec2",
            "run-instances",
            "--image-id",
            image_id,
            "--instance-type",
            instance_type,
            "--count",
            "1",
            "--subnet-id",
            zone["subnet_id"],
            "--security-group-ids",
            resources.security_group_id or "",
            "--tag-specifications",
            tag_spec("instance", cleanup_tags(run_id)),
            tag_spec("volume", cleanup_tags(run_id)),
        )
        instance = response["Instances"][0]
        instance_id = instance["InstanceId"]
        resources.instance_ids.append(instance_id)
        state = instance.get("State", {}).get("Name", "pending")
        return ProbeResult(
            region=aws.region,
            instance_type=instance_type,
            availability_zone=zone["name"],
            zone_id=zone.get("id"),
            outcome="capacity_available",
            detail=f"RunInstances accepted; instance entered {state} state and will be terminated.",
            elapsed_seconds=round(time.monotonic() - started, 3),
            instance_id=instance_id,
        )
    except AwsError as error:
        return ProbeResult(
            region=aws.region,
            instance_type=instance_type,
            availability_zone=zone["name"],
            zone_id=zone.get("id"),
            outcome=classify_error(error),
            detail=f"{error.code}: {str(error)}",
            elapsed_seconds=round(time.monotonic() - started, 3),
        )


def terminate_completed_probe(aws: AwsCli, resources: RegionResources, result: ProbeResult) -> None:
    """Release an accepted GPU allocation before testing the next AZ.

    This keeps the probe sequential and prevents successful 32-vCPU allocations
    from causing a later AZ to report a misleading quota failure.
    """
    if not result.instance_id:
        return
    try:
        aws.call("ec2", "terminate-instances", "--instance-ids", result.instance_id)
        wait_for_termination(aws, [result.instance_id])
        resources.instance_ids.remove(result.instance_id)
        result.detail += " Termination confirmed before the next AZ probe."
    except Exception as error:  # Final cleanup retains the ID and retries if this step fails.
        result.detail += f" WARNING: immediate termination was not confirmed: {error}"


def wait_for_termination(aws: AwsCli, instance_ids: list[str], timeout_seconds: int = 900) -> None:
    if not instance_ids:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = aws.call("ec2", "describe-instances", "--instance-ids", *instance_ids)
        states = {
            instance["State"]["Name"]
            for reservation in response.get("Reservations", [])
            for instance in reservation.get("Instances", [])
        }
        if states == {"terminated"}:
            return
        time.sleep(5)
    raise TimeoutError(f"Timed out waiting for instances to terminate: {', '.join(instance_ids)}")


def cleanup_resources(aws: AwsCli, resources: RegionResources) -> list[str]:
    notes: list[str] = []
    if resources.instance_ids:
        try:
            aws.call("ec2", "terminate-instances", "--instance-ids", *resources.instance_ids)
            wait_for_termination(aws, resources.instance_ids)
            notes.append(f"terminated {len(resources.instance_ids)} probe instance(s)")
        except Exception as error:  # Cleanup continues for every resource it can remove.
            notes.append(f"WARNING: could not confirm instance termination: {error}")
    for subnet_id in reversed(resources.subnet_ids):
        try:
            aws.call("ec2", "delete-subnet", "--subnet-id", subnet_id)
        except AwsError as error:
            notes.append(f"WARNING: could not delete subnet {subnet_id}: {error.code}")
    if resources.security_group_id:
        try:
            aws.call("ec2", "delete-security-group", "--group-id", resources.security_group_id)
        except AwsError as error:
            notes.append(f"WARNING: could not delete security group {resources.security_group_id}: {error.code}")
    if resources.vpc_id:
        try:
            aws.call("ec2", "delete-vpc", "--vpc-id", resources.vpc_id)
            notes.append(f"deleted temporary VPC {resources.vpc_id}")
        except AwsError as error:
            notes.append(f"WARNING: could not delete VPC {resources.vpc_id}: {error.code}")
    return notes


def probe_region(
    args: argparse.Namespace,
    region: str,
    instance_types: list[str],
    run_id: str,
    report: dict[str, Any],
    history: dict[tuple[str, str, str], dict[str, str]],
) -> None:
    aws = AwsCli(args.profile, region, verbose=args.verbose)
    region_report: dict[str, Any] = {"quota": get_g_vt_quota(aws), "instance_types": {}}
    report["regions"][region] = region_report
    for instance_type in instance_types:
        type_report: dict[str, Any] = {"candidate_zones": [], "results": [], "cleanup": []}
        region_report["instance_types"][instance_type] = type_report
        zones = get_candidate_zones(aws, instance_type)
        type_report["candidate_zones"] = [{"name": zone["name"], "id": zone.get("id")} for zone in zones]
        if not zones:
            type_report["results"].append(
                asdict(ProbeResult(region, instance_type, "", None, "not_offered", "No available AZs offer this instance type.", 0.0))
            )
            continue
        if args.availability_zone:
            zones = [zone for zone in zones if zone["name"] in args.availability_zone]
        if not zones:
            type_report["results"].append(
                asdict(ProbeResult(region, instance_type, "", None, "not_offered", "Requested AZs do not offer this instance type.", 0.0))
            )
            continue
        if not args.all_zones:
            zones = zones[:1]
        zones_to_probe: list[dict[str, str]] = []
        for zone in zones:
            previous = None if args.refresh else recent_history_entry(
                history,
                instance_type,
                region,
                zone["name"],
                args.cache_days,
            )
            if previous:
                type_report["results"].append(
                    asdict(
                        ProbeResult(
                            region,
                            instance_type,
                            zone["name"],
                            zone.get("id"),
                            "skipped_recent_result",
                            f"Skipped: last result was {previous['status']} at {previous['checked_at']}. Use --refresh to probe again.",
                            0.0,
                        )
                    )
                )
            else:
                zones_to_probe.append(zone)
        if not zones_to_probe:
            continue
        resources = RegionResources()
        try:
            resources = create_resources(aws, run_id, zones_to_probe)
            image_id = resolve_ami(aws)
            type_report["ami_id"] = image_id
            for zone in zones_to_probe:
                result = probe_zone(aws, resources, run_id, instance_type, zone, image_id)
                if result.outcome == "capacity_available":
                    terminate_completed_probe(aws, resources, result)
                type_report["results"].append(asdict(result))
                if result.outcome == "capacity_available" and args.stop_on_first_success:
                    break
        except AwsError as error:
            type_report["results"].append(
                asdict(ProbeResult(region, instance_type, "", None, classify_error(error), f"{error.code}: {error}", 0.0))
            )
        finally:
            type_report["cleanup"] = cleanup_resources(aws, resources)


def print_summary(report: dict[str, Any]) -> None:
    print("\nEC2 capacity probe summary")
    print(f"Run ID: {report['run_id']}  Started: {report['started_at']}")
    for region, region_report in report["regions"].items():
        quota = region_report["quota"]
        quota_text = f"{quota.get('name')}: {quota.get('value')} vCPUs" if quota["status"] == "available" else f"unavailable ({quota.get('error_code')})"
        print(f"\n{region} — G/VT quota: {quota_text}")
        for instance_type, type_report in region_report["instance_types"].items():
            results = type_report["results"]
            if not results:
                print(f"  {instance_type}: no result")
                continue
            for result in results:
                zone = result["availability_zone"] or "n/a"
                print(f"  {instance_type:<12} {zone:<12} {result['outcome']:<20} {result['detail'].splitlines()[0]}")
    print("\nA successful result is point-in-time evidence only; it does not reserve EC2 capacity.")


def write_report(report: dict[str, Any], requested_path: str | None) -> Path:
    destination = Path(requested_path).expanduser() if requested_path else REPORTS_DIR / f"capacity-probe-{report['run_id']}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def history_key(instance_type: str, region: str, availability_zone: str) -> tuple[str, str, str]:
    return instance_type, region, availability_zone


def markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ").strip()


def load_history(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    """Read the simple table managed by this script, ignoring prose around it."""
    if not path.exists():
        return {}
    records: dict[tuple[str, str, str], dict[str, str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        if len(cells) != 7 or cells[0] in {"Instance type", "---"} or set(cells[0]) == {"-"}:
            continue
        instance_type, region, availability_zone, zone_id, status, checked_at, detail = cells
        if not instance_type or not region or not availability_zone:
            continue
        records[history_key(instance_type, region, availability_zone)] = {
            "zone_id": zone_id,
            "status": status,
            "checked_at": checked_at,
            "detail": detail,
        }
    return records


def parse_history_time(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recent_history_entry(
    history: dict[tuple[str, str, str], dict[str, str]],
    instance_type: str,
    region: str,
    availability_zone: str,
    max_age_days: int,
) -> dict[str, str] | None:
    entry = history.get(history_key(instance_type, region, availability_zone))
    if not entry:
        return None
    checked_at = parse_history_time(entry.get("checked_at", ""))
    if not checked_at:
        return None
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max_age_days)
    return entry if checked_at >= cutoff else None


def update_history(path: Path, report: dict[str, Any]) -> int:
    """Merge actual attempt results into the portable Markdown history table."""
    history = load_history(path)
    finished_at = report.get("finished_at") or utc_now()
    changed = 0
    for region, region_report in report.get("regions", {}).items():
        for instance_type, type_report in region_report.get("instance_types", {}).items():
            for result in type_report.get("results", []):
                availability_zone = result.get("availability_zone")
                outcome = result.get("outcome")
                if not availability_zone or outcome in {"skipped_recent_result", "not_offered"}:
                    continue
                history[history_key(instance_type, region, availability_zone)] = {
                    "zone_id": result.get("zone_id") or "",
                    "status": outcome,
                    "checked_at": finished_at,
                    "detail": compact_history_detail(outcome, result.get("detail", "")),
                }
                changed += 1
    rows = []
    for (instance_type, region, availability_zone), entry in sorted(history.items()):
        rows.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    instance_type,
                    region,
                    availability_zone,
                    entry.get("zone_id"),
                    entry.get("status"),
                    entry.get("checked_at"),
                    entry.get("detail"),
                )
            )
            + " |"
        )
    contents = [
        "# EC2 Capacity Probe History",
        "",
        "Point-in-time results written by `capacity_probe.py`. A `capacity_available` result means `RunInstances` accepted a short-lived On-Demand request; it is not a reservation and can change at any time.",
        "",
        "By default, the probe skips a recorded AZ/type pair for seven days. Use `--refresh` to force a new allocation attempt, or `--cache-days` to choose a different freshness window.",
        "",
        "| Instance type | Region | Availability Zone | Zone ID | Last status | Last checked (UTC) | Detail |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(contents), encoding="utf-8")
    return changed


def compact_history_detail(outcome: str, detail: str) -> str:
    """Keep the Markdown database scannable; JSON reports retain full AWS text."""
    if outcome == "capacity_available":
        return "RunInstances accepted; termination confirmed." if "Termination confirmed" in detail else "RunInstances accepted."
    if outcome == "capacity_unavailable":
        return "AWS returned InsufficientInstanceCapacity."
    if outcome == "quota_error":
        code = detail.split(":", 1)[0] or "quota error"
        return f"AWS returned {code}."
    if outcome == "aws_error":
        code = detail.split(":", 1)[0] or "AWS error"
        return f"AWS returned {code}."
    return detail.splitlines()[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create isolated temporary EC2 resources and probe On-Demand capacity. Requires --execute for AWS writes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--profile", help="AWS CLI profile; AWS CLI default resolution applies when omitted.")
    parser.add_argument("--region", action="append", help="AWS region to probe; repeat for multiple regions.")
    parser.add_argument("--instance-type", action="append", help="EC2 instance type to probe; repeat for multiple types.")
    parser.add_argument("--availability-zone", action="append", help="Restrict probes to named AZs; repeat as needed.")
    parser.add_argument("--all-zones", action="store_true", help="Probe every offered candidate AZ instead of only the first one.")
    parser.add_argument("--stop-on-first-success", action="store_true", help="Stop testing further AZs for a type after capacity is found.")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY_PATH), help="Markdown capacity-history database.")
    parser.add_argument("--cache-days", type=int, default=7, help="Skip a recorded AZ/type result newer than this many days.")
    parser.add_argument("--refresh", action="store_true", help="Ignore recent history and perform every requested capacity attempt.")
    parser.add_argument("--record-report", help="Import an existing JSON probe report into --history without contacting AWS.")
    parser.add_argument("--execute", action="store_true", help="Permit temporary VPC/subnet/EC2 creation. Without it, print the intended probe only.")
    parser.add_argument("--report", help="Write JSON report here; defaults to ignored aws_probe/reports/.")
    parser.add_argument("--verbose", action="store_true", help="Print AWS CLI commands to stderr.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cache_days < 0:
        print("--cache-days must be zero or greater.", file=sys.stderr)
        return 2
    history_path = Path(args.history).expanduser()
    if args.record_report:
        report = json.loads(Path(args.record_report).expanduser().read_text(encoding="utf-8"))
        updated = update_history(history_path, report)
        print(f"Imported {updated} attempt result(s) into {history_path}")
        return 0
    if not args.region or not args.instance_type:
        print("--region and --instance-type are required unless --record-report is used.", file=sys.stderr)
        return 2
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    if not args.execute:
        print("Dry run only. Add --execute to create and immediately clean up temporary AWS resources.")
        print(f"Regions: {', '.join(args.region)}")
        print(f"Instance types: {', '.join(args.instance_type)}")
        return 0
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": utc_now(),
        "profile": args.profile or "AWS CLI default chain",
        "requested_regions": args.region,
        "requested_instance_types": args.instance_type,
        "all_zones": args.all_zones,
        "stop_on_first_success": args.stop_on_first_success,
        "identity": {},
        "regions": {},
    }
    history = load_history(history_path)
    try:
        identity = get_account_identity(AwsCli(args.profile, args.region[0], verbose=args.verbose))
        report["identity"] = {key: identity.get(key) for key in ("Account", "Arn", "UserId")}
        for region in args.region:
            probe_region(args, region, args.instance_type, run_id, report, history)
    except KeyboardInterrupt:
        report["interrupted"] = True
        print("\nInterrupted. Cleanup for the current type was attempted; inspect the report and RunId tags.", file=sys.stderr)
    except AwsError as error:
        report["fatal_error"] = {"code": error.code, "detail": str(error)}
        print(f"AWS error: {error.code}: {error}", file=sys.stderr)
    finally:
        report["finished_at"] = utc_now()
        report_path = write_report(report, args.report)
        updated = update_history(history_path, report)
        print_summary(report)
        print(f"\nJSON report: {report_path}")
        print(f"Capacity history: {history_path} ({updated} result(s) updated)")
    return 1 if report.get("fatal_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
