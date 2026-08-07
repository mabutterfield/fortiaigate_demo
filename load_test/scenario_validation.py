"""Compatibility import for the operator-owned functional validator.

New code imports :mod:`functional_test.validation`. This module remains only
for local scripts or notebooks that imported the earlier path.
"""

from functional_test.validation import *  # noqa: F401,F403
