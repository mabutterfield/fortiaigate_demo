import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('student_lab', ROOT / 'student_lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
TEMPLATE = json.loads((ROOT / 'student-template.json').read_text())


class StudentLabTests(unittest.TestCase):
    def test_numbering_and_project_names(self):
        items = lab.expand_template(TEMPLATE, 1, 2)
        self.assertEqual(items[0]['email'], 'student01@fortiai.lab')
        self.assertEqual(items[0]['workspace'], 'student01_workspace')
        self.assertEqual(items[1]['projects'], ['student02_fortistore-injection', 'student02_hr-tool-dlp',
                                                 'student02_resume-tool-injection'])
        self.assertEqual(lab.expand_template(TEMPLATE, 100, 1)[0]['student'], 'student100')

    def test_invalid_template_does_not_generate_duplicate_projects(self):
        with self.assertRaises(ValueError):
            lab.expand_template({**TEMPLATE, 'projects': ['same', 'same']}, 1, 1)
        with self.assertRaises(ValueError):
            lab.expand_template(TEMPLATE, 0, 1)

    def test_provider_bindings_use_distinct_scopes(self):
        provider = {'providerId': 'direct', 'platform': 'custom', 'name': 'direct', 'apiKeys': [{'id': 'key-id'}]}
        workspace, bindings, projects = lab.provider_bindings([provider])
        self.assertEqual(bindings[0]['keyIds'], ['key-id'])
        self.assertTrue(workspace[0]['allKeys'])
        self.assertNotIn('allKeys', projects[0])
        with self.assertRaises(ValueError):
            lab.provider_bindings([{**provider, 'apiKeys': []}])

    def test_users_are_read_across_pages(self):
        class Paginated:
            def call(self, method, path):
                if 'offset=0&' in path:
                    return {'items': [{'id': str(i)} for i in range(100)], 'total': 101}
                self.assert_path = path
                return {'items': [{'id': '100'}], 'total': 101}
        client = Paginated()
        self.assertEqual(len(lab.list_users(client)), 101)
        self.assertIn('offset=100&', client.assert_path)

    def test_collision_stops_before_writes(self):
        plan = lab.expand_template(TEMPLATE, 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            admin = directory / 'admin.json'
            admin.write_text(json.dumps({'username': 'admin', 'password': 'example'}))
            admin.chmod(0o600)
            writes = []
            class FakeClient:
                def __init__(self, origin, insecure): self.csrf = None
                def call(self, method, path, payload=None):
                    if method == 'POST' and path == '/api/v1/login': return {'csrf_token': 'csrf'}
                    if method != 'GET': writes.append((method, path))
                    if path.startswith('/api/v1/admin/users?'): return {'items': [], 'total': 0}
                    if path == '/api/v1/admin/workspaces': return [{'workspaceName': 'student01_workspace'}]
                    if path == '/api/v1/admin/projects': return []
                    if '/ai-providers/' in path: return {'providerId': path.rsplit('/', 1)[-1], 'platform': 'custom', 'name': 'provider', 'apiKeys': [{'id': 'key'}]}
                    raise AssertionError(path)
            args = argparse.Namespace(url='https://lab.example', admin_credentials=admin, credentials_dir=directory, password_file=None, insecure=True)
            with patch.object(lab, 'Client', FakeClient):
                with self.assertRaisesRegex(ValueError, 'Workspace already exists'):
                    lab.apply_plan(args, TEMPLATE, plan)
            self.assertEqual(writes, [])

    def test_apply_existing_student_creates_workspace_and_projects(self):
        plan = lab.expand_template(TEMPLATE, 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            admin, student = directory / 'admin.json', directory / 'student01.json'
            admin.write_text(json.dumps({'username': 'admin', 'password': 'example'}))
            student.write_text(json.dumps({'username': 'student01@fortiai.lab', 'password': 'example'}))
            admin.chmod(0o600)
            student.chmod(0o600)
            writes = []
            class FakeClient:
                def __init__(self, origin, insecure): self.csrf = None
                def call(self, method, path, payload=None):
                    if method == 'POST' and path == '/api/v1/login': return {'csrf_token': 'csrf'}
                    if path.startswith('/api/v1/admin/users?'): return {'items': [{'id': 'student-id', 'email': 'student01@fortiai.lab'}], 'total': 1}
                    if method == 'GET' and path == '/api/v1/admin/workspaces': return []
                    if method == 'GET' and path == '/api/v1/admin/projects':
                        return [entry for route, entry in writes if route == '/api/v1/admin/projects']
                    if '/ai-providers/' in path: return {'providerId': path.rsplit('/', 1)[-1], 'platform': 'custom', 'name': 'provider', 'apiKeys': [{'id': 'key'}]}
                    if method == 'POST' and path == '/api/v1/admin/workspaces':
                        writes.append((path, payload))
                        return {'id': 'workspace-id'}
                    if method == 'POST' and path == '/api/v1/admin/projects':
                        writes.append((path, payload))
                        return {'id': 'project-id'}
                    if path == '/api/v1/me/workspaces': return [{'id': 'workspace-id', 'membershipRole': 'admin'}]
                    raise AssertionError(path)
            args = argparse.Namespace(url='https://lab.example', admin_credentials=admin, credentials_dir=directory, password_file=None, insecure=True)
            with patch.object(lab, 'Client', FakeClient):
                lab.apply_plan(args, TEMPLATE, plan)
            self.assertEqual(writes[0][1]['admins'], [{'id': 'student-id'}])
            self.assertEqual([x[1]['name'] for x in writes[1:]], ['student01_fortistore-injection', 'student01_hr-tool-dlp',
                                                       'student01_resume-tool-injection'])
            self.assertTrue(all(x[1]['workspaceId'] == 'workspace-id' for x in writes[1:]))


if __name__ == '__main__':
    unittest.main()
