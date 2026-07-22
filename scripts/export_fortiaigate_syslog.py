#!/usr/bin/env python3
"""Export FortiAIGate syslog S3 objects and reconstruct a combined log file."""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
DEFAULT_BACKUP_ROOT = WORKSPACE_ROOT / "backups"
DEFAULT_PREP_MODULE = REPO_ROOT / "terraform" / "aws-prep"
DEFAULT_USER_TFVARS = REPO_ROOT / "terraform" / "user.tfvars"


def run_command(argv: list[str], *, cwd: Path = REPO_ROOT, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(argv)}")
    result = subprocess.run(
        argv,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout, end="")
        if capture and result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


def terraform_output_raw(module_path: Path, output_name: str) -> str:
    result = run_command(
        ["terraform", f"-chdir={module_path}", "output", "-raw", output_name],
        capture=True,
    )
    value = (result.stdout or "").strip()
    return "" if value == "null" else value


def tfvars_string(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    match = re.search(rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*"([^"]*)"', path.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def s3_uri(bucket: str, prefix: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"s3://{bucket}/{clean_prefix}/" if clean_prefix else f"s3://{bucket}/"


def sync_s3(bucket: str, prefix: str, destination: Path, profile: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    argv = ["aws", "s3", "sync", s3_uri(bucket, prefix), str(destination)]
    if profile:
        argv.extend(["--profile", profile])
    run_command(argv)


def list_downloaded_objects(download_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in download_dir.rglob("*")
        if path.is_file() and path.name.endswith(".gz")
    )


def append_file_content(source: Path, output_file) -> int:
    line_count = 0
    with gzip.open(source, "rt", encoding="utf-8", errors="replace") as input_file:
        for line in input_file:
            output_file.write(line.rstrip("\n"))
            output_file.write("\n")
            line_count += 1
    return line_count


def reconstruct(download_dir: Path, combined_path: Path, manifest_path: Path) -> None:
    objects = list_downloaded_objects(download_dir)
    combined_path.parent.mkdir(parents=True, exist_ok=True)

    line_count = 0
    with combined_path.open("w", encoding="utf-8") as output_file:
        for path in objects:
            line_count += append_file_content(path, output_file)

    manifest = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "download_dir": str(download_dir),
        "combined_path": str(combined_path),
        "object_count": len(objects),
        "line_count": line_count,
        "objects": [str(path.relative_to(download_dir)) for path in objects],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Downloaded gzip objects: {len(objects)}")
    print(f"Combined lines: {line_count}")
    print(f"Combined log: {combined_path}")
    print(f"Manifest: {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync FortiAIGate syslog S3 archive objects and reconstruct a combined log file."
    )
    parser.add_argument("--bucket", default="", help="S3 bucket name. Defaults to terraform/aws-prep output.")
    parser.add_argument("--prefix", default="", help="S3 prefix. Defaults to terraform/aws-prep output.")
    parser.add_argument("--profile", default="", help="AWS CLI profile. Defaults to terraform/user.tfvars aws_profile.")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT, help="Backup root directory.")
    parser.add_argument("--label", default="", help="Backup label. Defaults to fortiaigate-syslog-<UTC timestamp>.")
    parser.add_argument("--skip-sync", action="store_true", help="Reconstruct from an existing backup directory.")
    parser.add_argument("--download-dir", type=Path, default=None, help="Existing download directory for --skip-sync.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    label = args.label or f"fortiaigate-syslog-{timestamp}"
    backup_dir = args.download_dir if args.download_dir else args.backup_root / label / "raw"
    combined_path = backup_dir.parent / "fortiaigate-syslog-combined.jsonl"
    manifest_path = backup_dir.parent / "manifest.json"

    bucket = args.bucket or terraform_output_raw(DEFAULT_PREP_MODULE, "fortiaigate_syslog_bucket_name")
    prefix = args.prefix or terraform_output_raw(DEFAULT_PREP_MODULE, "fortiaigate_syslog_prefix")
    profile = args.profile or tfvars_string(DEFAULT_USER_TFVARS, "aws_profile")

    if not bucket:
        raise SystemExit("No syslog bucket provided and terraform output fortiaigate_syslog_bucket_name is empty.")
    if not args.skip_sync:
        sync_s3(bucket, prefix, backup_dir, profile)

    reconstruct(backup_dir, combined_path, manifest_path)


if __name__ == "__main__":
    main()
