#!/usr/bin/env python3
"""Tear down the disposable AWS lab while preserving shared artifacts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

try:
    import state_storage
except ModuleNotFoundError:
    from scripts import state_storage

ROOT = Path(__file__).resolve().parents[1]
HOST = 'terraform/aws-ec2-k3s'
PREP = 'terraform/aws-prep'
EIP = 'aws_eip.public["k3s"]'
HOST_TYPES = {'aws_instance', 'aws_vpc', 'aws_subnet', 'aws_security_group',
              'aws_internet_gateway', 'aws_route_table', 'aws_route_table_association',
              'aws_route', 'aws_eip_association', 'local_file'}
HOST_SECRET_ADDRESSES = {'local_sensitive_file.lab_bootstrap[0]': 'local_sensitive_file',
                         **{f'random_password.lab["{name}"]': 'random_password' for name in
                            ('faig_admin', 'litellm_master', 'litellm_ui', 'litellm_postgres')}}


def run(argv, *, capture=False):
    print('$ ' + ' '.join(argv), flush=True)
    return subprocess.run(argv, cwd=ROOT, text=True, check=True,
                          stdout=subprocess.PIPE if capture else None,
                          umask=0o077 if argv and argv[0] == 'terraform' else -1)


def settings(path):
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    return {k: v for k, v in re.findall(r'^\s*(aws_profile|aws_region)\s*=\s*"([^"\n]+)"', text, re.M)}


def resolve_profile_and_vars(directory):
    if not os.environ.get('TF_WORKSPACE'):
        raise ValueError('Set TF_WORKSPACE explicitly, including TF_WORKSPACE=default when intended.')
    base = settings(ROOT / 'terraform/user.tfvars')
    prep_settings = {**settings(ROOT / PREP / '00-system.auto.tfvars'), **base,
                     **settings(ROOT / PREP / '99-local.auto.tfvars')}
    host_settings = {**settings(ROOT / HOST / '00-system.auto.tfvars'), **base,
                     **settings(ROOT / HOST / '99-local.auto.tfvars')}
    if directory:
        directory = directory.expanduser().resolve()
        prep, host = directory / 'prep.tfvars', directory / 'host.tfvars'
        if not prep.is_file() or not host.is_file():
            raise ValueError('The Terraform overrides directory must contain prep.tfvars and host.tfvars.')
        p = {**prep_settings, **settings(prep)}
        h = {**host_settings, **settings(host)}
    else:
        prep = host = None
        p, h = prep_settings, host_settings
    if any(p.get(k) != h.get(k) for k in ('aws_profile', 'aws_region')):
        raise ValueError('Prep and host overrides disagree on AWS profile or region.')
    if not all(h.get(k) for k in ('aws_profile', 'aws_region')):
        raise ValueError('AWS profile and region are required in the selected profile.')
    return h['aws_profile'], h['aws_region'], prep, host


def state_resources(module):
    result = run(['terraform', '-chdir=' + module, 'state', 'list'], capture=True)
    return [line.strip() for line in result.stdout.splitlines()
            if line.strip() and not line.startswith('data.')]


def ensure_no_other_vpc_interfaces(profile, region, host_resources):
    """Refuse host teardown if any non-host ENI remains in the lab VPC.

    This catches appliances even when their state lives in another checkout or
    workspace. An unreadable or incomplete host state fails closed.
    """
    if 'aws_vpc.this' not in host_resources:
        if 'aws_instance.this' in host_resources:
            raise SystemExit('Lab instance remains tracked but its VPC is not tracked; inspect state before teardown.')
        print('No lab VPC or instance is tracked; skipping the VPC interface check.')
        return
    vpc = run(['terraform', '-chdir=' + HOST, 'output', '-raw', 'vpc_id'], capture=True).stdout.strip()
    instance = ''
    if 'aws_instance.this' in host_resources:
        instance = run(['terraform', '-chdir=' + HOST, 'output', '-raw', 'instance_id'], capture=True).stdout.strip()
    if not re.fullmatch(r'vpc-[0-9a-f]+', vpc) or (instance and not re.fullmatch(r'i-[0-9a-f]+', instance)):
        raise SystemExit('Cannot verify the lab VPC and instance from Terraform state; inspect before teardown.')
    if 'aws_instance.this' in host_resources and not instance:
        raise SystemExit('Lab instance is tracked but its ID is unavailable; inspect before teardown.')
    # An ENI filter alone returns an empty list in the wrong account or region.
    # An explicit VPC lookup fails instead of treating that as an empty VPC.
    observed_vpc = run(['aws', 'ec2', 'describe-vpcs', '--profile', profile, '--region', region,
                        '--vpc-ids', vpc, '--query', 'Vpcs[0].VpcId', '--output', 'text'], capture=True)
    if observed_vpc.stdout.strip() != vpc:
        raise SystemExit('Lab VPC was not confirmed in the selected AWS account and region.')
    response = run(['aws', 'ec2', 'describe-network-interfaces', '--profile', profile, '--region', region,
                    '--filters', 'Name=vpc-id,Values=' + vpc,
                    '--query', 'NetworkInterfaces[].{id:NetworkInterfaceId,instance:Attachment.InstanceId}',
                    '--output', 'json'], capture=True)
    try:
        interfaces = json.loads(response.stdout)
        if not isinstance(interfaces, list) or any(not isinstance(item, dict) or not item.get('id') for item in interfaces):
            raise ValueError('bad interface response')
    except (ValueError, TypeError):
        raise SystemExit('Cannot verify VPC network interfaces; inspect before teardown.') from None
    foreign = [item['id'] for item in interfaces if item.get('instance') != instance]
    if foreign:
        raise SystemExit('Other network interfaces remain in the lab VPC (' + ', '.join(foreign) +
                         '); tear down optional appliances or other dependent resources first.')


def destroy(module, vars_file, auto_approve, *, target=None, variables=None):
    if target or module == HOST:
        # Inspect the saved plan so host cleanup cannot remove shared artifacts,
        # and a targeted EIP destroy cannot cascade into other resources.
        with tempfile.TemporaryDirectory(prefix='faig-eip-plan-') as directory:
            plan = Path(directory) / 'eip.tfplan'
            argv = ['terraform', '-chdir=' + module, 'plan', '-destroy', '-out=' + str(plan)]
            if target:
                argv.append('-target=' + target)
            if vars_file:
                argv.append('-var-file=' + str(vars_file))
            for variable in variables or []:
                argv.extend(['-var', variable])
            run(argv)
            raw = run(['terraform', '-chdir=' + module, 'show', '-json', str(plan)], capture=True)
            changes = json.loads(raw.stdout).get('resource_changes', [])
            affected = [(item['address'], item.get('type'), item['change']['actions']) for item in changes
                        if item.get('mode') == 'managed' and item.get('change', {}).get('actions') != ['no-op']]
            if target:
                invalid = any(address != target or actions != ['delete'] for address, _, actions in affected)
            else:
                invalid = any((kind not in HOST_TYPES and
                               (address not in HOST_SECRET_ADDRESSES or HOST_SECRET_ADDRESSES[address] != kind))
                              or actions != ['delete'] for address, kind, actions in affected)
            if invalid:
                raise SystemExit('Teardown plan contains other changes; nothing in that plan was applied.')
            if not affected:
                print('Teardown plan has no changes.')
                return
            label = 'the lab Elastic IP' if target else 'the listed EC2/VPC resources'
            if not auto_approve and input(f'Delete {label}? [y/N] ').strip().lower() not in ('y', 'yes'):
                raise SystemExit('Stopped before applying the teardown plan.')
            run(['terraform', '-chdir=' + module, 'apply', str(plan)])
        return
    argv = ['terraform', '-chdir=' + module, 'destroy']
    if vars_file:
        argv.append('-var-file=' + str(vars_file))
    if auto_approve:
        argv.append('-auto-approve')
    run(argv)


def read_storage_profile():
    workspace_root = Path(os.environ.get('FAIG_WORKSPACE_ROOT') or ROOT.parent).expanduser().resolve()
    return state_storage.read_storage_settings(workspace_root / '.faig-storage-settings.json')


def initialize_teardown_module(module, settings):
    if settings is None or settings.state is None:
        run(['terraform', '-chdir=' + module, 'init'])
        return []
    layout = settings.state
    if (layout.root / '.migration-in-progress.json').exists():
        raise SystemExit('State migration is incomplete; teardown cannot safely continue.')
    workspace = os.environ['TF_WORKSPACE']
    try:
        args = state_storage.prepare_external_module(ROOT / module, layout, Path(module).name,
                                                     workspace, require_existing=True)
        state_storage.secure_state_files(layout.state_path(Path(module).name, workspace),
                                         named_workspace=(workspace != 'default'))
        state_storage.prime_backend_data(layout, ROOT, Path(module).name,
                                        os.environ.get('FAIG_REAL_TERRAFORM') or shutil.which('terraform'))
    except (OSError, ValueError) as exc:
        raise SystemExit(f'External Terraform state is not ready: {exc}') from None
    run(['terraform', '-chdir=' + module, *args])
    return layout.dependency_vars(Path(module).name, workspace)


def instance_is_terminated(profile, region, instance, *, allow_not_found=False):
    """Ask AWS directly; unknown or unauthorized results never permit cleanup."""
    if not re.fullmatch(r'i-[0-9a-f]+', instance):
        raise ValueError('invalid EC2 instance ID')
    command = ['aws', 'ec2', 'describe-instances', '--profile', profile, '--region', region,
               '--instance-ids', instance, '--query', 'Reservations[0].Instances[0].State.Name',
               '--output', 'text']
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        if 'InvalidInstanceID.NotFound' in (result.stderr or ''):
            # Not found is usable only after matching a recorded account and region.
            return allow_not_found
        raise ValueError('could not verify instance termination in the selected AWS account and region')
    return result.stdout.strip() == 'terminated'


def clean_retired_instance_secrets(settings, profile, region):
    """Retry bounded cleanup for confirmed terminated instances in this workspace."""
    try:
        import lab_credentials
    except ModuleNotFoundError:
        from scripts import lab_credentials
    workspace = os.environ.get('TF_WORKSPACE', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', workspace):
        raise ValueError('invalid Terraform workspace for instance cleanup')
    root = settings.secrets_root
    directory = root / workspace
    if root.is_symlink() or directory.is_symlink():
        raise ValueError('instance secret root and workspace must not be symlinks')
    if not directory.exists():
        return 0
    if not directory.is_dir():
        raise ValueError('instance secrets workspace is not a directory')
    identity = subprocess.run(['aws', 'sts', 'get-caller-identity', '--profile', profile,
                               '--query', 'Account', '--output', 'text'], cwd=ROOT,
                              text=True, capture_output=True, check=False)
    account = identity.stdout.strip()
    if identity.returncode or not re.fullmatch(r'[0-9]{12}', account):
        raise ValueError('cannot verify the AWS account for generated secret cleanup')
    removed = 0
    for item in sorted(directory.iterdir()):
        if not re.fullmatch(r'i-[0-9a-f]+', item.name):
            continue
        if item.is_symlink() or not item.is_dir():
            raise ValueError('an instance secrets directory is unsafe')
        marker = item / '.lab-instance'
        if not marker.exists() and not marker.is_symlink():
            # Terraform may have created its tracked file before bootstrap; do
            # not infer ownership or delete an unmarked directory.
            continue
        lab_credentials.private_regular_file(marker)
        marker_data = json.loads(marker.read_text(encoding='utf-8'))
        if marker_data.get('account_id') != account or marker_data.get('region') != region:
            # Old markers without account/region and markers from other accounts
            # are not sufficient evidence for safe cleanup.
            continue
        if instance_is_terminated(profile, region, item.name, allow_not_found=True):
            if lab_credentials.remove_generated_instance_files(root, workspace, item.name, terminated=True,
                                                               account=account, region=region):
                removed += 1
    return removed


def remove_destroyed_host_backup(path, *, instance_terminated):
    """Delete a generated host state backup only after confirmed teardown."""
    if instance_terminated is not True:
        return False
    if path.is_symlink() or not path.is_file():
        raise ValueError('current host state is missing or unsafe; backup was preserved')
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
        managed = [item for item in doc.get('resources', []) if item.get('mode') == 'managed' and item.get('instances')]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('cannot verify current host state; backup was preserved') from exc
    if managed:
        raise ValueError('host state still contains managed resources; backup was preserved')
    backup = path.with_suffix(path.suffix + '.backup')
    if backup.is_symlink():
        raise ValueError('host state backup is a symlink; it was preserved')
    if not backup.exists():
        return False
    if not backup.is_file() or backup.stat().st_uid != os.getuid():
        raise ValueError('host state backup is not an owner-owned regular file; it was preserved')
    backup.unlink()
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terraform-vars-dir', type=Path,
                        default=Path(os.environ['FAIG_TERRAFORM_VARS_DIR']) if os.environ.get('FAIG_TERRAFORM_VARS_DIR') else None,
                        help='Directory containing prep.tfvars and host.tfvars for the selected workspace.')
    parser.add_argument('--keep-eip', action='store_true', help='Keep the lab Elastic IP allocated.')
    parser.add_argument('--skip-ec2', action='store_true', help='Keep the EC2/VPC stack; implies --keep-eip.')
    parser.add_argument('--auto-approve', action='store_true', help='Pass -auto-approve to Terraform.')
    parser.add_argument('--yes', action='store_true', help='Skip the script-level confirmation.')
    parser.add_argument('--yolo', action='store_true', help='Equivalent to --yes --auto-approve.')
    return parser.parse_args(argv)


_storage_operation_lock = None


def _main(argv=None):
    global _storage_operation_lock
    args = parse_args(argv)
    try:
        storage = read_storage_profile()
        if storage is not None:
            requested = os.environ.get('TF_WORKSPACE')
            if requested and requested != storage.workspace:
                raise ValueError('TF_WORKSPACE conflicts with the saved storage profile')
            os.environ['TF_WORKSPACE'] = storage.workspace
            if args.terraform_vars_dir is not None:
                if storage.terraform_vars_dir != args.terraform_vars_dir.expanduser().resolve():
                    raise ValueError('Terraform overrides directory conflicts with the saved storage profile')
            else:
                args.terraform_vars_dir = storage.terraform_vars_dir
        if storage is not None and storage.state is not None:
            if not storage.state.root.is_dir():
                raise ValueError('configured external state root is missing')
            _storage_operation_lock = state_storage.acquire_operation_lock(storage.state)
            if (storage.state.root / '.migration-in-progress.json').exists():
                raise ValueError('state migration is incomplete')
            state_storage.verify_state_manifest(storage.state)
            workspace_root = Path(os.environ.get('FAIG_WORKSPACE_ROOT') or ROOT.parent).expanduser().resolve()
            state_storage.configure_terraform_proxy(ROOT, workspace_root / '.faig-storage-settings.json')
        profile, region, prep_vars, host_vars = resolve_profile_and_vars(args.terraform_vars_dir)
    except (OSError, ValueError) as exc:
        raise SystemExit(f'Cannot read storage settings: {exc}') from None
    keep_eip = args.keep_eip or args.skip_ec2
    print(f'AWS profile: {profile}; region: {region}; workspace: {os.environ.get("TF_WORKSPACE", "default")}')
    print('EC2/VPC: ' + ('retain' if args.skip_ec2 else 'destroy'))
    print('Lab Elastic IP: ' + ('retain' if keep_eip else 'release after EC2 teardown'))
    print('ECR, S3, shared prep resources and optional appliances: retain')
    if not (args.yes or args.yolo):
        if input('Proceed with lab teardown? [y/N] ').strip().lower() not in ('y', 'yes'):
            raise SystemExit('Stopped before teardown.')
    run(['aws', 'sts', 'get-caller-identity', '--profile', profile])
    auto = args.auto_approve or args.yolo
    destroyed_instance = None
    if not args.skip_ec2:
        host_variables = initialize_teardown_module(HOST, storage)
        if storage is not None:
            host_variables += ['lab_generated_secrets_enabled=true', f'lab_secrets_root={storage.secrets_root}']
        resources = state_resources(HOST)
        if resources:
            if storage is not None and 'aws_instance.this' in resources:
                value = run(['terraform', '-chdir=' + HOST, 'output', '-raw', 'instance_id'], capture=True).stdout.strip()
                if not re.fullmatch(r'i-[0-9a-f]+', value):
                    raise SystemExit('Cannot identify the host instance before teardown; no destroy plan was applied.')
                destroyed_instance = value
            try:
                ensure_no_other_vpc_interfaces(profile, region, resources)
            except subprocess.CalledProcessError as exc:
                raise SystemExit(f'Cannot verify the lab VPC in Terraform/AWS (exit {exc.returncode}); '
                                 'no teardown plan was applied. Check account, region, session and state.') from None
            if host_variables:
                destroy(HOST, host_vars, auto, variables=host_variables)
            else:
                destroy(HOST, host_vars, auto)
        else:
            print('No disposable host resources remain in this workspace.')
    if not keep_eip:
        prep_variables = initialize_teardown_module(PREP, storage)
        if EIP in state_resources(PREP):
            if prep_variables:
                destroy(PREP, prep_vars, auto, target=EIP, variables=prep_variables)
            else:
                destroy(PREP, prep_vars, auto, target=EIP)
        else:
            print('No lab Elastic IP is tracked in this workspace.')
    if storage is not None and not args.skip_ec2:
        try:
            removed = clean_retired_instance_secrets(storage, profile, region)
            if destroyed_instance and instance_is_terminated(profile, region, destroyed_instance):
                workspace = os.environ['TF_WORKSPACE']
                if storage.state is not None:
                    path = storage.state.state_path(Path(HOST).name, workspace)
                elif workspace == 'default':
                    path = ROOT / HOST / 'terraform.tfstate'
                else:
                    path = ROOT / HOST / 'terraform.tfstate.d' / workspace / 'terraform.tfstate'
                if remove_destroyed_host_backup(path, instance_terminated=True):
                    print('Removed the destroyed host state backup containing generated credentials.')
        except (OSError, ValueError) as exc:
            raise SystemExit(f'Cloud teardown completed, but generated secret cleanup stopped: {exc}') from None
        print(f'Cleaned generated credentials for {removed} confirmed terminated instance(s).')
    print('Lab teardown finished; ECR and S3 were not modified.')


def main(argv=None):
    global _storage_operation_lock
    try:
        return _main(argv)
    finally:
        if _storage_operation_lock is not None:
            _storage_operation_lock.close()
            _storage_operation_lock = None


if __name__ == '__main__':
    main()
