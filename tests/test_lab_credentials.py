import json
from pathlib import Path
import tempfile
import unittest

from scripts.lab_credentials import load_bootstrap, read_static_password, validate_instance_directory


class LabCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.path = self.root / 'bootstrap.json'
        self.doc = {'instance_id': 'i-123', 'workspace': 'ohio-802',
                    'faig_admin': {'password': 'Example_123', 'static_password_file': None},
                    'litellm': {'master_key': 'synthetic-master', 'ui_password': 'synthetic-ui',
                                'postgres_password': 'synthetic-database'}}
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.doc))
        self.path.chmod(0o600)

    def load(self, instance='i-123'):
        return load_bootstrap(self.path, instance=instance, workspace='ohio-802', repo_root=self.repo,
                              email='admin@example.test', display_name='Admin', organization='Lab')

    def test_single_source_derives_setup_and_login(self):
        setup, login, litellm = self.load()
        self.assertEqual(setup['password'], login['password'])
        self.assertEqual(login['username'], setup['email'])
        self.assertEqual(litellm['litellm_master_key'], 'synthetic-master')

    def test_wrong_instance_and_excess_permissions_fail(self):
        with self.assertRaisesRegex(ValueError, 'different instance'):
            self.load('i-other')
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            self.load()

    def test_static_password_file_is_private_and_outside_repo(self):
        password = self.root / 'static'
        password.write_text('Fictional_123\n')
        password.chmod(0o600)
        self.doc['faig_admin'] = {'password': None, 'static_password_file': str(password)}
        self.write()
        self.assertEqual(self.load()[1]['password'], 'Fictional_123')
        bad = self.repo / 'static'
        bad.write_text('Fictional_123')
        bad.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'outside'):
            read_static_password(bad, self.repo)
        password.write_text('weak')
        with self.assertRaisesRegex(ValueError, 'requirements'):
            self.load()

    def test_instance_directory_marker_and_boundary(self):
        directory = self.root / 'generated' / 'ohio-802' / 'i-123'
        directory.mkdir(parents=True, mode=0o700)
        result = validate_instance_directory(directory, root=self.root / 'generated', workspace='ohio-802', instance='i-123')
        self.assertEqual(result, directory)
        self.assertEqual((directory / '.lab-instance').stat().st_mode & 0o777, 0o600)
        self.assertEqual(validate_instance_directory(directory, root=self.root / 'generated', workspace='ohio-802', instance='i-123'), directory)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            validate_instance_directory(directory, root=self.root / 'generated', workspace='ohio-802', instance='i-456')
        (directory / '.lab-instance').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'marker does not match'):
            validate_instance_directory(directory, root=self.root / 'generated', workspace='ohio-802', instance='i-123')

    def test_symlink_and_dual_password_source_are_refused(self):
        actual = self.root / 'actual'
        self.path.rename(actual)
        self.path.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            self.load()
        self.path.unlink()
        actual.rename(self.path)
        self.doc['faig_admin']['static_password_file'] = str(actual)
        self.write()
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.load()
