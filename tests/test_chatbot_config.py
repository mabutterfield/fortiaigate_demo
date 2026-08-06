from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CHATBOT_PATH = REPO_ROOT / "chatbot" / "app" / "chatbot.py"


def load_chatbot_module():
    streamlit = types.ModuleType("streamlit")
    streamlit.session_state = {}
    httpx = types.ModuleType("httpx")
    httpx.Client = object
    openai = types.ModuleType("openai")
    openai.OpenAI = object

    with mock.patch.dict(
        sys.modules,
        {
            "streamlit": streamlit,
            "httpx": httpx,
            "openai": openai,
        },
    ):
        spec = importlib.util.spec_from_file_location("phase11_chatbot", CHATBOT_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load {CHATBOT_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


chatbot = load_chatbot_module()


class ChatbotConfigurationTests(unittest.TestCase):
    def test_frontend_profiles_parse_and_select_named_instruction(self) -> None:
        configured = [
            {
                "id": "fortistore-injection-compromised",
                "display_name": "Compromised FortiStore Frontend",
                "source_type": "file",
                "scenario_id": "fortistore-injection",
                "instruction": "controlled frontend fixture",
            },
            {
                "id": "none",
                "display_name": "No Frontend Instructions",
                "source_type": "none",
                "instruction": "",
            },
        ]
        with mock.patch.dict(
            os.environ,
            {"TEST_FRONTEND_PROFILES": json.dumps(configured)},
            clear=False,
        ):
            profiles = chatbot.env_json_frontend_profiles("TEST_FRONTEND_PROFILES")

        self.assertEqual(
            chatbot.frontend_profile_by_id(
                profiles,
                "fortistore-injection-compromised",
            )["instruction"],
            "controlled frontend fixture",
        )
        self.assertEqual(
            chatbot.frontend_profile_by_id(profiles, "none")["instruction"],
            "",
        )

    def test_frontend_profiles_add_none_and_preserve_legacy_fallback(self) -> None:
        profiles = chatbot.build_frontend_instruction_profiles([], "legacy fixture")
        self.assertEqual([profile["id"] for profile in profiles], ["none", "legacy"])

    def test_duplicate_frontend_profile_ids_are_rejected(self) -> None:
        value = json.dumps(
            [
                {"id": "duplicate", "instruction": "first"},
                {"id": "duplicate", "instruction": "second"},
            ]
        )
        with mock.patch.dict(
            os.environ,
            {"TEST_FRONTEND_PROFILES": value},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "duplicate id"):
                chatbot.env_json_frontend_profiles("TEST_FRONTEND_PROFILES")

    def test_replace_mode_does_not_expose_builtin_legacy_tool_profiles(self) -> None:
        profiles = chatbot.build_mcp_tool_profiles(
            [
                {
                    "name": "hr-tool-dlp",
                    "label": "HR Tool DLP",
                    "tools": ["employee_search"],
                }
            ],
            mode="replace",
        )
        self.assertEqual([profile["name"] for profile in profiles], ["hr-tool-dlp"])

    def test_replace_mode_without_mcp_scenarios_has_disabled_profile(self) -> None:
        profiles = chatbot.build_mcp_tool_profiles([], mode="replace")
        self.assertEqual(profiles[0]["name"], "none")
        self.assertFalse(profiles[0]["allow_all"])

    def test_empty_header_route_configuration_stays_empty(self) -> None:
        self.assertEqual(chatbot.build_faig_routes("", [], "/v1/intelligent"), [])


if __name__ == "__main__":
    unittest.main()
