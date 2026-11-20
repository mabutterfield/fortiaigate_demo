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

    def test_default_destroys_host_then_only_k3s_ip(self):
        with mock.patch.object(teardown, 'run') as run, \
             mock.patch.object(teardown, 'state_resources', side_effect=[['aws_instance.this'], [teardown.EIP]]), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
             mock.patch.object(teardown, 'destroy') as destroy, contextlib.redirect_stdout(io.StringIO()):
            teardown.main(['--yolo', '--terraform-vars-dir', str(self.overrides)])
        self.assertEqual(destroy.call_count, 2)
        self.assertEqual(destroy.call_args_list[0].args[:1], (teardown.HOST,))
        self.assertEqual(destroy.call_args_list[1].kwargs['target'], teardown.EIP)
        self.assertFalse(any('aws-ecr' in ' '.join(c.args[0]) or 's3' in ' '.join(c.args[0]) for c in run.call_args_list))

    def test_keep_ip_and_skip_host_do_not_touch_prep(self):
        for args in (['--keep-eip'], ['--skip-ec2']):
            with self.subTest(args=args), mock.patch.object(teardown, 'run') as run, \
                 mock.patch.object(teardown, 'state_resources', return_value=['aws_instance.this']), \
                 mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces'), \
                 mock.patch.object(teardown, 'destroy') as destroy, contextlib.redirect_stdout(io.StringIO()):
                teardown.main(['--yolo'] + args)
                self.assertFalse(any(teardown.PREP in ' '.join(c.args[0]) for c in run.call_args_list))
                self.assertEqual(destroy.call_count, 0 if '--skip-ec2' in args else 1)

    def test_target_plan_refuses_any_other_resource_change(self):
        plan = {'resource_changes': [
            {'mode':'managed', 'address':teardown.EIP, 'change':{'actions':['delete']}},
            {'mode':'managed', 'address':'aws_s3_bucket.example', 'change':{'actions':['delete']}}]}
        with mock.patch.object(teardown, 'run', side_effect=[None, subprocess.CompletedProcess([], 0, json.dumps(plan))]) as run:
            with self.assertRaisesRegex(SystemExit, 'other changes'):
                teardown.destroy(teardown.PREP, None, True, target=teardown.EIP)
            self.assertEqual(run.call_count, 2)

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

    def test_host_destroy_failure_prevents_eip_release(self):
        with mock.patch.object(teardown, 'run'), mock.patch.object(teardown, 'state_resources', return_value=['aws_instance.this']), \
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
                teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_instance.this'])

    def test_host_interfaces_and_private_route_are_allowed(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('i-123'), response('vpc-123'),
                 response(json.dumps([{'id':'eni-host', 'instance':'i-123'}]))]):
            teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_instance.this'])
        self.assertIn('aws_route', teardown.HOST_TYPES)

    def test_vpc_not_found_cannot_pass_as_empty_interface_list(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('i-123'),
                subprocess.CalledProcessError(1, ['aws', 'ec2', 'describe-vpcs'])]):
            with self.assertRaises(subprocess.CalledProcessError):
                teardown.ensure_no_other_vpc_interfaces('wrong-account', 'us-east-2', ['aws_instance.this'])

    def test_partial_state_without_instance_allows_empty_vpc_only(self):
        def response(text):
            return subprocess.CompletedProcess([], 0, text)
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('vpc-123'), response('[]')]):
            teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_vpc.this'])
        with mock.patch.object(teardown, 'run', side_effect=[response('vpc-123'), response('vpc-123'),
                response(json.dumps([{'id': 'eni-leftover', 'instance': None}]))]):
            with self.assertRaisesRegex(SystemExit, 'other dependent resources'):
                teardown.ensure_no_other_vpc_interfaces('test', 'us-east-2', ['aws_vpc.this'])

    def test_cloud_failure_has_clear_message_and_stops_teardown(self):
        with mock.patch.object(teardown, 'run'), mock.patch.object(teardown, 'state_resources', return_value=['aws_instance.this']), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces', side_effect=subprocess.CalledProcessError(1, ['aws'])), \
             mock.patch.object(teardown, 'destroy') as destroy, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'Cannot verify the lab VPC'):
                teardown.main(['--yolo'])
            destroy.assert_not_called()

    def test_vpc_guard_failure_prevents_host_and_ip_destroy(self):
        with mock.patch.object(teardown, 'run'), mock.patch.object(teardown, 'state_resources', return_value=['aws_instance.this']), \
             mock.patch.object(teardown, 'ensure_no_other_vpc_interfaces', side_effect=SystemExit('other interfaces')), \
             mock.patch.object(teardown, 'destroy') as destroy, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'other interfaces'):
                teardown.main(['--yolo'])
            destroy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
