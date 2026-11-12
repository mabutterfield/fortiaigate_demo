from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'ansible/roles/k3s/files/select_instance_store.py'
SPEC = importlib.util.spec_from_file_location('disk_select', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def disk(path='/dev/nvme1n1', model='Amazon EC2 NVMe Instance Storage', **kwargs):
    return {'path': path, 'model': model, 'type': 'disk', **kwargs}


class InstanceStoreSelectionTests(unittest.TestCase):
    def test_accept_one_instance_store(self):
        self.assertEqual(MODULE.select_device([disk(), disk('/dev/nvme0n1', 'Amazon Elastic Block Store')]), '/dev/nvme1n1')

    def test_reject_root_partitioned_or_wrong_model(self):
        for disks, roots in [([disk()], ['/dev/nvme1n1']), ([disk(children=[{'path': '/dev/nvme1n1p1'}])], []), ([disk(model='Amazon Elastic Block Store')], [])]:
            with self.subTest(disks=disks), self.assertRaises(ValueError):
                MODULE.select_device(disks, root_devices=roots)

    def test_multiple_disks_require_explicit_selection(self):
        disks = [disk(), disk('/dev/nvme2n1')]
        with self.assertRaises(ValueError):
            MODULE.select_device(disks)
        self.assertEqual(MODULE.select_device(disks, '/dev/nvme2n1'), '/dev/nvme2n1')
        with self.assertRaises(ValueError):
            MODULE.select_device(disks, '/dev/nvme0n1')


if __name__ == '__main__':
    unittest.main()
