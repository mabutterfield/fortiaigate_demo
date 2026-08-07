"""Public facade over the shared metadata-driven scenario validator.

The implementation remains shared with the developer load generator for this
release so both tools classify responses and tool traces identically.
"""

from load_test.scenario_validation import *  # noqa: F401,F403
from load_test.scenario_validation import main

__all__ = [name for name in globals() if not name.startswith("_")]
