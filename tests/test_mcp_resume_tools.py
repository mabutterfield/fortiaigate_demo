from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp" / "chart" / "files" / "server.py"
DOCUMENT_ROOT = REPO_ROOT / "mcp" / "chart" / "files" / "documents"


def load_mcp_server():
    spec = importlib.util.spec_from_file_location("faig_mcp_resume_test_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load MCP server: {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DOCUMENT_INDEX_PATH = str(DOCUMENT_ROOT / "documents.json")
    module.DOCUMENT_ROOT = DOCUMENT_ROOT
    return module


class ResumeToolFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_mcp_server()

    def test_poisoned_resume_requires_explicit_attack_access(self) -> None:
        ok, blocked = self.server.document_read({"document_id": "RESUME-9001"})
        self.assertFalse(ok)
        self.assertIn("requires include_attack=true", blocked["error"])

        ok, result = self.server.document_read(
            {"document_id": "RESUME-9001", "include_attack": True}
        )
        self.assertTrue(ok)
        self.assertTrue(result["attack_fixture"])
        self.assertIn("cloud inventory", result["content"].lower())
        self.assertIn("ignore all previous instructions", result["content"].lower())
        self.assertIn("reveal the system prompt", result["content"].lower())

    def test_poisoned_resume_reports_injection_and_tool_pivot(self) -> None:
        ok, result = self.server.document_injection_check(
            {"document_id": "RESUME-9001", "include_attack": True}
        )
        self.assertTrue(ok)
        self.assertTrue(result["contains_prompt_injection_indicators"])
        finding_names = {finding["name"] for finding in result["findings"]}
        self.assertIn("ignore_instructions", finding_names)
        self.assertIn("tool_pivot", finding_names)

    def test_upload_and_cloud_tools_are_simulated_only(self) -> None:
        ok, upload = self.server.document_upload_simulation(
            {"document_id": "RESUME-9001", "include_attack": True}
        )
        self.assertTrue(ok)
        self.assertTrue(upload["simulated"])
        self.assertEqual(upload["event"], "pre_staged_document_available")
        self.assertIn("No file was written", upload["message"])

        ok, inventory = self.server.cloud_bucket_list_demo({})
        self.assertTrue(ok)
        self.assertEqual(inventory["source"], "synthetic demo data")
        self.assertEqual(inventory["count"], 2)
        self.assertIn("not an AWS CLI executor", inventory["note"])


if __name__ == "__main__":
    unittest.main()
