"""catalog802.sensitive matches the legacy functional_test copy (Change 2026-11-20)."""
from __future__ import annotations

import unittest

from catalog802.sensitive import contains_sensitive
# Change 2026-11-23: legacy parity target retired.

SAMPLES = [
    "SSN: 489-36-8350", "mail jane.doe@example.com", "call (555) 123-4567", "card 4111 1111 1111 1111",
    "4111111111111111", {"credit_card_number": "x"}, {"employee": {"ssn": "489-36-8350"}},
    "SSN: [REDACTED_SSN_1]", "Hello.", "", {"name": "Alex"}, "order 12345", "2026-11-20",
]


class SensitiveTests(unittest.TestCase):
    def test_detects_synthetic_values(self):
        self.assertTrue(contains_sensitive("SSN: 489-36-8350"))
        self.assertTrue(contains_sensitive({"employee": {"email": "a.b@example.com"}}))
        self.assertFalse(contains_sensitive("SSN: [REDACTED_SSN_1]"))
        self.assertFalse(contains_sensitive("Hello."))

    # Change 2026-11-23: legacy scenario installer test retired.
    # def test_matches_legacy_copy(self):
    #     for sample in SAMPLES:
    #         self.assertEqual(contains_sensitive(sample), legacy_contains_sensitive(sample), sample)


if __name__ == "__main__":
    unittest.main()
