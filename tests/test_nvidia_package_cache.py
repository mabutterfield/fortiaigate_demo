import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'nvidia_package_cache.py'
spec = importlib.util.spec_from_file_location('nvidia_cache', SCRIPT)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class NvidiaCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.packages = self.root / 'debs'
        self.packages.mkdir()
        self.bundle = self.root / 'cache.tar'
        self.names = cache.required('595-server')
        for name in self.names:
            (self.packages / (name + '.deb')).write_bytes(name.encode())
        self.id_patch = patch.object(cache, 'identity', return_value={'os_id': 'ubuntu', 'os_version': '24.04', 'arch': 'amd64'})
        self.id_patch.start()
        self.addCleanup(self.id_patch.stop)
        self.field_patch = patch.object(cache, 'fields', side_effect=lambda path: {'Package': path.stem, 'Version': '595.91.07-ubuntu1', 'Architecture': 'amd64'})
        self.field_patch.start()
        self.addCleanup(self.field_patch.stop)

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cache.build(argparse.Namespace(output=self.bundle, packages=self.packages, driver_suffix='595-server'))

    def test_build_and_prepare_pin_versions(self):
        self.build()
        args = argparse.Namespace(archive=self.bundle, sha256=cache.digest(self.bundle), driver_suffix='595-server', root=self.root / 'repo')
        out = io.StringIO()
        with patch.object(cache.subprocess, 'check_output', return_value='Package: test\nVersion: 1\nArchitecture: amd64\n'), contextlib.redirect_stdout(out):
            cache.prepare(args)
        result = json.loads(out.getvalue())
        self.assertEqual(result['packages'], [name + '=595.91.07-ubuntu1' for name in self.names])
        self.assertTrue((Path(result['repository']) / 'Packages').is_file())

    def test_checksum_mismatch_refuses_bundle(self):
        self.build()
        args = argparse.Namespace(archive=self.bundle, sha256='0' * 64, driver_suffix='595-server', root=self.root / 'repo')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            cache.prepare(args)

    def test_missing_required_driver_package_rejected(self):
        (self.packages / (self.names[0] + '.deb')).unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.build()
        self.assertFalse(self.bundle.exists())

    def test_bundle_with_unexpected_path_rejected(self):
        with tarfile.open(self.bundle, 'w') as tar:
            info = tarfile.TarInfo('../escape.deb')
            info.size = 1
            tar.addfile(info, io.BytesIO(b'x'))
        args = argparse.Namespace(archive=self.bundle, sha256=cache.digest(self.bundle), driver_suffix='595-server', root=self.root / 'repo')
        with self.assertRaisesRegex(ValueError, 'unexpected paths'):
            cache.prepare(args)


if __name__ == '__main__':
    unittest.main()
