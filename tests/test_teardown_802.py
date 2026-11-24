import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import teardown_802 as teardown


class TeardownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'terraform').mkdir()
        (self.root / 'terraform/user.tfvars').write_text('aws_profile = "lab"\naws_region = "us-east-1"\n')
        self.overrides = self.root / 'ohio'
        self.overrides.mkdir()
        for name in ('prep.tfvars', 'host.tfvars'):
            (self.overrides / name).write_text('aws_region = "us-east-2"\n')
        self.root_patch = mock.patch.object(teardown, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.env_patch = mock.patch.dict(os.environ, {'TF_WORKSPACE': 'ohio-802'}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        # Bucket names come from terraform state; flow tests use no tracked buckets
        # unless they patch this themselves.
        self.real_prep_bucket_names = teardown.prep_bucket_names
        self.bucket_patch = mock.patch.object(teardown, 'prep_bucket_names', return_value={})
        self.bucket_patch.start()
        self.addCleanup(self.bucket_patch.stop)

    def test_matching_workspace_overrides(self):
        profile, region, prep, host = teardown.resolve_profile_and_vars(self.overrides)
        self.assertEqual((profile, region), ('lab', 'us-east-2'))
        self.assertEqual(prep, (self.overrides / 'prep.tfvars').resolve())
        self.assertEqual(host, (self.overrides / 'host.tfvars').resolve())

    def test_missing_workspace_and_region_mismatch_fail_before_destroy(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'TF_WORKSPACE'):
                teardown.resolve_profile_and_vars(self.overrides)
        (self.overrides / 'host.tfvars').write_text('aws_region = "us-east-1"\n')
        with self.assertRaisesRegex(ValueError, 'disagree'):
            teardown.resolve_profile_and_vars(self.overrides)

    def test_module_local_overrides_are_considered(self):
        local = self.root / teardown.PREP
        local.mkdir(parents=True)
        (local / '99-local.auto.tfvars').write_text('aws_region = "us-east-2"\n')
        with self.assertRaisesRegex(ValueError, 'disagree'):
            teardown.resolve_profile_and_vars(None)

    def test_default_destroys_host_then_eips_and_lab_iam(self):
        prep = [teardown.EIP, 'aws_iam_role.ec2', 'aws_s3_bucket.fortiaigate_syslog[0]']
        with mock.patch.object(teardown, 'run') as run, \
             mock.patch.object(teardown, 'state_resources', side_effect=[prep, ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy') as destroy, \
             mock.patch.object(teardown, 'destroy_selected') as selected, contextlib.redirect_stdout(io.StringIO()):
            teardown.main(['--yolo', '--terraform-vars-dir', str(self.overrides)])
        self.assertEqual(destroy.call_count, 1)
        self.assertEqual(destroy.call_args.args[0], teardown.HOST)
        # Without --keep-eip the whole aws-prep module is destroyed, buckets included.
        self.assertEqual(set(selected.call_args.args[1]), set(prep))
        self.assertTrue(selected.call_args.kwargs['full'])
        self.assertTrue(selected.call_args_list[0].kwargs['check_only'])
        self.assertNotIn('check_only', selected.call_args.kwargs)
        self.assertFalse(any('aws-ecr' in ' '.join(c.args[0]) for c in run.call_args_list))

    def test_keep_ip_still_cleans_iam_but_skip_ec2_keeps_both(self):
        for args in (['--keep-eip'], ['--skip-ec2']):
            with self.subTest(args=args), mock.patch.object(teardown, 'run'), \
                 mock.patch.object(teardown, 'state_resources', side_effect=[[teardown.EIP, 'aws_iam_role.ec2'], ['aws_instance.this']]), \
                 mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
                 mock.patch.object(teardown, 'destroy') as destroy, \
                 mock.patch.object(teardown, 'destroy_selected') as selected, contextlib.redirect_stdout(io.StringIO()):
                teardown.main(['--yolo'] + args)
                if '--skip-ec2' in args:
                    destroy.assert_not_called()
                    selected.assert_not_called()
                else:
                    self.assertEqual(selected.call_args.args[1], ['aws_iam_role.ec2'])

    def test_appliances_are_destroyed_before_host_and_iam(self):
        calls = []
        with mock.patch.object(teardown, 'run'), \
             mock.patch.object(teardown, 'module_state_exists', return_value=True), \
             mock.patch.object(teardown, 'initialize_teardown_module', return_value=[]), \
             mock.patch.object(teardown, 'state_resources', side_effect=[
                 [teardown.EIP, 'aws_iam_role.ec2', 'aws_s3_bucket.fortiaigate_syslog[0]'],
                 ['aws_instance.this[0]', 'aws_s3_object.license[0]'],
                 ['aws_instance.this[0]'], ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy_selected', side_effect=lambda module, *a, **k: calls.append(module)), \
             mock.patch.object(teardown, 'destroy', side_effect=lambda module, *a, **k: calls.append(module)), \
             contextlib.redirect_stdout(io.StringIO()):
            teardown.main(['--yolo'])
        # The prep plan is checked first, then applied last.
        self.assertEqual(calls, [teardown.PREP, 'terraform/aws-fortiweb', 'terraform/aws-fortigate', teardown.HOST, teardown.PREP])

    def test_external_teardown_uses_saved_workspace_and_dependency_paths(self):
        from scripts.state_storage import StateLayout, StorageSettings
        layout = StateLayout((self.root / 'external-state').resolve())
        layout.root.mkdir(mode=0o700)
        settings = StorageSettings((self.root / 'external-secrets').resolve(), layout, 'ohio-802')
        with mock.patch.object(teardown, 'read_storage_profile', return_value=settings), \
             mock.patch.object(teardown.state_storage, 'verify_state_manifest'), \
             mock.patch.object(teardown.state_storage, 'configure_terraform_proxy'), \
             mock.patch.object(teardown, 'initialize_teardown_module', side_effect=[['aws_ecr_state_path=/state/ecr'], ['aws_prep_state_path=/state/prep']]), \
             mock.patch.object(teardown, 'run', side_effect=lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, 'i-123\n') if 'output' in argv else None), \
             mock.patch.object(teardown, 'instance_is_terminated', return_value=False), \
             mock.patch.object(teardown, 'state_resources', side_effect=[[teardown.EIP], ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy') as destroy, \
             mock.patch.object(teardown, 'destroy_selected') as selected, contextlib.redirect_stdout(io.StringIO()):
            teardown.main(['--yolo'])
        host_vars = destroy.call_args_list[0].kwargs['variables']
        self.assertIn('aws_prep_state_path=/state/prep', host_vars)
        self.assertIn('lab_generated_secrets_enabled=true', host_vars)
        self.assertTrue(any(v.startswith('lab_secrets_root=') for v in host_vars))
        self.assertEqual(selected.call_args.kwargs['variables'], ['aws_ecr_state_path=/state/ecr'])

    def test_refused_prep_plan_stops_before_anything_is_destroyed(self):
        def refuse(module, *args, **kwargs):
            if kwargs.get('check_only'):
                raise SystemExit('Teardown plan includes an unapproved change outside the lab environment')
        with mock.patch.object(teardown, 'run'), \
             mock.patch.object(teardown, 'module_state_exists', return_value=True), \
             mock.patch.object(teardown, 'initialize_teardown_module', return_value=[]), \
             mock.patch.object(teardown, 'state_resources', side_effect=[[teardown.EIP, 'aws_iam_role.ec2']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy') as destroy, \
             mock.patch.object(teardown, 'destroy_selected', side_effect=refuse) as selected, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'unapproved change'):
                teardown.main(['--yolo'])
        destroy.assert_not_called()
        self.assertEqual(selected.call_count, 1)

    def test_check_only_plan_is_validated_but_not_applied(self):
        changes = [{'mode': 'managed', 'address': address, 'change': {'actions': ['delete']}}
                   for address in ('aws_iam_role.fortiweb_cloudinit[0]', 'aws_s3_bucket_policy.fortiweb_cloudinit[0]')]
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps({'resource_changes': changes}))]) as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            teardown.destroy_selected(teardown.PREP, ['aws_iam_role.fortiweb_cloudinit[0]'], teardown.PREP_IAM_RESOURCES,
                                      None, True, check_only=True)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(any('apply' in call.args[0] for call in run.call_args_list))
        self.assertIn('2 deletion(s)', output.getvalue())

    def test_generated_secrets_are_cleaned_before_prep_is_applied(self):
        from scripts.state_storage import StateLayout, StorageSettings
        layout = StateLayout((self.root / 'external-state').resolve())
        layout.root.mkdir(mode=0o700)
        settings = StorageSettings((self.root / 'external-secrets').resolve(), layout, 'ohio-802')
        calls = []
        with mock.patch.object(teardown, 'read_storage_profile', return_value=settings), \
             mock.patch.object(teardown.state_storage, 'verify_state_manifest'), \
             mock.patch.object(teardown.state_storage, 'configure_terraform_proxy'), \
             mock.patch.object(teardown, 'initialize_teardown_module', return_value=[]), \
             mock.patch.object(teardown, 'module_state_exists', return_value=False), \
             mock.patch.object(teardown, 'run', side_effect=lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, 'i-123\n') if 'output' in argv else None), \
             mock.patch.object(teardown, 'instance_is_terminated', return_value=False), \
             mock.patch.object(teardown, 'state_resources', side_effect=[[teardown.EIP], ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy', side_effect=lambda module, *a, **k: calls.append(('destroy', module))), \
             mock.patch.object(teardown, 'clean_retired_instance_secrets', side_effect=lambda *a: calls.append(('secrets',)) or 1), \
             mock.patch.object(teardown, 'destroy_selected',
                               side_effect=lambda module, *a, **k: calls.append(('check' if k.get('check_only') else 'apply', module))), \
             contextlib.redirect_stdout(io.StringIO()):
            teardown.main(['--yolo'])
        self.assertEqual(calls, [('check', teardown.PREP), ('destroy', teardown.HOST), ('secrets',), ('apply', teardown.PREP)])

    def test_prep_selection_is_full_module_unless_eips_are_kept(self):
        prep = [teardown.EIP, 'aws_iam_role.ec2', 'aws_s3_bucket.fortiweb_cloudinit[0]',
                'aws_s3_bucket_versioning.fortiweb_cloudinit[0]', 'aws_s3_bucket.fortiaigate_syslog[0]']
        targets, allowed, full = teardown.prep_teardown_selection(prep, keep_eip=False)
        self.assertEqual((targets, full), (prep, True))
        self.assertIn('aws_s3_bucket_lifecycle_configuration.fortiaigate_syslog', allowed)
        targets, allowed, full = teardown.prep_teardown_selection(prep, keep_eip=True)
        self.assertFalse(full)
        self.assertNotIn(teardown.EIP, targets)
        self.assertNotIn('aws_eip.public', allowed)
        self.assertFalse(any(base.startswith('aws_ecr') for base in teardown.PREP_RESOURCES))

    def test_unknown_prep_resource_is_refused_by_name_before_planning(self):
        with mock.patch.object(teardown, 'run') as run:
            with self.assertRaisesRegex(SystemExit, r'aws_ecr_repository\.this\["api"\]'):
                teardown.destroy_selected(teardown.PREP, ['aws_iam_role.ec2', 'aws_ecr_repository.this["api"]'],
                                          teardown.PREP_RESOURCES, None, True, full=True)
            run.assert_not_called()

    def test_full_plan_has_no_targets(self):
        plan = {'resource_changes': [{'mode': 'managed', 'address': 'aws_s3_bucket.fortiweb_cloudinit[0]',
                                      'change': {'actions': ['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan)), None]) as run:
            teardown.destroy_selected(teardown.PREP, ['aws_s3_bucket.fortiweb_cloudinit[0]'], teardown.PREP_RESOURCES,
                                      None, True, full=True)
        self.assertFalse(any(arg.startswith('-target=') for arg in run.call_args_list[0].args[0]))
        self.assertIn('apply', run.call_args_list[-1].args[0])

    def test_bucket_names_read_from_state(self):
        shown = 'resource "aws_s3_bucket" "fortiweb_cloudinit" {\n    arn = "arn:aws:s3:::lab-fwb"\n    bucket = "lab-fwb"\n    bucket_domain_name = "lab-fwb.s3.amazonaws.com"\n}\n'
        with mock.patch.object(teardown, 'run', return_value=subprocess.CompletedProcess([], 0, shown)) as run:
            names = self.real_prep_bucket_names([teardown.EIP, 'aws_s3_bucket.fortiweb_cloudinit[0]',
                                                 'aws_s3_bucket_versioning.fortiweb_cloudinit[0]'])
        self.assertEqual(names, {'aws_s3_bucket.fortiweb_cloudinit[0]': 'lab-fwb'})
        self.assertEqual(run.call_count, 1)

    def test_empty_bucket_deletes_versions_and_markers_until_empty(self):
        page = {'Versions': [{'Key': 'a', 'VersionId': '1'}], 'DeleteMarkers': [{'Key': 'a', 'VersionId': '2'}]}
        with mock.patch.object(teardown, 'aws_json', side_effect=[page, {}, {}]) as aws:
            self.assertEqual(teardown.empty_bucket('lab', 'us-east-2', 'lab-fwb'), 2)
        self.assertEqual([call.args[0][2] for call in aws.call_args_list],
                         ['list-object-versions', 'delete-objects', 'list-object-versions'])
        with mock.patch.object(teardown, 'aws_json', side_effect=[page, {'Errors': [{'Key': 'a'}]}]):
            with self.assertRaisesRegex(SystemExit, 'Could not delete 1 object'):
                teardown.empty_bucket('lab', 'us-east-2', 'lab-fwb')

    def test_syslog_choice_is_required_before_anything_is_destroyed(self):
        args = teardown.parse_args(['--yolo'])
        with mock.patch.object(teardown, 'bucket_object_count', return_value=0):
            self.assertIsNone(teardown.resolve_syslog_choice(args, 'lab-syslog', 'lab', 'us-east-2'))
        self.assertIsNone(teardown.resolve_syslog_choice(args, None, 'lab', 'us-east-2'))
        with mock.patch.object(teardown, 'bucket_object_count', return_value=3):
            with self.assertRaisesRegex(SystemExit, '--export-syslog DIR.*--discard-syslog'):
                teardown.resolve_syslog_choice(args, 'lab-syslog', 'lab', 'us-east-2')
            self.assertEqual(teardown.resolve_syslog_choice(teardown.parse_args(['--yolo', '--discard-syslog']),
                                                            'lab-syslog', 'lab', 'us-east-2'), 'discard')
            with self.assertRaisesRegex(SystemExit, 'outside the repository'):
                teardown.resolve_syslog_choice(teardown.parse_args(['--yolo', '--export-syslog', str(self.root / 'logs')]),
                                               'lab-syslog', 'lab', 'us-east-2')
            outside = Path(tempfile.mkdtemp()) / 'syslog'
            self.addCleanup(lambda: __import__('shutil').rmtree(outside.parent, ignore_errors=True))
            self.assertEqual(teardown.resolve_syslog_choice(teardown.parse_args(['--yolo', '--export-syslog', str(outside)]),
                                                            'lab-syslog', 'lab', 'us-east-2'), outside.resolve())

    def test_syslog_is_exported_then_buckets_emptied_before_prep_destroy(self):
        calls = []
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(outside, ignore_errors=True))
        buckets = {'aws_s3_bucket.fortiaigate_syslog[0]': 'lab-syslog', 'aws_s3_bucket.fortiweb_cloudinit[0]': 'lab-fwb'}
        with mock.patch.object(teardown, 'run'), \
             mock.patch.object(teardown, 'module_state_exists', return_value=False), \
             mock.patch.object(teardown, 'initialize_teardown_module', return_value=[]), \
             mock.patch.object(teardown, 'state_resources', side_effect=[list(buckets), []]), \
             mock.patch.object(teardown, 'prep_bucket_names', return_value=buckets), \
             mock.patch.object(teardown, 'bucket_object_count', return_value=5), \
             mock.patch.object(teardown, 'export_syslog', side_effect=lambda *a: calls.append(('export', a[2]))), \
             mock.patch.object(teardown, 'empty_bucket', side_effect=lambda *a: calls.append(('empty', a[2])) or 5), \
             mock.patch.object(teardown, 'destroy_selected',
                               side_effect=lambda module, *a, **k: calls.append(('check' if k.get('check_only') else 'destroy', module))), \
             contextlib.redirect_stdout(io.StringIO()):
            teardown.main(['--yolo', '--export-syslog', str(outside / 'syslog')])
        self.assertEqual(calls, [('check', teardown.PREP), ('export', 'lab-syslog'), ('empty', 'lab-syslog'),
                                 ('empty', 'lab-fwb'), ('destroy', teardown.PREP)])

    def test_target_plan_refuses_any_other_resource_change(self):
        plan = {'resource_changes': [
            {'mode':'managed', 'address':teardown.EIP, 'change':{'actions':['delete']}},
            {'mode':'managed', 'address':'aws_s3_bucket.example', 'change':{'actions':['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan))]) as run:
            with self.assertRaisesRegex(SystemExit, 'other changes'):
                teardown.destroy(teardown.PREP, None, True, target=teardown.EIP)
            self.assertEqual(run.call_count, 2)

    def test_selected_plan_refuses_syslog_bucket_or_unrelated_s3_objects(self):
        for address in ('aws_s3_bucket.fortiaigate_syslog[0]', 'aws_s3_object.unrelated[0]', 'aws_ecr_repository.this["api"]'):
            plan = {'resource_changes': [
                {'mode': 'managed', 'address': 'aws_s3_object.license[0]', 'change': {'actions': ['delete']}},
                {'mode': 'managed', 'address': address, 'change': {'actions': ['delete']}}]}
            with self.subTest(address=address), mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan))]) as run:
                with self.assertRaisesRegex(SystemExit, 'unapproved change'):
                    teardown.destroy_selected('terraform/aws-fortiweb', ['aws_s3_object.license[0]'], teardown.APPLIANCE_RESOURCES, None, True)
                self.assertEqual(run.call_count, 2)

    def test_rejected_plan_identifies_resource_and_action(self):
        plan = {'resource_changes': [
            {'mode': 'managed', 'address': 'aws_s3_bucket_policy.example[0]',
             'change': {'actions': ['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan))]):
            with self.assertRaisesRegex(SystemExit, r'aws_s3_bucket_policy\.example\[0\] \(delete\)'):
                teardown.destroy_selected(teardown.PREP, ['aws_iam_role.ec2'], teardown.PREP_IAM_RESOURCES, None, True)

    def test_selected_plan_allows_fortiweb_cloud_init_objects(self):
        changes = [{'mode': 'managed', 'address': f'aws_s3_object.{name}[0]', 'change': {'actions': ['delete']}}
                   for name in ('config_generated', 'config_file', 'license')]
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps({'resource_changes': changes})), None]) as run:
            teardown.destroy_selected('terraform/aws-fortiweb', [change['address'] for change in changes], teardown.APPLIANCE_RESOURCES, None, True)
            self.assertEqual(run.call_count, 3)

    def test_selected_prep_plan_refuses_unrelated_eip(self):
        plan = {'resource_changes': [{'mode': 'managed', 'address': 'aws_eip.public["unrelated"]',
                                      'change': {'actions': ['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan))]) as run:
            with self.assertRaisesRegex(SystemExit, 'unapproved change'):
                teardown.destroy_selected(teardown.PREP, [teardown.EIP], {'aws_eip.public'}, None, True)
            self.assertEqual(run.call_count, 2)

    def test_prep_plan_can_remove_fortiweb_role_and_dependent_bucket_policy(self):
        changes = [{'mode': 'managed', 'address': address, 'change': {'actions': ['delete']}}
                   for address in ('aws_iam_role.fortiweb_cloudinit[0]', 'aws_s3_bucket_policy.fortiweb_cloudinit[0]')]
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps({'resource_changes': changes})), None]) as run:
            teardown.destroy_selected(teardown.PREP, ['aws_iam_role.fortiweb_cloudinit[0]'], teardown.PREP_IAM_RESOURCES, None, True)
            self.assertEqual(run.call_count, 3)

    def test_target_plan_applies_only_single_ip(self):
        plan = {'resource_changes': [{'mode':'managed', 'address':teardown.EIP, 'change':{'actions':['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan)), None]) as run:
            teardown.destroy(teardown.PREP, self.overrides / 'prep.tfvars', True, target=teardown.EIP)
            self.assertIn('apply', run.call_args_list[-1].args[0])

    def test_host_plan_refuses_shared_resource_deletion(self):
        plan = {'resource_changes': [
            {'mode':'managed', 'type':'aws_instance', 'address':'aws_instance.this', 'change':{'actions':['delete']}},
            {'mode':'managed', 'type':'aws_ecr_repository', 'address':'aws_ecr_repository.this', 'change':{'actions':['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan))]) as run:
            with self.assertRaisesRegex(SystemExit, 'other changes'):
                teardown.destroy(teardown.HOST, None, True)
            self.assertEqual(run.call_count, 2)

    def test_host_plan_allows_only_named_generated_credential_resources(self):
        changes = [{'mode': 'managed', 'type': kind, 'address': address, 'change': {'actions': ['delete']}}
                   for address, kind in teardown.HOST_SECRET_ADDRESSES.items()]
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps({'resource_changes': changes})), None]) as run:
            teardown.destroy(teardown.HOST, None, True)
            self.assertIn('apply', run.call_args_list[-1].args[0])
        changes.append({'mode': 'managed', 'type': 'random_password', 'address': 'random_password.other', 'change': {'actions': ['delete']}})
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps({'resource_changes': changes}))]) as run:
            with self.assertRaisesRegex(SystemExit, 'other changes'):
                teardown.destroy(teardown.HOST, None, True)
            self.assertEqual(run.call_count, 2)

    def test_cleanup_only_deletes_verified_terminated_instance_files(self):
        from scripts.lab_credentials import validate_instance_directory
        from scripts.state_storage import StorageSettings
        root = (self.root / 'secrets').resolve()
        stopped = root / 'ohio-802/i-123'
        running = root / 'ohio-802/i-456'
        for folder in (stopped, running):
            folder.mkdir(parents=True, mode=0o700)
            validate_instance_directory(folder, root=root, workspace='ohio-802', instance=folder.name,
                                        account='123456789012', region='us-east-2')
            (folder / 'quickstart-smoke-key.json').write_text('fictional')
        account = subprocess.CompletedProcess([], 0, '123456789012\n', '')
        with mock.patch.object(teardown.subprocess, 'run', return_value=account), \
             mock.patch.object(teardown, 'instance_is_terminated', side_effect=lambda _p, _r, i, **_k: i == 'i-123'):
            self.assertEqual(teardown.clean_retired_instance_secrets(StorageSettings(root, None), 'profile', 'us-east-2'), 1)
        self.assertFalse(stopped.exists())
        self.assertTrue(running.exists())

    def test_cleanup_keeps_markers_from_other_account_even_if_instance_missing(self):
        from scripts.lab_credentials import validate_instance_directory
        from scripts.state_storage import StorageSettings
        root = (self.root / 'secrets').resolve()
        folder = root / 'ohio-802/i-123'
        folder.mkdir(parents=True, mode=0o700)
        validate_instance_directory(folder, root=root, workspace='ohio-802', instance='i-123',
                                    account='123456789012', region='us-east-2')
        (folder / 'quickstart-smoke-key.json').write_text('fictional')
        identity = subprocess.CompletedProcess([], 0, '999999999999\n', '')
        with mock.patch.object(teardown.subprocess, 'run', return_value=identity), \
             mock.patch.object(teardown, 'instance_is_terminated') as query:
            self.assertEqual(teardown.clean_retired_instance_secrets(StorageSettings(root, None), 'profile', 'us-east-2'), 0)
            query.assert_not_called()
        self.assertTrue(folder.exists())

    def test_instance_lookup_accepts_only_explicit_termination(self):
        terminated = subprocess.CompletedProcess([], 0, 'terminated\n', '')
        active = subprocess.CompletedProcess([], 0, 'running\n', '')
        missing = subprocess.CompletedProcess([], 255, '', 'InvalidInstanceID.NotFound')
        denied = subprocess.CompletedProcess([], 255, '', 'AccessDenied')
        with mock.patch.object(teardown.subprocess, 'run', side_effect=[terminated, active, missing, denied]):
            self.assertTrue(teardown.instance_is_terminated('p', 'r', 'i-123'))
            self.assertFalse(teardown.instance_is_terminated('p', 'r', 'i-123'))
            self.assertFalse(teardown.instance_is_terminated('p', 'r', 'i-123'))
            with self.assertRaisesRegex(ValueError, 'could not verify'):
                teardown.instance_is_terminated('p', 'r', 'i-123')

    def test_generated_state_backup_removed_only_after_termination_and_empty_state(self):
        state = self.root / 'host.tfstate'
        backup = self.root / 'host.tfstate.backup'
        backup.write_text('fictional-generated-credentials')
        state.write_text(json.dumps({'version': 4, 'lineage': 'fixture', 'resources': [{'mode': 'managed', 'instances': [{}]}]}))
        self.assertFalse(teardown.remove_destroyed_host_backup(state, instance_terminated=False))
        self.assertTrue(backup.exists())
        with self.assertRaisesRegex(ValueError, 'still contains'):
            teardown.remove_destroyed_host_backup(state, instance_terminated=True)
        self.assertTrue(backup.exists())
        state.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'cannot verify'):
            teardown.remove_destroyed_host_backup(state, instance_terminated=True)
        self.assertTrue(backup.exists())
        state.write_text(json.dumps({'version': 4, 'lineage': 'fixture', 'resources': []}))
        self.assertTrue(teardown.remove_destroyed_host_backup(state, instance_terminated=True))
        self.assertFalse(backup.exists())

    def test_host_destroy_failure_prevents_eip_release(self):
        with mock.patch.object(teardown, 'run'), mock.patch.object(teardown, 'state_resources', side_effect=[[], ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy', side_effect=subprocess.CalledProcessError(1, ['terraform'])) as destroy, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                teardown.main(['--yolo'])
            self.assertEqual(destroy.call_count, 1)

    def test_appliance_interface_is_detected_before_destroy(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        interfaces = json.dumps([{'id': 'eni-host', 'instance': 'i-123'},
                                 {'id': 'eni-appliance', 'instance': 'i-456'}])
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('i-123'), response('vpc-123'), response(interfaces)]):
            with self.assertRaisesRegex(SystemExit, 'tear down optional appliances'):
                teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_vpc.this', 'aws_instance.this'])

    def test_host_interfaces_and_private_route_are_allowed(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('i-123'), response('vpc-123'),
                 response(json.dumps([{'id':'eni-host', 'instance':'i-123'}]))]):
            teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_vpc.this', 'aws_instance.this'])
        self.assertIn('aws_route', teardown.HOST_TYPES)

    def test_vpc_not_found_cannot_pass_as_empty_interface_list(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('i-123'),
                subprocess.CalledProcessError(1, ['aws', 'ec2', 'describe-vpcs'])]):
            with self.assertRaises(subprocess.CalledProcessError):
                teardown.ensure_no_other_vpc_interfaces('wrong-account', 'us-east-2', ['aws_vpc.this', 'aws_instance.this'])

    def test_partial_state_without_instance_allows_empty_vpc_only(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('vpc-123'), response('[]')]):
            teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_vpc.this'])
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('vpc-123'),
                response(json.dumps([{'id': 'eni-leftover', 'instance': None}]))]):
            with self.assertRaisesRegex(SystemExit, 'other dependent resources'):
                teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_vpc.this'])

    def test_partial_state_without_vpc_skips_eni_check_only_without_instance(self):
        with mock.patch.object(teardown, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_security_group.this'])
            run.assert_not_called()
            with self.assertRaisesRegex(SystemExit, 'instance remains tracked'):
                teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_instance.this'])
            run.assert_not_called()

    def test_cloud_failure_has_clear_message_and_stops_teardown(self):
        with mock.patch.object(teardown, 'run'), mock.patch.object(teardown, 'state_resources', side_effect=[[], ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces', side_effect=subprocess.CalledProcessError(1, ['aws'])), \
             mock.patch.object(teardown, 'destroy') as destroy, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'Cannot verify the lab VPC'):
                teardown.main(['--yolo'])
            destroy.assert_not_called()

    def test_vpc_guard_failure_prevents_host_and_ip_destroy(self):
        with mock.patch.object(teardown, 'run'), mock.patch.object(teardown, 'state_resources', side_effect=[[], ['aws_instance.this']]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces', side_effect=SystemExit('other interfaces')), \
             mock.patch.object(teardown, 'destroy') as destroy, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'other interfaces'):
                teardown.main(['--yolo'])
            destroy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
