"""Shared catalog vocabulary for 8.0.2 views and later test consumers."""

ACTION_IDS = ("alert", "redact", "block")
EXPECTED_RESULTS = (
    "completed", "blocked", "redacted", "tool-pivot", "sensitive-output", "sensitive-tool-result",
)
LOG_VERDICTS = ("Log", "Alert", "Redact", "Block")
