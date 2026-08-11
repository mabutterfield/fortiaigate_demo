from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "server.py"
TOOLS_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "tools.json"
HIDDEN_TOOL_FIELDS = {
    "data_source",
    "credit_card_expiration",
    "credit_card_cvv",
}


def load_mcp_server():
    spec = importlib.util.spec_from_file_location("faig_mcp_hr_test_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load MCP server: {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DATA_PATH = str(TOOLS_PATH)
    return module


class HrToolFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_mcp_server()

    def assert_hidden_fields_absent(self, record: dict) -> None:
        self.assertTrue(HIDDEN_TOOL_FIELDS.isdisjoint(record))

    def test_employee_tools_hide_fixture_and_unused_card_metadata(self) -> None:
        ok, search = self.server.employee_search({})
        self.assertTrue(ok)
        self.assertEqual(search["count"], 5)
        for record in search["items"]:
            self.assert_hidden_fields_absent(record)

        ok, safe = self.server.employee_lookup({"employee_id": "EMP-5001"})
        self.assertTrue(ok)
        self.assert_hidden_fields_absent(safe)

        ok, sensitive = self.server.employee_sensitive_lookup_demo(
            {"employee_id": "EMP-5001"}
        )
        self.assertTrue(ok)
        self.assert_hidden_fields_absent(sensitive)
        self.assertIn("date_of_birth", sensitive)
        self.assertIn("credit_card_number", sensitive)

        ok, table = self.server.employee_table_with_cc({})
        self.assertTrue(ok)
        for record in table["items"]:
            self.assert_hidden_fields_absent(record)

    def test_detector_friendly_card_fixtures_are_used_for_last_two_employees(self) -> None:
        expected = {
            "EMP-5004": "4111-1111-1111-1111",
            "EMP-5005": "5555-5555-5555-4444",
        }
        for employee_id, card_number in expected.items():
            ok, record = self.server.employee_sensitive_lookup_demo(
                {"employee_id": employee_id}
            )
            self.assertTrue(ok)
            self.assertEqual(record["credit_card_number"], card_number)


if __name__ == "__main__":
    unittest.main()
