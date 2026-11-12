#!/usr/bin/env python3
"""Select a whole, unpartitioned AWS EC2 instance-store NVMe disk."""
import json
import os
import sys

MODEL = "Amazon EC2 NVMe Instance Storage"


def select_device(devices, configured="", root_devices=()):
    roots = {os.path.realpath(path) for path in root_devices}
    candidates = [d for d in devices if d.get("type") == "disk" and
                  (d.get("model") or "").strip() == MODEL and
                  os.path.basename(d.get("path", "")).startswith("nvme")]
    if configured:
        candidates = [d for d in candidates if os.path.realpath(d["path"]) == os.path.realpath(configured)]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one EC2 NVMe instance-store disk; specify the device if there are several")
    disk = candidates[0]
    if os.path.realpath(disk["path"]) in roots:
        raise ValueError("Refusing a disk backing the root filesystem")
    if disk.get("children"):
        raise ValueError("Refusing instance store with partitions or mapped devices")
    return disk["path"]


def main():
    data = json.load(sys.stdin)
    try:
        print(select_device(data["blockdevices"], sys.argv[1], sys.argv[2:]))
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
