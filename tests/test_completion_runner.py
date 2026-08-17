from __future__ import annotations

import random
import unittest
from collections import Counter

from load_test import completion_runner


class CompletionRunnerTests(unittest.TestCase):
    def test_default_profile_is_valid(self) -> None:
        path, profile = completion_runner.load_profile("dashboard-completion-driven-24h")
        self.assertEqual(path.name, "dashboard-completion-driven-24h.json")
        self.assertEqual(profile["mix"]["normal_ratio"], 0.75)

    def test_hourly_queue_covers_every_deny_and_redact_path(self) -> None:
        queue = completion_runner.build_hourly_item_queue(
            random.Random(42),
            cases_by_action={
                "alert": [{"id": "alert-1", "route": "alert"}, {"id": "alert-2", "route": "alert"}],
                "deny": [
                    {"id": "deny-1", "route": "deny"},
                    {"id": "deny-2", "route": "deny"},
                    {"id": "deny-3", "route": "deny"},
                ],
                "redact": [{"id": "redact-1", "route": "redact"}],
            },
            each_path_actions=["deny", "redact"],
            alert_count=1,
            coverage_within_requests=12,
        )
        route_counts = Counter(
            "passthrough" if item is None else item["route"] for item in queue
        )
        self.assertEqual(
            route_counts,
            {"passthrough": 7, "alert": 1, "deny": 3, "redact": 1},
        )
        required_ids = {item["id"] for item in queue if item and item["route"] in {"deny", "redact"}}
        self.assertEqual(required_ids, {"deny-1", "deny-2", "deny-3", "redact-1"})

    def test_hourly_queue_expands_if_required_paths_exceed_window(self) -> None:
        queue = completion_runner.build_hourly_item_queue(
            random.Random(7),
            cases_by_action={
                "alert": [{"id": "alert-1", "route": "alert"}],
                "deny": [
                    {"id": f"deny-{index}", "route": "deny"} for index in range(5)
                ],
                "redact": [{"id": "redact-1", "route": "redact"}],
            },
            each_path_actions=["deny", "redact"],
            alert_count=1,
            coverage_within_requests=4,
        )
        self.assertEqual(len(queue), 15)
        self.assertEqual(
            Counter("passthrough" if item is None else item["route"] for item in queue),
            {"passthrough": 8, "alert": 1, "deny": 5, "redact": 1},
        )

    def test_random_backoff_is_deterministic_and_bounded(self) -> None:
        first_rng = random.Random(99)
        second_rng = random.Random(99)
        first = [
            completion_runner.random_backoff_seconds(
                first_rng, minimum=1, mean=5, maximum=15
            )
            for _ in range(100)
        ]
        second = [
            completion_runner.random_backoff_seconds(
                second_rng, minimum=1, mean=5, maximum=15
            )
            for _ in range(100)
        ]
        self.assertEqual(first, second)
        self.assertTrue(all(1 <= value <= 15 for value in first))
        self.assertGreater(len(set(first)), 1)

    def test_error_backoff_never_exceeds_cap(self) -> None:
        values = [
            completion_runner.random_backoff_seconds(
                random.Random(seed),
                minimum=1,
                mean=5,
                maximum=15,
                consecutive_errors=20,
            )
            for seed in range(100)
        ]
        self.assertTrue(all(1 <= value <= 15 for value in values))


if __name__ == "__main__":
    unittest.main()
