import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'initialize.py'
spec = importlib.util.spec_from_file_location('faig_initialize', MODULE)
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)


class Reply:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return json.dumps(self.value).encode()


class BootstrapTests(unittest.TestCase):
    def test_rotation_and_missing_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ('FAIG-b.lic', 'FAIG-a.lic'):
                (folder / name).write_text('license')
            selected, marker = init.choose_license(folder)
            self.assertEqual(selected.name, 'FAIG-a.lic')
            init.record_license(marker, selected.name)
            self.assertEqual(init.choose_license(folder)[0].name, 'FAIG-b.lic')
            init.record_license(marker, 'FAIG-b.lic')
            self.assertEqual(init.choose_license(folder)[0].name, 'FAIG-a.lic')
            marker.write_text('missing.lic')
            with self.assertRaises(ValueError):
                init.choose_license(folder)

    def test_setup_upload_then_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'FAIG-a.lic').write_text('test-license')
            config = folder / 'setup.json'
            config.write_text(json.dumps({'email': 'test@example.com', 'username': 'admin', 'password': 'secret', 'organization_name': 'test'}))
            config.chmod(0o600)
            requests = []
            class Client:
                def open(self, request, timeout):
                    requests.append(request)
                    if request.full_url.endswith('/setup-status'):
                        return Reply({'needs_setup': True})
                    if request.full_url.endswith('/setup'):
                        return Reply({'csrf_token': 'test-token'})
                    return Reply([{'status': 'Active'}])
            argv = ['initialize.py', '--url', 'https://lab.example', '--setup-file', str(config), '--licenses', str(folder)]
            with patch.object(init.sys, 'argv', argv), patch.object(init.urllib.request, 'build_opener', return_value=Client()):
                init.main()
            self.assertEqual([r.method for r in requests], ['GET', 'POST', 'POST'])
            self.assertEqual(requests[2].get_header('X-csrf-token'), 'test-token')
            self.assertIn(b'name="files"', requests[2].data)
            self.assertEqual((folder / '.last-used').read_text(), 'FAIG-a.lic\n')

    def test_existing_setup_is_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'FAIG-a.lic').write_text('license')
            config = folder / 'setup.json'
            config.write_text(json.dumps({'email': 'e', 'username': 'u', 'password': 'p', 'organization_name': 'o'}))
            config.chmod(0o600)
            class Client:
                def open(self, request, timeout):
                    return Reply({'needs_setup': False})
            argv = ['initialize.py', '--url', 'https://lab.example', '--setup-file', str(config), '--licenses', str(folder)]
            with patch.object(init.sys, 'argv', argv), patch.object(init.urllib.request, 'build_opener', return_value=Client()):
                with self.assertRaisesRegex(RuntimeError, 'not awaiting'):
                    init.main()
            self.assertFalse((folder / '.last-used').exists())

    def test_failed_upload_does_not_rotate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'FAIG-a.lic').write_text('license')
            config = folder / 'setup.json'
            config.write_text(json.dumps({'email': 'e', 'username': 'u', 'password': 'p', 'organization_name': 'o'}))
            config.chmod(0o600)
            class Client:
                def open(self, request, timeout):
                    if request.full_url.endswith('/setup-status'):
                        return Reply({'needs_setup': True})
                    if request.full_url.endswith('/setup'):
                        return Reply({'csrf_token': 'token'})
                    raise OSError('connection lost')
            argv = ['initialize.py', '--url', 'https://lab.example', '--setup-file', str(config), '--licenses', str(folder)]
            with patch.object(init.sys, 'argv', argv), patch.object(init.urllib.request, 'build_opener', return_value=Client()):
                with self.assertRaisesRegex(RuntimeError, 'result is unknown'):
                    init.main()
            self.assertFalse((folder / '.last-used').exists())


if __name__ == '__main__':
    unittest.main()
