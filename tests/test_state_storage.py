import unittest
from pathlib import Path
from scripts.state_storage import StateLayout, checked_state_identity, resolve_state_root, read_state_settings, write_state_settings


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

    def test_private_state_settings_round_trip_and_disable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state-settings.json'
            self.assertIsNone(read_state_settings(path))
            write_state_settings(path, self.layout)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(read_state_settings(path), self.layout)
            write_state_settings(path, None)
            self.assertIsNone(read_state_settings(path))
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'private'):
                read_state_settings(path)

    def test_state_settings_symlink_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings'
            path.symlink_to(Path(directory) / 'elsewhere')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                write_state_settings(path, self.layout)

    def test_real_local_backend_migrates_two_workspaces(self):
        import json
        import shutil
        import subprocess
        import tempfile
        if not shutil.which('terraform'):
            self.skipTest('terraform is unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / 'module'
            module.mkdir()
            (module / 'main.tf').write_text('terraform {\n backend "local" {}\n}\noutput "synthetic" { value = "example" }\n')
            layout = StateLayout((root / 'state').resolve())
            def terraform(*args):
                return subprocess.run(['terraform', '-chdir=' + str(module), *args],
                                      check=True, capture_output=True, text=True)
            terraform('init', '-input=false')
            terraform('apply', '-input=false', '-auto-approve')
            terraform('workspace', 'new', 'ohio-802')
            terraform('apply', '-input=false', '-auto-approve')
            source = {'default': module / 'terraform.tfstate',
                      'ohio-802': module / 'terraform.tfstate.d/ohio-802/terraform.tfstate'}
            before = {ws: checked_state_identity(path) for ws, path in source.items()}
            terraform('init', '-input=false', '-migrate-state', '-force-copy', *layout.backend_args('aws-ecr'))
            for workspace, identity in before.items():
                self.assertEqual(checked_state_identity(layout.state_path('aws-ecr', workspace)), identity)

    def test_backend_config_includes_default_and_workspace_locations(self):
        args = self.layout.backend_args('aws-prep')
        self.assertEqual(len(args), 2)
        self.assertTrue(args[0].startswith('-backend-config=path='))
        self.assertTrue(args[1].startswith('-backend-config=workspace_dir='))


if __name__ == '__main__':
    unittest.main()
