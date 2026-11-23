"""Exercise the external-state quickstart path with local synthetic modules."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scripts.state_storage import StateLayout, StorageSettings, activate_storage_settings, configure_terraform_proxy
import automated_quickstart as quickstart

BACKEND = 'terraform {\n backend "local" {}\n}\n'
MODULES = {
    'aws-ecr': BACKEND + 'output "registry" { value = "fixture-registry" }\n',
    'aws-prep': BACKEND + '''variable "aws_ecr_state_path" { type = string }
data "terraform_remote_state" "ecr" {
  backend = "local"
  config = { path = var.aws_ecr_state_path }
}
output "from_ecr" { value = data.terraform_remote_state.ecr.outputs.registry }
''',
    'aws-ec2-k3s': BACKEND + '''variable "aws_prep_state_path" { type = string }
variable "lab_generated_secrets_enabled" { type = bool }
variable "lab_secrets_root" { type = string }
data "terraform_remote_state" "prep" {
  backend = "local"
  config = { path = var.aws_prep_state_path }
}
output "from_prep" { value = data.terraform_remote_state.prep.outputs.from_ecr }
''',
}


class ExternalStateIntegrationTests(unittest.TestCase):
    def test_quickstart_terraform_path_uses_external_dependencies(self):
        binary = shutil.which('terraform')
        if not binary:
            self.skipTest('terraform is unavailable')
        with tempfile.TemporaryDirectory(prefix='faig-integration-') as directory:
            root = Path(directory).resolve()
            old, new = root / 'old', root / 'new'
            for tree in (old, new):
                for name, content in MODULES.items():
                    module = tree / 'terraform' / name
                    module.mkdir(parents=True)
                    (module / 'main.tf').write_text(content)
            for name in MODULES:
                module = old / 'terraform' / name
                subprocess.run([binary, '-chdir=' + str(module), 'init', '-input=false'],
                               check=True, capture_output=True)
                args = ['apply', '-input=false', '-auto-approve']
                if name == 'aws-prep':
                    args.append('-var=aws_ecr_state_path=' + str(old / 'terraform/aws-ecr/terraform.tfstate'))
                elif name == 'aws-ec2-k3s':
                    args += ['-var=aws_prep_state_path=' + str(old / 'terraform/aws-prep/terraform.tfstate'),
                             '-var=lab_generated_secrets_enabled=false', '-var=lab_secrets_root=' + str(root / 'secrets')]
                subprocess.run([binary, '-chdir=' + str(module), *args], check=True, capture_output=True)
            scripts = new / 'scripts'
            (scripts / 'bin').mkdir(parents=True)
            for name in ('terraform_proxy.py', 'state_storage.py'):
                shutil.copy2(ROOT / 'scripts' / name, scripts / name)
            shutil.copy2(ROOT / 'scripts/bin/terraform', scripts / 'bin/terraform')
            profile = root / 'settings.json'
            settings = StorageSettings(root / 'secrets', StateLayout(root / 'state'))
            activate_storage_settings(settings, profile, [old, new], root / 'backup')
            with mock.patch.dict(os.environ, {'TF_WORKSPACE': 'default'}, clear=False):
                configure_terraform_proxy(new, profile)
                original = quickstart.run_command
                def run(argv, **kwargs):
                    kwargs['cwd'] = new
                    return original(argv, **kwargs)
                modules = [('ecr', 'terraform/aws-ecr'), ('prep', 'terraform/aws-prep'),
                           ('host', 'terraform/aws-ec2-k3s')]
                with mock.patch.object(quickstart, 'REPO_ROOT', new), \
                     mock.patch.object(quickstart, 'run_command', side_effect=run), \
                     mock.patch.object(quickstart, 'restore_existing_ecr_vars'), \
                     mock.patch.object(quickstart, 'TERRAFORM_MODULES', modules):
                    quickstart.run_terraform(True, [], 'profile', 'region',
                                             state_layout=settings.state, secrets_root=settings.secrets_root)
                result = subprocess.run([str(scripts / 'bin/terraform'),
                                         '-chdir=' + str(new / 'terraform/aws-ec2-k3s'),
                                         'output', '-raw', 'from_prep'],
                                        cwd=new, env=os.environ.copy(), capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout, 'fixture-registry')
