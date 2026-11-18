from __future__ import annotations

import os
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import fortiaigate_chat_test  # noqa: E402


class FortiAIGateChatTestContractTests(unittest.TestCase):
    def test_cli_defaults_to_canonical_passthrough_without_auth(self) -> None:
        with mock.patch.dict(os.environ, {"BEDROCK_MODEL": "ignored-model"}, clear=True), mock.patch.object(
            sys, "argv", ["fortiaigate_chat_test.py"]
        ):
            args = fortiaigate_chat_test.parse_args()

        self.assertEqual(args.path, "/ai/openai/v1/chat/completions")
        self.assertEqual(args.model, "pass-model")
        self.assertEqual(args.api_key, "")
        self.assertEqual(
            fortiaigate_chat_test.build_headers(args),
            [("Content-Type", "application/json")],
        )

    def test_api_key_file_must_be_owner_only(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key.json"
            path.write_text(json.dumps({"secretKey": "faig_test"}), encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(fortiaigate_chat_test.key_from_file(str(path)), "faig_test")
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                fortiaigate_chat_test.key_from_file(str(path))

    def test_explicit_auth_and_route_headers_are_preserved(self) -> None:
        args = Namespace(
            api_key="client-token",
            api_key_header="Authorization",
            api_key_prefix="Bearer",
            jwt=False,
            header=["X-FAIG-Model-Route: resume-tool-injection"],
        )

        self.assertEqual(
            fortiaigate_chat_test.build_headers(args),
            [
                ("Content-Type", "application/json"),
                ("Authorization", "Bearer client-token"),
                ("X-FAIG-Model-Route", "resume-tool-injection"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
