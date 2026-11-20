"""Keys tab edge cases for the lab chatbot UI, with a stand-in streamlit module (Change 2026-11-20)."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = REPO_ROOT / "chatbot" / "lab-chatbot" / "chart" / "files"


class FakeStreamlit(types.ModuleType):
    """Records calls; buttons are never pressed; selectboxes return their first option or None."""

    def __init__(self):
        super().__init__("streamlit")
        self.calls, self.session_state = [], _State()
        self.context = types.SimpleNamespace(headers={})  # unsigned: main() at import stops at sign-in

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        if name.startswith("cache"):
            return lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))

        def call(*args, **kwargs):
            self.calls.append((name, args))
            if name == "selectbox":
                options = list(args[1]) if len(args) > 1 else list(kwargs.get("options", []))
                return options[0] if options else None
            if name in ("button", "checkbox", "form_submit_button"):
                return False
            if name == "text_input":
                return ""
            return _Context()
        return call


class _State(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


class _Context:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def load_chatbot(fake):
    import os, tempfile
    key = tempfile.NamedTemporaryFile("wb", delete=False); key.write(b"unit-test-key"); key.close()
    os.environ["LAB_SIGNING_KEY_FILE"] = key.name
    saved = {n: sys.modules.get(n) for n in ("streamlit", "faig_agent", "result_contract")}
    sys.modules["streamlit"] = fake
    sys.modules["faig_agent"] = types.ModuleType("faig_agent")
    rc = types.ModuleType("result_contract"); rc.contains_sensitive = lambda *_: False
    sys.modules["result_contract"] = rc
    sys.path[:0] = [str(FILES), str(REPO_ROOT)]
    try:
        spec = importlib.util.spec_from_file_location("lab_chatbot_ui_test", FILES / "lab_chatbot.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.unlink(key.name)
        os.environ.pop("LAB_SIGNING_KEY_FILE", None)
        del sys.path[:2]
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class KeysTabTests(unittest.TestCase):
    def setUp(self):
        self.st = FakeStreamlit()
        self.bot = load_chatbot(self.st)
        self.st.calls.clear()

    def test_all_keys_missing_shows_empty_state_without_forms(self):
        keys = [{"faig_key_id": "11111111-2222-3333-4444-555555555555", "key_name": "student02_gone",
                 "status": "missing", "scenario_id": "", "action": ""}]
        self.bot.keys_tab({"role": "student"}, "student02", {}, {}, keys, "")
        names = [c[0] for c in self.st.calls]
        self.assertIn("info", names)
        self.assertTrue(any("No active keys" in str(c[1]) for c in self.st.calls if c[0] == "info"))
        self.assertNotIn("selectbox", names)  # no map, hello-world or rotate form

    def test_unmapped_key_gets_map_form(self):
        keys = [{"faig_key_id": "11111111-2222-3333-4444-555555555555", "key_name": "student02_new",
                 "status": "unmapped", "scenario_id": "", "action": ""}]
        self.bot.keys_tab({"role": "student"}, "student02", {}, {}, keys, "")
        self.assertTrue(any(c[0] == "markdown" and "Map a new key" in str(c[1]) for c in self.st.calls))


if __name__ == "__main__":
    unittest.main()
