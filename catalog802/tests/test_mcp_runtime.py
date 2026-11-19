import importlib.util
from pathlib import Path
import unittest

from catalog802 import loader
from catalog802.mcp_compile import compile_registry

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('catalog_test_mcp_server', ROOT / 'mcp/chart/files/server.py')
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class McpRuntimeTests(unittest.TestCase):
    def test_catalog_replaces_matching_contracts_and_preserves_legacy(self):
        catalog, errors = loader.load(ROOT)
        self.assertEqual(errors, [])
        compiled = compile_registry(catalog)
        compiled[0]['function']['description'] = 'catalog authoritative'
        merged = SERVER.apply_catalog_registry(SERVER.TOOLS, compiled)
        old_names = {x['function']['name'] for x in SERVER.TOOLS}
        new_names = {x['function']['name'] for x in merged}
        self.assertEqual(old_names, new_names)
        self.assertEqual(len(merged), len(SERVER.TOOLS))
        match = next(x for x in merged if x['function']['name'] == compiled[0]['function']['name'])
        self.assertEqual(match['function']['description'], 'catalog authoritative')

    def test_rejects_duplicate_and_missing_dispatch_names(self):
        catalog, _ = loader.load(ROOT)
        compiled = compile_registry(catalog)
        with self.assertRaisesRegex(ValueError, 'duplicate or lacks'):
            SERVER.apply_catalog_registry(SERVER.TOOLS, [compiled[0], compiled[0]])
        with self.assertRaisesRegex(ValueError, 'duplicate or lacks'):
            SERVER.apply_catalog_registry(SERVER.TOOLS, [{'type':'function','function':{'name':'unknown','description':'','parameters':{}}}])


if __name__ == '__main__':
    unittest.main()
