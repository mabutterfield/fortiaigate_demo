import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from functional_test.catalog_evaluate import main


class CatalogEvaluateTests(unittest.TestCase):
    def test_evaluates_supplied_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'observations.json'
            path.write_text(json.dumps({'execution': 'completed', 'verdict_rows': [{'uuid': 'x', 'verdict': 'alert'}],
                                        'requests_sent': 1, 'evidence': ['sensitive-data-in-tool-result'],
                                        'tools_called': ['employee_sensitive_lookup']}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(['--scenario', 'hr-tool-dlp', '--test', 'alert-attack', '--faig-version', '8.0.2', '--observations', str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())['outcome'], 'pass')

    def test_missing_observations_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'observations.json'
            path.write_text('{}')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--scenario', 'hr-tool-dlp', '--test', 'alert-attack', '--faig-version', '8.0.2', '--observations', str(path)]), 2)


if __name__ == '__main__':
    unittest.main()
