from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automated_quickstart as quickstart


class Quickstart802Tests(unittest.TestCase):
    def setUp(self):
        try:
            original_cwd = Path.cwd()
        except FileNotFoundError:
            original_cwd = Path(__file__).resolve().parents[1]
            os.chdir(original_cwd)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(os.chdir, original_cwd)
        self.root = Path(self.temp.name)
        self.user = self.root / "ansible/group_vars/user.yml"
        self.user.parent.mkdir(parents=True)
        self.user.write_text("---\nprivate_value: secret-do-not-print\n")
        self.root_patch = mock.patch.object(quickstart, "REPO_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_explicit_override_does_not_change_saved_choice(self):
        self.user.write_text("quickstart_experimental_faig_init: true\n")
        self.assertFalse(quickstart.select_experimental_init(False, noninteractive=True))
        self.assertIn("true", self.user.read_text())
        self.assertTrue(quickstart.select_experimental_init(None, noninteractive=True))

    def test_interactive_choice_is_saved_and_reused(self):
        with mock.patch.object(quickstart, "prompt_yes_no", return_value=True):
            self.assertTrue(quickstart.select_experimental_init(None, noninteractive=False))
        with mock.patch.object(quickstart, "prompt_yes_no", side_effect=AssertionError("prompted")):
            self.assertTrue(quickstart.select_experimental_init(None, noninteractive=True))
        self.assertIn("private_value: secret-do-not-print", self.user.read_text())

    def test_default_enabled_and_invalid_choice_fails_without_leaking_values(self):
        self.assertTrue(quickstart.select_experimental_init(None, noninteractive=True))
        for value in ("maybe",):
            if value:
                self.user.write_text(f"private_value: secret-do-not-print\nquickstart_experimental_faig_init: {value}\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as error:
                quickstart.select_experimental_init(None, noninteractive=True)
            self.assertNotIn("secret-do-not-print", output.getvalue() + str(error.exception))

    def test_yolo_requires_aws_values_without_printing_content(self):
        with self.assertRaises(SystemExit) as error:
            quickstart.validate_yolo_aws_profile('aws_profile = "secret-do-not-print"\n')
        self.assertIn("aws_region", str(error.exception))
        self.assertNotIn("secret-do-not-print", str(error.exception))
        quickstart.validate_yolo_aws_profile('\n'.join(f'{key} = "value"' for key in
            ("aws_profile", "aws_region", "ssh_key_name", "ssh_private_key_file")))

    def test_failed_login_does_not_prompt_in_yolo(self):
        with mock.patch.object(quickstart, "run_command", return_value=mock.Mock(returncode=1)), \
             mock.patch.object(quickstart, "choose_aws_login_method", side_effect=AssertionError("prompted")):
            with self.assertRaisesRegex(SystemExit, "refresh the SSO session"):
                quickstart.ensure_aws_login("test", noninteractive=True)

    def test_initialization_preflight_reuses_private_files_and_license(self):
        import json, os
        env = self.root / 'private'; env.mkdir(mode=0o700)
        licenses = self.root / 'licenses'; licenses.mkdir()
        (licenses / 'FAIG123.lic').write_text('license')
        setup = {'email':'admin@fortiai.lab','username':'Admin','password':'secret','organization_name':'Lab'}
        (env / 'admin-setup.json').write_text(json.dumps(setup)); (env / 'admin-setup.json').chmod(0o600)
        (env / 'admin-login.json').write_text(json.dumps({'username':setup['email'],'password':setup['password']})); (env / 'admin-login.json').chmod(0o600)
        self.user.write_text(f"license_source_dir: '{licenses}'\nquickstart_faig_license_regex: 'FAIG[0-9]+\\.lic'\n")
        with mock.patch.dict(os.environ, {'FAIG_ENV_DIR':str(env)}, clear=False), \
             mock.patch.object(quickstart, 'run_command', side_effect=AssertionError('overwrote credentials')):
            result = quickstart.prepare_802_initialization()
        self.assertEqual(result['environment'], env.resolve())
        self.assertEqual(result['license_dir'], licenses)

    def test_initialization_preflight_rejects_incomplete_private_files(self):
        import os
        env = self.root / 'private'; env.mkdir(mode=0o700)
        licenses = self.root / 'licenses'; licenses.mkdir(); (licenses / 'FAIG.lic').write_text('license')
        (env / 'admin-login.json').write_text('{}'); (env / 'admin-login.json').chmod(0o600)
        self.user.write_text(f"license_source_dir: '{licenses}'\n")
        with mock.patch.dict(os.environ, {'FAIG_ENV_DIR':str(env)}, clear=False):
            with self.assertRaisesRegex(SystemExit, 'files are incomplete'):
                quickstart.prepare_802_initialization()

    def test_appliances_need_explicit_local_opt_in(self):
        path = self.root / 'terraform/aws-fortigate/99-local.auto.tfvars'
        path.parent.mkdir(parents=True)
        self.assertFalse(quickstart.appliance_enabled_from_tfvars('fortigate'))
        path.write_text('fortigate_enabled = true\n')
        self.assertTrue(quickstart.appliance_enabled_from_tfvars('fortigate'))
        path.write_text('fortigate_enabled = false\n')
        self.assertFalse(quickstart.appliance_enabled_from_tfvars('fortigate'))

    def test_override_preflight_requires_workspace_and_both_files(self):
        import os
        directory = self.root / 'overrides'; directory.mkdir()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'TF_WORKSPACE'):
                quickstart.validate_terraform_vars_dir(directory)
        with mock.patch.dict(os.environ, {'TF_WORKSPACE':'ohio-802'}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'prep.tfvars'):
                quickstart.validate_terraform_vars_dir(directory)
            (directory / 'prep.tfvars').write_text('')
            with self.assertRaisesRegex(SystemExit, 'host.tfvars'):
                quickstart.validate_terraform_vars_dir(directory)
            (directory / 'host.tfvars').write_text('')
            self.assertEqual(quickstart.validate_terraform_vars_dir(directory), directory.resolve())

    def test_override_preflight_rejects_region_mismatch(self):
        directory = self.root / 'overrides'; directory.mkdir()
        (directory / 'prep.tfvars').write_text('aws_region = "us-east-1"\n')
        (directory / 'host.tfvars').write_text('aws_region = "us-east-2"\n')
        with self.assertRaisesRegex(SystemExit, 'disagree on aws_region'):
            quickstart.effective_terraform_user_settings('aws_profile = "test"\n', directory)

    def test_terraform_preserves_ecr_by_default(self):
        with mock.patch.object(quickstart, 'run_ecr_terraform') as ecr, \
             mock.patch.object(quickstart, 'restore_existing_ecr_vars') as restore, \
             mock.patch.object(quickstart, 'terraform_init_validate'), \
             mock.patch.object(quickstart, 'terraform_apply') as apply:
            quickstart.run_terraform(True, [], 'profile', 'region')
            ecr.assert_not_called()
            restore.assert_called_once_with('profile', 'region')
            self.assertTrue(apply.called)
            self.assertFalse(any(call.args[0] == 'terraform/aws-ecr' for call in apply.call_args_list))

    def test_generated_secret_settings_are_private_and_reused(self):
        module = self.root / 'host'
        module.mkdir()
        quickstart.persist_generated_secret_settings(module, self.root / 'secrets')
        path = module / '99-local.auto.tfvars'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn('lab_generated_secrets_enabled = true', path.read_text())
        quickstart.persist_generated_secret_settings(module, self.root / 'secrets')
        with self.assertRaisesRegex(ValueError, 'differ'):
            quickstart.persist_generated_secret_settings(module, self.root / 'other')

    def test_generated_secret_settings_reject_symlink(self):
        module = self.root / 'host'
        module.mkdir()
        (module / '99-local.auto.tfvars').symlink_to(self.root / 'target')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            quickstart.persist_generated_secret_settings(module, self.root / 'secrets')

    def test_generated_secret_settings_preserve_user_values(self):
        module = self.root / 'host'
        module.mkdir()
        path = module / '99-local.auto.tfvars'
        path.write_text('instance_type = "g6.4xlarge"\n')
        quickstart.persist_generated_secret_settings(module, self.root / 'secrets')
        self.assertTrue(path.read_text().startswith('instance_type = "g6.4xlarge"\n'))
        before = path.read_text()
        with self.assertRaisesRegex(ValueError, 'differs'):
            quickstart.persist_generated_secret_settings(module, self.root / 'other')
        self.assertEqual(path.read_text(), before)

    def test_host_override_rejects_generated_secret_settings(self):
        directory = self.root / 'overrides'
        directory.mkdir()
        (directory / 'prep.tfvars').write_text('')
        (directory / 'host.tfvars').write_text('lab_generated_secrets_enabled = false\n')
        with mock.patch.dict(os.environ, {'TF_WORKSPACE': 'ohio-802'}):
            with self.assertRaisesRegex(SystemExit, 'must not override'):
                quickstart.validate_terraform_vars_dir(directory)

    def test_bare_terraform_plan_keeps_generated_secret_settings(self):
        import shutil
        import subprocess
        if not shutil.which('terraform'):
            self.skipTest('terraform is unavailable')
        module = self.root / 'host'
        module.mkdir()
        (module / 'main.tf').write_text('''
variable "lab_generated_secrets_enabled" {\n type = bool\n default = false\n}
variable "lab_secrets_root" {\n type = string\n default = ""\n}
resource "terraform_data" "fixture" {
  count = var.lab_generated_secrets_enabled ? 1 : 0
  input = var.lab_secrets_root
}
''')
        quickstart.persist_generated_secret_settings(module, self.root / 'secrets')
        for command in (['init', '-input=false'], ['apply', '-input=false', '-auto-approve']):
            subprocess.run(['terraform', '-chdir=' + str(module), *command], check=True, capture_output=True)
        result = subprocess.run(['terraform', '-chdir=' + str(module), 'plan', '-input=false', '-detailed-exitcode'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_quickstart_does_not_offer_ecr_mutation_flags(self):
        import sys
        with mock.patch.object(sys, 'argv', ['quickstart', '--manage-ecr']), \
             mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit) as exc:
                quickstart.parse_args()
        self.assertEqual(exc.exception.code, 2)

    def test_terraform_workspace_overrides_passed_to_prep_and_host(self):
        directory = self.root / 'ohio'
        with mock.patch.object(quickstart, 'restore_existing_ecr_vars'), \
             mock.patch.object(quickstart, 'terraform_init_validate'), \
             mock.patch.object(quickstart, 'terraform_apply') as apply:
            quickstart.run_terraform(True, [], 'profile', 'region', terraform_vars_dir=directory)
        calls = {call.args[0]: call.kwargs.get('var_file') for call in apply.call_args_list}
        self.assertEqual(calls['terraform/aws-prep'], directory / 'prep.tfvars')
        self.assertEqual(calls['terraform/aws-ec2-k3s'], directory / 'host.tfvars')

    def test_existing_ecr_vars_come_from_matching_workspace(self):
        import json
        data = {'registry': {'value': '123456789012.dkr.ecr.us-east-2.amazonaws.com'},
                'account_id': {'value': '123456789012'},
                'repository_arns': {'value': {'api': 'arn:aws:ecr:us-east-2:123456789012:repository/fortiaigate/api'}},
                'repository_urls': {'value': {'api': '123456789012.dkr.ecr.us-east-2.amazonaws.com/fortiaigate/api'}}}
        with mock.patch.object(quickstart, 'REPO_ROOT', self.root), \
             mock.patch.object(quickstart, 'parse_ecr_tfvars', return_value=('fortiaigate', ['api'])), \
             mock.patch.object(quickstart, 'command_output', side_effect=[json.dumps(data), '123456789012', json.dumps(data), '123456789012']):
            quickstart.restore_existing_ecr_vars('test', 'us-east-2')
            output = json.loads((self.root / 'ansible/group_vars/ecr.generated.yml').read_text())
            self.assertEqual(output['fortiaigate_image_repository'], data['registry']['value'] + '/fortiaigate')
            with self.assertRaisesRegex(SystemExit, 'matching existing ECR'):
                quickstart.restore_existing_ecr_vars('test', 'us-east-1')

    def test_existing_ecr_vars_reject_other_aws_account(self):
        import json
        data = {'registry': {'value': '123456789012.dkr.ecr.us-east-2.amazonaws.com'},
                'account_id': {'value': '123456789012'},
                'repository_arns': {'value': {'api': 'arn:aws:ecr:us-east-2:123456789012:repository/fortiaigate/api'}},
                'repository_urls': {'value': {'api': '123456789012.dkr.ecr.us-east-2.amazonaws.com/fortiaigate/api'}}}
        with mock.patch.object(quickstart, 'REPO_ROOT', self.root), \
             mock.patch.object(quickstart, 'parse_ecr_tfvars', return_value=('fortiaigate', ['api'])), \
             mock.patch.object(quickstart, 'command_output', side_effect=[json.dumps(data), '999999999999']):
            with self.assertRaisesRegex(SystemExit, 'matching existing ECR'):
                quickstart.restore_existing_ecr_vars('test', 'us-east-2')
            self.assertFalse((self.root / 'ansible/group_vars/ecr.generated.yml').exists())

    def test_existing_ecr_vars_reject_incomplete_or_wrong_arns(self):
        data = {'registry': {'value': '123456789012.dkr.ecr.us-east-2.amazonaws.com'},
                'account_id': {'value': '123456789012'},
                'repository_urls': {'value': {'api': '123456789012.dkr.ecr.us-east-2.amazonaws.com/fortiaigate/api'}},
                'repository_arns': {'value': {'api': 'arn:aws:ecr:us-east-1:123456789012:repository/fortiaigate/api'}}}
        with mock.patch.object(quickstart, 'REPO_ROOT', self.root), \
             mock.patch.object(quickstart, 'parse_ecr_tfvars') as config, \
             mock.patch.object(quickstart, 'command_output') as command:
            for expected in (['api'], ['api', 'core']):
                config.return_value = ('fortiaigate', expected)
                command.side_effect = [json.dumps(data), '123456789012']
                with self.assertRaisesRegex(SystemExit, 'matching existing ECR'):
                    quickstart.restore_existing_ecr_vars('test', 'us-east-2')
            data['repository_arns']['value']['api'] = 'arn:aws:ecr:us-east-2:123456789012:repository/fortiaigate/api'
            config.return_value = ('fortiaigate', ['api', 'core'])
            command.side_effect = [json.dumps(data), '123456789012']
            with self.assertRaisesRegex(SystemExit, 'matching existing ECR'):
                quickstart.restore_existing_ecr_vars('test', 'us-east-2')

    def test_802_service_order_and_manual_setup(self):
        args = Namespace(faig_status_retries=1, faig_status_delay=1)
        from scripts import faig_bootstrap_802
        fake_client = mock.Mock()
        fake_client.call.return_value = {'needs_setup': True}
        with mock.patch.object(quickstart, 'run_ansible_playbook') as run, \
             mock.patch.object(quickstart, 'get_layered_yaml_scalar', return_value='192.0.2.1'), \
             mock.patch.object(faig_bootstrap_802, 'Client', return_value=fake_client):
            quickstart.run_802_ansible_flow(args, None)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            'bootstrap_gpu_k3s.yml', 'deploy_fortiaigate.yml', 'deploy_litellm.yml', 'deploy_mcp.yml',
            'deploy_lab_management.yml', 'deploy_demo_https_gateway.yml', 'deploy_lab_management.yml',
            'deploy_lab_chatbot.yml'])

    def test_802_initialization_runs_after_litellm_and_before_ui(self):
        from scripts import faig_bootstrap_802
        import catalog802.loader
        args = Namespace(faig_status_retries=1, faig_status_delay=1)
        private = {'environment': self.root, 'setup': self.root / 'setup', 'litellm_key': self.root / 'key',
                   'license_dir': self.root, 'license_regex': 'x', 'journal': self.root / 'journal', 'smoke_key': self.root / 'smoke'}
        sequence = []
        setup = {'email':'admin@fortiai.lab'}
        fake_client = mock.Mock()
        fake_client.call.return_value = {'needs_setup': True}
        with mock.patch.object(quickstart, 'run_ansible_playbook', side_effect=lambda name, **kwargs: sequence.append(name)), \
             mock.patch.object(quickstart, 'get_layered_yaml_scalar', return_value='192.0.2.1'), \
             mock.patch.object(quickstart, 'get_layered_yaml_bool', return_value=True), \
             mock.patch.object(quickstart, 'get_ec2_instance_id', return_value='i-123abc'), \
             mock.patch.object(faig_bootstrap_802, 'Client', return_value=fake_client), \
             mock.patch.object(faig_bootstrap_802, 'private_json', side_effect=[setup, {'api_key':'private'}]), \
             mock.patch.object(catalog802.loader, 'load', return_value=({'models': {'pass-model':{}}}, [])), \
             mock.patch.object(faig_bootstrap_802, 'initialize', side_effect=lambda *a, **k: (sequence.append('initialize') or {'license_active':True, 'scanning_enabled':True, 'provider_verified':True, 'governed_verified':True})):
            quickstart.run_802_ansible_flow(args, private)
        self.assertLess(sequence.index('deploy_litellm.yml'), sequence.index('initialize'))
        self.assertLess(sequence.index('initialize'), sequence.index('deploy_lab_management.yml'))
        self.assertEqual(private['journal'].name, 'faig-init-i-123abc.json')
        self.assertEqual(private['smoke_key'].name, 'quickstart-smoke-key-i-123abc.json')
        self.assertLess(sequence.index('deploy_demo_https_gateway.yml'), sequence.index('deploy_lab_chatbot.yml'))

    def test_external_state_paths_override_user_var_file(self):
        with mock.patch.object(quickstart, 'run_command') as run:
            quickstart.terraform_apply('terraform/aws-prep', True,
                ['aws_ecr_state_path=/private/state/ecr'], var_file=self.root / 'prep.tfvars')
        args = run.call_args.args[0]
        self.assertLess(args.index('-var-file=' + str(self.root / 'prep.tfvars')), args.index('-var'))
        self.assertIn('aws_ecr_state_path=/private/state/ecr', args)

    def test_storage_preferences_coordinate_paths_without_writing_before_migration(self):
        profile = self.root / 'storage.json'
        workspace = (self.root / 'workspace').resolve()
        workspace.mkdir()
        with mock.patch.object(quickstart, 'REPO_ROOT', workspace / 'repo'), \
             mock.patch.object(quickstart, 'prompt_yes_no', return_value=True), \
             mock.patch.object(quickstart, 'prompt_text', side_effect=['default', str(workspace / '.state'), str(workspace / '.secrets')]):
            selected = quickstart.select_storage_settings(profile_path=profile, noninteractive=False, workspace_root=workspace)
        self.assertEqual(selected.state.root, workspace / '.state')
        self.assertEqual(selected.secrets_root, workspace / '.secrets')
        self.assertFalse(profile.exists())
        default = quickstart.select_storage_settings(profile_path=profile, noninteractive=True, workspace_root=workspace)
        self.assertIsNone(default.state)
        self.assertEqual(default.secrets_root, workspace / '.secrets')

    def test_yolo_reads_saved_workspace_and_overrides_without_environment(self):
        from scripts.state_storage import StateLayout, StorageSettings, write_storage_settings
        workspace = (self.root / 'workspace').resolve()
        workspace.mkdir()
        overrides = workspace / 'ohio-vars'
        overrides.mkdir()
        profile = workspace / 'storage.json'
        expected = StorageSettings(workspace / '.secrets', StateLayout(workspace / '.state'), 'ohio-802', overrides)
        write_storage_settings(profile, expected)
        with mock.patch.object(quickstart, 'REPO_ROOT', workspace / 'repo'), mock.patch.dict(os.environ, {}, clear=True):
            actual = quickstart.select_storage_settings(profile_path=profile, noninteractive=True, workspace_root=workspace)
        self.assertEqual(actual, expected)
        with mock.patch.object(quickstart, 'REPO_ROOT', workspace / 'repo'), mock.patch.dict(os.environ, {'TF_WORKSPACE':'other'}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'conflicts'):
                quickstart.select_storage_settings(profile_path=profile, noninteractive=True, workspace_root=workspace)

    def test_generated_bootstrap_activation_checks_terraform_identity(self):
        import json
        import os
        from unittest.mock import patch
        root = self.root / 'private'
        directory = root / 'ohio-802' / 'i-123abc'
        directory.mkdir(parents=True, mode=0o700)
        bootstrap = directory / 'bootstrap-secrets.json'
        bootstrap.write_text(json.dumps({'workspace': 'ohio-802', 'instance_id': 'i-123abc',
             'faig_admin': {'password': 'Fictional_123', 'static_password_file': None},
             'litellm': {'master_key': 'fictional', 'ui_password': 'fictional', 'postgres_password': 'fictional'}}))
        bootstrap.chmod(0o600)
        with patch.dict(os.environ, {'TF_WORKSPACE': 'ohio-802'}, clear=True), \
             patch.object(quickstart, 'get_ec2_instance_id', return_value='i-123abc'), \
             patch.object(quickstart, 'command_output', side_effect=lambda argv, **_kw: '123456789012' if argv[0] == 'aws' else str(directory)), \
             patch.object(quickstart, 'get_layered_yaml_scalar', return_value='admin@example.test'):
            result = quickstart.activate_802_generated_bootstrap(secrets_root=root, license_dir=self.root, license_regex='x', profile='lab', region='us-east-2')
            self.assertEqual(result['instance_id'], 'i-123abc')
            self.assertTrue((directory / '.lab-instance').exists())
            self.assertEqual(os.environ['FAIG_ENV_DIR'], str(directory))
            os.environ['FAIG_ENV_DIR'] = str(self.root / 'old-instance')
            with self.assertRaisesRegex(SystemExit, 'conflicts'):
                quickstart.activate_802_generated_bootstrap(secrets_root=root, license_dir=self.root, license_regex='x', profile='lab', region='us-east-2')

    def test_802_generated_bootstrap_uses_one_canonical_file(self):
        from scripts import faig_bootstrap_802
        import catalog802.loader
        args = Namespace(faig_status_retries=1, faig_status_delay=1)
        setup = {'email': 'admin@example.test', 'password': 'fictional'}
        private = {'environment': self.root, 'instance_id': 'i-123abc', 'bootstrap_file': self.root / 'bootstrap.json',
                   'setup_data': setup, 'litellm_key': self.root / 'shared-key.json',
                   'license_dir': self.root, 'license_regex': 'x', 'journal': self.root / 'faig-init.json',
                   'smoke_key': self.root / 'quickstart-smoke-key.json'}
        fake_client = mock.Mock()
        fake_client.call.return_value = {'needs_setup': True}
        with mock.patch.object(quickstart, 'run_ansible_playbook') as play, \
             mock.patch.object(quickstart, 'get_layered_yaml_scalar', return_value='192.0.2.1'), \
             mock.patch.object(quickstart, 'get_layered_yaml_bool', return_value=True), \
             mock.patch.object(quickstart, 'get_ec2_instance_id', return_value='i-123abc'), \
             mock.patch.object(faig_bootstrap_802, 'Client', return_value=fake_client), \
             mock.patch.object(faig_bootstrap_802, 'private_json', return_value={'api_key': 'synthetic'}), \
             mock.patch.object(catalog802.loader, 'load', return_value=({'models': {'pass-model': {}}}, [])), \
             mock.patch.object(faig_bootstrap_802, 'initialize', return_value={'license_active': True, 'scanning_enabled': True, 'provider_verified': True, 'governed_verified': True}) as init:
            quickstart.run_802_ansible_flow(args, private)
        self.assertEqual(init.call_args.args[1], setup)
        self.assertEqual(private['journal'].name, 'faig-init.json')
        self.assertEqual(play.call_args_list[0].kwargs['extra_vars']['lab_bootstrap_secrets_file'], str(private['bootstrap_file']))
        self.assertNotIn('fictional', repr(play.call_args_list))

    def test_yolo_orchestrates_generated_instance_credentials(self):
        import contextlib
        import os
        import sys
        from scripts import state_storage
        from types import SimpleNamespace
        (self.root / 'terraform').mkdir(exist_ok=True)
        (self.root / 'terraform/user.tfvars').write_text('aws_profile = "lab"\naws_region = "us-east-2"\nssh_key_name = "fixture"\n')
        playbooks = self.root / 'ansible/playbooks'
        playbooks.mkdir(parents=True, exist_ok=True)
        for name in ('deploy_lab_management.yml', 'deploy_lab_chatbot.yml', 'deploy_demo_https_gateway.yml'):
            (playbooks / name).write_text('---\n')
        secrets_root = (self.root.parent / 'fixture-secrets').resolve()
        settings = state_storage.StorageSettings(secrets_root, None, 'ohio-802')
        runtime = {'instance_id': 'i-123', 'bootstrap_file': self.root / 'bootstrap.json'}
        old_cwd = os.getcwd()
        with contextlib.ExitStack() as stack:
            self.addCleanup(os.chdir, old_cwd)
            stack.enter_context(mock.patch.dict(os.environ, {'TF_WORKSPACE':'ohio-802', 'FAIG_WORKSPACE_ROOT':str(self.root.parent)}, clear=True))
            stack.enter_context(mock.patch.object(sys, 'argv', ['automated_quickstart.py', '--yolo']))
            for name in ('check_repo_root', 'check_requirements', 'validate_yolo_aws_profile', 'preflight_static_password_files',
                         'ensure_aws_login', 'configure_ansible_env', 'configure_disabled_appliance_tfvars',
                         'ensure_appliance_prep_tfvars', 'ensure_appliance_collections', 'configure_appliance_license_preflight',
                         'prompt_ec2_status', 'show_appliance_ec2_statuses'):
                stack.enter_context(mock.patch.object(quickstart, name))
            stack.enter_context(mock.patch.object(quickstart, 'ensure_user_profile', return_value='existing'))
            stack.enter_context(mock.patch.object(quickstart, 'preflight_802_license', return_value=(self.root, 'x')))
            stack.enter_context(mock.patch.object(quickstart, 'select_storage_settings', return_value=settings))
            stack.enter_context(mock.patch.object(quickstart, 'repo_worktrees', return_value=[]))
            stack.enter_context(mock.patch.object(state_storage, 'read_storage_settings', return_value=None))
            stack.enter_context(mock.patch.object(state_storage, 'activate_storage_settings'))
            stack.enter_context(mock.patch.object(quickstart.profile_tool, 'warn_legacy_files'))
            stack.enter_context(mock.patch.object(quickstart.profile_tool, 'ensure_ec2_instance_type'))
            stack.enter_context(mock.patch.object(quickstart, 'selected_appliance_keys', return_value=[]))
            stack.enter_context(mock.patch.object(quickstart, 'filter_existing_appliances_for_skipped_terraform', return_value=[]))
            stack.enter_context(mock.patch.object(quickstart, 'filter_noninteractive_default_appliances', return_value=[]))
            deploy = stack.enter_context(mock.patch.object(quickstart, 'run_terraform'))
            stack.enter_context(mock.patch.object(quickstart, 'activate_802_generated_bootstrap', return_value=runtime))
            ansible = stack.enter_context(mock.patch.object(quickstart, 'run_802_ansible_flow'))
            quickstart.main()
        self.assertEqual(deploy.call_args.kwargs['secrets_root'], secrets_root)
        self.assertEqual(ansible.call_args.args[1], runtime)
        self.assertEqual(ansible.call_args.kwargs['runtime'], runtime)

    def test_missing_management_integration_stops_before_deployment(self):
        (self.root / "terraform").mkdir()
        (self.root / "terraform/user.tfvars").write_text("")
        for choice in (True, False):
            args = Namespace(target="aws", auto_approve=False, yolo=True,
                             skip_ansible=False, experimental_faig_init=choice, terraform_vars_dir=None,
                             include_appliances=False, include_fortigate=False,
                             include_fortiweb=False, no_appliances=False,
                             no_fortigate=False, no_fortiweb=False)
            with mock.patch.object(quickstart, "parse_args", return_value=args), \
                 mock.patch.object(quickstart, "check_repo_root"), \
                 mock.patch.object(quickstart, "check_requirements"), \
                 mock.patch.object(quickstart, "ensure_user_profile", return_value="existing"), \
                 mock.patch.object(quickstart, "run_ansible_flow", side_effect=AssertionError("deployed")):
                with mock.patch.object(quickstart, "validate_yolo_aws_profile"), self.assertRaisesRegex(SystemExit, "Lab Management integration"):
                    quickstart.main()


if __name__ == "__main__":
    unittest.main()
