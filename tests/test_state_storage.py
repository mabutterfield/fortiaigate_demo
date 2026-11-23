import unittest
from pathlib import Path
from scripts.state_storage import StateLayout, checked_state_identity, resolve_state_root, read_state_settings, write_state_settings, check_migration_source, verify_migrated_states, archive_migrated_sources, migrate_one_module, StorageSettings, read_storage_settings, write_storage_settings, prepare_external_module, discover_worktree_states, backup_legacy_states, build_migration_plan, migrate_plan, activate_storage_settings


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
            self.assertEqual(checked_state_identity(path)[:3], ('synthetic', 4, 1))

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

    def test_migration_collision_is_refused(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / 'old'
            module.mkdir()
            (module / 'terraform.tfstate').write_text(json.dumps({'lineage': 'id', 'serial': 1, 'resources': []}))
            layout = StateLayout((root / 'state').resolve())
            expected = check_migration_source(module, layout, 'aws-ecr')
            self.assertEqual(expected['default'][:3], ('id', 1, 0))
            target = layout.module_root('aws-ecr')
            target.mkdir(parents=True)
            (target / 'other').write_text('occupied')
            with self.assertRaisesRegex(ValueError, 'not empty'):
                check_migration_source(module, layout, 'aws-ecr')
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                verify_migrated_states(layout, 'aws-ecr', expected)

    def test_verified_source_is_archived_privately(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'old'
            old.mkdir()
            source = old / 'terraform.tfstate'
            source.write_text(json.dumps({'lineage': 'x', 'serial': 2, 'resources': []}))
            backup = old / 'terraform.tfstate.backup'
            backup.write_text('fictional-backup')
            layout = StateLayout((root / 'new').resolve())
            expected = check_migration_source(old, layout, 'aws-ecr')
            target = layout.state_path('aws-ecr', 'default')
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
            archive = root / 'archive'
            archive_migrated_sources(old, layout, 'aws-ecr', expected, archive)
            self.assertFalse(source.exists())
            self.assertFalse(backup.exists())
            self.assertEqual((archive / 'default' / 'terraform.tfstate').stat().st_mode & 0o777, 0o600)
            self.assertEqual((archive / 'default' / 'terraform.tfstate.backup').read_text(), 'fictional-backup')
            self.assertTrue(target.exists())

    def test_module_migration_archives_both_original_workspaces(self):
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
                return subprocess.run(['terraform', '-chdir=' + str(module), *args], check=True, capture_output=True, text=True)
            terraform('init', '-input=false')
            terraform('apply', '-input=false', '-auto-approve')
            terraform('workspace', 'new', 'ohio-802')
            terraform('apply', '-input=false', '-auto-approve')
            original = check_migration_source(module, layout, 'aws-ecr')
            migrate_one_module(module, layout, 'aws-ecr', root / 'private-archive')
            verify_migrated_states(layout, 'aws-ecr', original)
            self.assertFalse((module / 'terraform.tfstate').exists())
            self.assertFalse((module / 'terraform.tfstate.d/ohio-802/terraform.tfstate').exists())
            self.assertTrue((root / 'private-archive/default/terraform.tfstate').is_file())
            self.assertTrue((root / 'private-archive/ohio-802/terraform.tfstate').is_file())

    def test_coordinated_paths_are_private_and_cannot_overlap(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            file = base / 'settings.json'
            expected = StorageSettings(base / '.secrets', StateLayout(base / '.state'))
            write_storage_settings(file, expected)
            self.assertEqual(read_storage_settings(file), expected)
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            local = StorageSettings(base / '.secrets', None)
            write_storage_settings(file, local)
            self.assertEqual(read_storage_settings(file), local)
            with self.assertRaisesRegex(ValueError, 'must not overlap'):
                StorageSettings(base / '.state' / 'secrets', StateLayout(base / '.state'))
            with self.assertRaisesRegex(ValueError, 'must not overlap'):
                StorageSettings(base / '.secrets', StateLayout(base / '.secrets'))

    def test_external_initialization_refuses_unmigrated_or_missing_required_state(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            module = root / 'module'
            module.mkdir()
            layout = StateLayout(root / 'state')
            with self.assertRaisesRegex(ValueError, 'required external state is missing'):
                prepare_external_module(module, layout, 'aws-ecr', 'ohio-802', require_existing=True)
            legacy = module / 'terraform.tfstate'
            legacy.write_text(json.dumps({'lineage': 'x', 'serial': 0, 'resources': []}))
            with self.assertRaisesRegex(ValueError, 'legacy state still exists'):
                prepare_external_module(module, layout, 'aws-ecr', 'ohio-802')
            legacy.unlink()
            args = prepare_external_module(module, layout, 'aws-prep', 'ohio-802')
            self.assertIn('-reconfigure', args)
            self.assertEqual(layout.root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(layout.module_root('aws-prep').stat().st_mode & 0o777, 0o700)

    def test_worktree_inventory_deduplicates_aliases_but_rejects_distinct_snapshots(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / 'one' / 'terraform' / 'aws-ecr'
            second = root / 'two' / 'terraform' / 'aws-ecr'
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            state = first / 'terraform.tfstate.d/ohio-802/terraform.tfstate'
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({'lineage': 'x', 'serial': 2, 'resources': []}))
            (second / 'terraform.tfstate.d').symlink_to(first / 'terraform.tfstate.d', target_is_directory=True)
            found = discover_worktree_states([root / 'one', root / 'two'], 'aws-ecr')
            self.assertEqual(found['ohio-802'], state.resolve())
            (second / 'terraform.tfstate.d').unlink()
            duplicate = second / 'terraform.tfstate.d/ohio-802/terraform.tfstate'
            duplicate.parent.mkdir(parents=True)
            duplicate.write_bytes(state.read_bytes())
            with self.assertRaisesRegex(ValueError, 'multiple legacy state files'):
                discover_worktree_states([root / 'one', root / 'two'], 'aws-ecr')

    def test_migration_detects_changed_resource_with_same_lineage_and_count(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / 'old'
            module.mkdir()
            state = {'lineage': 'x', 'serial': 2, 'resources': [
                {'mode': 'managed', 'instances': [{'attributes': {'id': 'resource-a'}}]}]}
            (module / 'terraform.tfstate').write_text(json.dumps(state))
            layout = StateLayout((root / 'new').resolve())
            expected = check_migration_source(module, layout, 'aws-ecr')
            target = layout.state_path('aws-ecr', 'default')
            target.parent.mkdir(parents=True)
            state['resources'][0]['instances'][0]['attributes']['id'] = 'resource-b'
            target.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                verify_migrated_states(layout, 'aws-ecr', expected)

    def test_pre_migration_backup_is_private_and_leaves_sources_intact(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / 'module'
            module.mkdir()
            snapshot = module / 'terraform.tfstate'
            snapshot.write_text(json.dumps({'lineage': 'x', 'serial': 2, 'resources': []}))
            backup = root / 'backup'
            self.assertEqual(backup_legacy_states(module, backup)['default'][:3], ('x', 2, 0))
            self.assertTrue(snapshot.exists())
            copy = backup / 'default' / 'terraform.tfstate'
            self.assertEqual(copy.read_bytes(), snapshot.read_bytes())
            self.assertEqual(copy.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
            with self.assertRaisesRegex(ValueError, 'new empty'):
                backup_legacy_states(module, backup)

    def test_plan_requires_one_real_owner_for_all_module_workspaces(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trees = [root / 'one', root / 'two']
            one = trees[0] / 'terraform/aws-ecr'
            two = trees[1] / 'terraform/aws-ecr'
            one.mkdir(parents=True)
            two.mkdir(parents=True)
            doc = json.dumps({'lineage': 'x', 'serial': 2, 'resources': []})
            (one / 'terraform.tfstate').write_text(doc)
            named = one / 'terraform.tfstate.d/ohio-802/terraform.tfstate'
            named.parent.mkdir(parents=True)
            named.write_text(doc)
            layout = StateLayout((root / 'state').resolve())
            plan = build_migration_plan(trees, layout)
            self.assertEqual(plan['aws-ecr']['module_root'], one.resolve())
            self.assertEqual(set(plan['aws-ecr']['workspaces']), {'default', 'ohio-802'})
            other = two / 'terraform.tfstate.d/other/terraform.tfstate'
            other.parent.mkdir(parents=True)
            other.write_text(doc)
            with self.assertRaisesRegex(ValueError, 'different owning checkouts'):
                build_migration_plan(trees, layout)

    def test_multi_module_migration_writes_private_backups_and_removes_journal(self):
        import shutil
        import subprocess
        import tempfile
        if not shutil.which('terraform'):
            self.skipTest('terraform is unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            tree = root / 'repo'
            for name in ('aws-ecr', 'aws-prep'):
                module = tree / 'terraform' / name
                module.mkdir(parents=True)
                (module / 'main.tf').write_text('terraform {\n backend "local" {}\n}\noutput "synthetic" { value = "example" }\n')
                for args in (['init', '-input=false'], ['apply', '-input=false', '-auto-approve']):
                    subprocess.run(['terraform', '-chdir=' + str(module), *args], check=True, capture_output=True)
            layout = StateLayout(root / 'state')
            plan = build_migration_plan([tree], layout)
            backup = root / 'backup'
            migrate_plan(plan, layout, backup)
            self.assertFalse((layout.root / '.migration-in-progress.json').exists())
            for name in ('aws-ecr', 'aws-prep'):
                self.assertTrue(layout.state_path(name, 'default').is_file())
                self.assertTrue((backup / 'preflight' / name / 'default/terraform.tfstate').is_file())
                self.assertFalse((tree / 'terraform' / name / 'terraform.tfstate').exists())

    def test_interrupted_migration_retains_journal_and_source(self):
        import json
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            tree = root / 'repo'
            module = tree / 'terraform/aws-ecr'
            module.mkdir(parents=True)
            snapshot = module / 'terraform.tfstate'
            snapshot.write_text(json.dumps({'lineage': 'x', 'serial': 2, 'resources': []}))
            layout = StateLayout(root / 'state')
            plan = build_migration_plan([tree], layout)
            with patch('scripts.state_storage.migrate_one_module', side_effect=RuntimeError('synthetic interruption')):
                with self.assertRaisesRegex(RuntimeError, 'interruption'):
                    migrate_plan(plan, layout, root / 'backup')
            self.assertTrue(snapshot.exists())
            self.assertTrue((layout.root / '.migration-in-progress.json').is_file())
            with self.assertRaisesRegex(ValueError, 'earlier state migration'):
                migrate_plan(plan, layout, root / 'other-backup')

    def test_storage_activation_migrates_then_remembers_both_roots(self):
        import shutil
        import subprocess
        import tempfile
        if not shutil.which('terraform'):
            self.skipTest('terraform is unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            tree = root / 'repo'
            module = tree / 'terraform/aws-ecr'
            module.mkdir(parents=True)
            (module / 'main.tf').write_text('terraform {\n backend "local" {}\n}\noutput "synthetic" { value = "example" }\n')
            for args in (['init', '-input=false'], ['apply', '-input=false', '-auto-approve']):
                subprocess.run(['terraform', '-chdir=' + str(module), *args], check=True, capture_output=True)
            settings = StorageSettings(root / '.secrets', StateLayout(root / '.state'))
            profile = root / 'storage-settings.json'
            activate_storage_settings(settings, profile, [tree], root / 'private-backup')
            self.assertEqual(read_storage_settings(profile), settings)
            self.assertTrue(settings.state.state_path('aws-ecr', 'default').exists())
            self.assertFalse((module / 'terraform.tfstate').exists())
            activate_storage_settings(settings, profile, [tree], root / 'unused-backup')
            self.assertFalse((root / 'unused-backup').exists())

    def test_backend_config_includes_default_and_workspace_locations(self):
        args = self.layout.backend_args('aws-prep')
        self.assertEqual(len(args), 2)
        self.assertTrue(args[0].startswith('-backend-config=path='))
        self.assertTrue(args[1].startswith('-backend-config=workspace_dir='))


if __name__ == '__main__':
    unittest.main()
