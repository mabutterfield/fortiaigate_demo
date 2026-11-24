"""External-state launcher routes Terraform and leaves legacy guards in place."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.state_storage import (StateLayout, StorageSettings, activate_storage_settings,
                                   is_moved_sentinel, prime_backend_data)
from scripts.terraform_proxy import module_from_args

ROOT = Path(__file__).resolve().parents[1]


class TerraformProxyTests(unittest.TestCase):
    def test_rejects_unrelated_module(self):
        with self.assertRaisesRegex(ValueError, 'only supports'):
            module_from_args(['-chdir=/tmp/unrelated', 'apply'], ROOT, ROOT)

    def test_real_proxy_uses_external_backend_with_legacy_guard(self):
        binary = shutil.which('terraform')
        if not binary:
            self.skipTest('terraform is unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            old, new = root / 'old', root / 'new'
            code = 'terraform {\n backend "local" {}\n}\noutput "synthetic" { value = "example" }\n'
            for tree in (old, new):
                module = tree / 'terraform/aws-ecr'
                module.mkdir(parents=True)
                (module / 'main.tf').write_text(code)
            source = old / 'terraform/aws-ecr'
            for args in (['init', '-input=false'], ['apply', '-auto-approve', '-input=false']):
                subprocess.run([binary, '-chdir=' + str(source), *args], check=True, capture_output=True)
            scripts = new / 'scripts'
            (scripts / 'bin').mkdir(parents=True)
            for name in ('terraform_proxy.py', 'state_storage.py'):
                shutil.copy2(ROOT / 'scripts' / name, scripts / name)
            shutil.copy2(ROOT / 'scripts/bin/terraform', scripts / 'bin/terraform')
            settings = StorageSettings(root / '.secrets', StateLayout(root / '.state'))
            profile = root / 'settings.json'
            activate_storage_settings(settings, profile, [old, new], root / 'backup')
            prime_backend_data(settings.state, new, 'aws-ecr', binary)
            env = dict(os.environ, FAIG_STORAGE_PROFILE=str(profile), FAIG_REAL_TERRAFORM=binary,
                       TF_WORKSPACE='default')
            module = new / 'terraform/aws-ecr'
            proxy = scripts / 'bin/terraform'
            args = ['-chdir=' + str(module), 'init', '-input=false', *settings.state.backend_args('aws-ecr')]
            subprocess.run([str(proxy), *args], cwd=new, env=env, check=True, capture_output=True)
            result = subprocess.run([str(proxy), '-chdir=' + str(module), 'output', '-raw', 'synthetic'],
                                    cwd=new, env=env, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout, 'example')
            ansible = shutil.which('ansible-playbook')
            if ansible:
                try:
                    usable = subprocess.run([ansible, '--version'], capture_output=True, timeout=15).returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    usable = False
                if not usable:
                    self.skipTest('ansible-playbook cannot run; repair or reinstall Ansible')
                playbook = root / 'terraform-output.yml'
                playbook.write_text(f'''- hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.command:
        argv: [terraform, "-chdir={module}", output, -raw, synthetic]
      register: result
    - ansible.builtin.assert:
        that: result.stdout == "example"
''')
                ansible_env = dict(env, PATH=str(proxy.parent) + os.pathsep + env['PATH'])
                subprocess.run([ansible, '-i', 'localhost,', '-c', 'local', str(playbook)],
                               cwd=new, env=ansible_env, check=True, capture_output=True, text=True)
            self.assertTrue(is_moved_sentinel(module / 'terraform.tfstate'))
            raw = subprocess.run([binary, '-chdir=' + str(module), 'state', 'list'], cwd=new, capture_output=True)
            self.assertNotEqual(raw.returncode, 0)


if __name__ == '__main__':
    unittest.main()
