"""Focused unit tests for capacity probe classification and harmless helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capacity_probe  # noqa: E402


class CapacityProbeTests(unittest.TestCase):
    def test_classifies_quota_error(self) -> None:
        error = capacity_probe.AwsError([], 255, "An error occurred (VcpuLimitExceeded) when calling RunInstances", "VcpuLimitExceeded")
        self.assertEqual(capacity_probe.classify_error(error), "quota_error")

    def test_classifies_capacity_error(self) -> None:
        error = capacity_probe.AwsError([], 255, "An error occurred (InsufficientInstanceCapacity) when calling RunInstances", "InsufficientInstanceCapacity")
        self.assertEqual(capacity_probe.classify_error(error), "capacity_unavailable")

    def test_tag_spec_is_aws_cli_shorthand(self) -> None:
        self.assertEqual(
            capacity_probe.tag_spec("instance", {"Name": "probe", "RunId": "abc"}),
            "ResourceType=instance,Tags=[{Key=Name,Value=probe},{Key=RunId,Value=abc}]",
        )

    def test_error_code_parser(self) -> None:
        self.assertEqual(
            capacity_probe.aws_error_code("An error occurred (InsufficientInstanceCapacity) when calling the RunInstances operation"),
            "InsufficientInstanceCapacity",
        )

    def test_history_round_trip_and_recent_entry(self) -> None:
        report = {
            "finished_at": "2026-08-17T20:00:00Z",
            "regions": {
                "us-east-2": {
                    "instance_types": {
                        "g6.8xlarge": {
                            "results": [
                                {
                                    "availability_zone": "us-east-2a",
                                    "zone_id": "use2-az1",
                                    "outcome": "capacity_available",
                                    "detail": "RunInstances accepted.",
                                }
                            ]
                        }
                    }
                }
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.md"
            self.assertEqual(capacity_probe.update_history(path, report), 1)
            history = capacity_probe.load_history(path)
        entry = history[("g6.8xlarge", "us-east-2", "us-east-2a")]
        self.assertEqual(entry["status"], "capacity_available")
        self.assertEqual(entry["zone_id"], "use2-az1")

    def test_recent_history_entry_uses_fresh_timestamp(self) -> None:
        history = {
            ("g6.8xlarge", "us-east-2", "us-east-2a"): {
                "checked_at": "2026-08-17T20:00:00Z",
                "status": "capacity_available",
            }
        }
        entry = capacity_probe.recent_history_entry(history, "g6.8xlarge", "us-east-2", "us-east-2a", 7)
        self.assertEqual(entry["status"], "capacity_available")

    def test_history_detail_is_compact(self) -> None:
        self.assertEqual(
            capacity_probe.compact_history_detail("capacity_unavailable", "InsufficientInstanceCapacity: very long AWS diagnostic"),
            "AWS returned InsufficientInstanceCapacity.",
        )


if __name__ == "__main__":
    unittest.main()
