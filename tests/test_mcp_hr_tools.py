from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "server.py"
TOOLS_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "tools.json"
HIDDEN_TOOL_FIELDS = {
    "data_source",
    "credit_card_number",
    "credit_card_expiration",
    "credit_card_cvv",
    "salary_usd",
    "record_simulated",
    "safe_summary",
    "demo_export_note",
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
        ok, search = self.server.employee_directory({})
        self.assertTrue(ok)
        self.assertEqual(search["count"], 5)
        for record in search["items"]:
            self.assert_hidden_fields_absent(record)
            self.assertEqual(
                set(record),
                {"employee_id", "name", "title", "department", "location"},
            )

        ok, safe = self.server.employee_lookup({"employee_id": "EMP-5001"})
        self.assertTrue(ok)
        self.assert_hidden_fields_absent(safe)
        self.assertEqual(
            set(safe),
            {"employee_id", "name", "title", "department", "location"},
        )

        ok, sensitive = self.server.employee_sensitive_lookup(
            {"employee_id": "EMP-5001"}
        )
        self.assertTrue(ok)
        self.assert_hidden_fields_absent(sensitive)
        self.assertEqual(
            set(sensitive),
            {
                "name",
                "employee_id",
                "location",
                "date_of_birth",
                "ssn",
                "phone",
                "personal_email",
            },
        )

        ok, table = self.server.employee_directory_sensitive({})
        self.assertTrue(ok)
        self.assertEqual(set(table), {"count", "items"})
        for record in table["items"]:
            self.assert_hidden_fields_absent(record)
            self.assertEqual(
                set(record),
                {
                    "employee_id",
                    "name",
                    "location",
                    "date_of_birth",
                    "phone",
                    "ssn",
                    "personal_email",
                },
            )

    def test_payment_card_fixtures_remain_in_source_data_but_are_hidden_from_tools(self) -> None:
        import json

        expected = {
            "EMP-5004": "4111-1111-1111-1111",
            "EMP-5005": "5555-5555-5555-4444",
        }
        for employee_id, card_number in expected.items():
            source_data = json.loads(TOOLS_PATH.read_text(encoding="utf-8"))
            self.assertEqual(source_data["employees"][employee_id]["credit_card_number"], card_number)
            ok, record = self.server.employee_sensitive_lookup({"employee_id": employee_id})
            self.assertTrue(ok)
            self.assertNotIn("credit_card_number", record)

    def test_sensitive_search_normalizes_exact_dob_and_ssn_formats(self) -> None:
        cases = [
            ("date_of_birth", "January 2nd, 1981"),
            ("ssn", "489368350"),
        ]
        for lookup_type, lookup_value in cases:
            with self.subTest(lookup_type=lookup_type):
                ok, result = self.server.employee_sensitive_search_demo(
                    {"lookup_type": lookup_type, "lookup_value": lookup_value}
                )
                self.assertTrue(ok)
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["items"][0]["employee_id"], "EMP-5001")
                self.assert_hidden_fields_absent(result["items"][0])
                self.assertEqual(result["match"]["lookup_type"], lookup_type)

    def test_sensitive_search_returns_a_consistent_no_match_result(self) -> None:
        ok, result = self.server.employee_sensitive_search_demo(
            {"lookup_type": "date_of_birth", "lookup_value": "1970-01-01"}
        )
        self.assertTrue(ok)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["message"], "No employee found")

    def test_sensitive_all_lookup_returns_every_full_synthetic_record(self) -> None:
        ok, result = self.server.employee_sensitive_all_lookup_demo({})
        self.assertTrue(ok)
        self.assertEqual(result["count"], 5)
        self.assertEqual(len(result["items"]), 5)
        self.assertEqual(result["match"], {"lookup_type": "all_records", "match_mode": "all"})
        self.assertEqual(result["data_classification"], "synthetic sensitive DLP demo data")
        for record in result["items"]:
            self.assert_hidden_fields_absent(record)
            self.assertIn("date_of_birth", record)
            self.assertIn("ssn", record)
            self.assertNotIn("credit_card_number", record)
            self.assertNotIn("salary_usd", record)

        tool_names = {
            tool["function"]["name"]
            for tool in self.server.TOOLS
            if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
        }
        self.assertIn("employee_directory", tool_names)
        self.assertIn("employee_directory_sensitive", tool_names)
        self.assertIn("employee_sensitive_lookup", tool_names)

    def test_sensitive_search_rejects_invalid_lookup_contracts(self) -> None:
        ok, result = self.server.employee_sensitive_search_demo(
            {"lookup_type": "employee_id", "lookup_value": "EMP-5001"}
        )
        self.assertFalse(ok)
        self.assertIn("lookup_type", result["error"])

        ok, result = self.server.employee_sensitive_search_demo(
            {"lookup_type": "ssn", "lookup_value": "1234"}
        )
        self.assertFalse(ok)
        self.assertIn("nine digits", result["error"])

        ok, result = self.server.employee_sensitive_search_demo(
            {"lookup_type": "credit_card_number", "lookup_value": "4929 3813 3266 4295"}
        )
        self.assertFalse(ok)
        self.assertIn("date_of_birth or ssn", result["error"])


if __name__ == "__main__":
    unittest.main()
