import unittest
from pathlib import Path
from scripts.state_storage import StateLayout, checked_state_identity, resolve_state_root


class StateLayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = StateLayout(Path('/tmp/faig-test-state'))

    def test_default_and_named_workspace_are_separate(self):
        self.assertEqual(self.layout.state_path('aws-ecr', 'default'), Path('/tmp/faig-test-state/aws-ecr/terraform.tfstate').resolve())
        self.assertEqual(self.layout.state_path('aws-ecr', 'ohio-802'), Path('/tmp/faig-test-state/aws-ecr/workspaces/ohio-802/terraform.tfstate').resolve())

    def test_cross_module_dependencies_use_the_same_workspace(self):
        result = self.layout.dependency_vars('aws-fortiweb', 'ohio-802')
        self.assertEqual(len(result), 2)
        self.assertTrue(all('/workspaces/ohio-802/' in item for item in result))
        self.assertTrue(any(item.startswith('aws_ec2_k3s_state_path=') for item in result))

    def test_invalid_inputs_cannot_escape_root(self):
        with self.assertRaises(ValueError):
            self.layout.state_path('aws-ecr', '../../other')
        with self.assertRaises(ValueError):
            self.layout.module_root('../other')
        with self.assertRaises(ValueError):
            StateLayout(Path('relative'))

    def test_external_root_rejects_repo_paths(self):
        workspace = Path('/tmp/faig-workspace').resolve()
        repo = workspace / 'repo'
        self.assertEqual(resolve_state_root('.state', workspace, repo), workspace / '.state')
        with self.assertRaisesRegex(ValueError, 'outside'):
            resolve_state_root(str(repo / 'secrets'), workspace, repo)

    def test_state_identity_ignores_secret_values(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state'
            path.write_text(json.dumps({'lineage': 'synthetic', 'serial': 4, 'resources': [
                {'mode': 'managed', 'instances': [{'attributes': {'secret': 'fictional'}}]},
                {'mode': 'data', 'instances': [{}]}]}))
            self.assertEqual(checked_state_identity(path), ('synthetic', 4, 1))

    def test_backend_config_includes_default_and_workspace_locations(self):
        args = self.layout.backend_args('aws-prep')
        self.assertEqual(len(args), 2)
        self.assertTrue(args[0].startswith('-backend-config=path='))
        self.assertTrue(args[1].startswith('-backend-config=workspace_dir='))


if __name__ == '__main__':
    unittest.main()
