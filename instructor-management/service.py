"""Standalone instructor preview and operation journal. No FAIG writes are performed."""
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get('LAB_REPO_ROOT', Path(__file__).resolve().parent.parent))
DB = os.environ.get('INSTRUCTOR_DB', '/data/instructor.sqlite3')
AUTH_URL = os.environ.get('INSTRUCTOR_AUTH_URL', '')
PUBLIC_ORIGIN = os.environ.get('INSTRUCTOR_PUBLIC_ORIGIN', '').rstrip('/')
HEADERS = ('X-Lab-User', 'X-Lab-Student', 'X-Lab-Role', 'X-Lab-Workspace-Id', 'X-Lab-Ts', 'X-Lab-Signature')


def catalog(root=ROOT):
    """Derive the management view from the tracked scenario catalog and profiles."""
    base = root / 'chatbot/scenarios/examples'
    index = json.loads((base / 'catalog.json').read_text())
    mappings = json.loads((root / 'experiments/faig-api-lab/scenario-catalog.json').read_text())['scenarios']
    result = []
    for sid, item in index['scenarios'].items():
        if not item.get('active'):
            continue
        profile_path = (base / item['path']).resolve()
        if not profile_path.is_relative_to(base.resolve()):
            raise ValueError('active scenario outside catalog directory')
        profile = json.loads(profile_path.read_text())
        if profile['id'] != sid or sid not in mappings:
            raise ValueError('scenario ID or compatibility mapping mismatch: ' + sid)
        instruction = (profile_path.parent / profile['instruction_file']).resolve()
        if not instruction.is_relative_to(profile_path.parent):
            raise ValueError('invalid instruction path')
        text = instruction.read_text()
        result.append({'id': sid, 'version': profile['schema_version'], 'title': profile['display_name'],
                       'description': profile.get('description', ''), 'alias': mappings[sid]['model'],
                       'instruction_sha256': hashlib.sha256(text.encode()).hexdigest(),
                       'instruction': text, 'tools': profile.get('mcp', {}).get('required_tools', []),
                       'actions': profile.get('matrix', {}).get('entry_points', []),
                       'sample_prompts': {'clean': profile.get('clean_prompts', []), 'attack': profile.get('attack_prompts', [])},
                       'tests': profile.get('validation', {}).get('cases', [])})
    return result


def connect(path=None):
    db = sqlite3.connect(path or DB, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS selection (id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL, created INTEGER NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, detail TEXT NOT NULL)')
    db.commit()
    return db


def select(db, ids, known):
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids) or len(set(ids)) != len(ids) or not set(ids) <= known:
        raise ValueError('invalid scenario selection')
    with db:
        db.execute('DELETE FROM selection')
        db.executemany('INSERT INTO selection VALUES (?)', [(x,) for x in ids])


def create_job(db, kind, actor, request):
    # Do not accept arbitrary bodies: journals must never hold passwords or keys.
    if kind == 'deploy':
        if request != {}:
            raise ValueError('unexpected deployment fields')
        clean = {'scenarios': [r[0] for r in db.execute('SELECT id FROM selection ORDER BY id')]}
        if not clean['scenarios']:
            raise ValueError('select at least one scenario')
    elif kind == 'students':
        if set(request) != {'count', 'start_index', 'prepopulate'} or type(request['count']) is not int or type(request['start_index']) is not int or type(request['prepopulate']) is not bool or not 1 <= request['count'] <= 100 or not 1 <= request['start_index'] <= 99999:
            raise ValueError('invalid student batch')
        clean = dict(request, scenarios=[r[0] for r in db.execute('SELECT id FROM selection ORDER BY id')])
        if not clean['scenarios']:
            raise ValueError('select at least one scenario')
    else:
        raise ValueError('unknown operation')
    job = str(uuid.uuid4())
    with db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)', (job, kind, actor, int(time.time()), 'blocked', json.dumps(clean), 'Experimental FAIG execution bridge is not connected; no changes were made.'))
    return job


def authorize(headers):
    """Gateway checks the signed identity AND makes a live FAIG admin request."""
    if not AUTH_URL or headers.get('X-Lab-Role') != 'admin':
        return False
    forwarded = {k: headers.get(k, '') for k in HEADERS}
    if not all(forwarded[k] for k in ('X-Lab-User', 'X-Lab-Role', 'X-Lab-Ts', 'X-Lab-Signature')):
        return False
    try:
        request = urllib.request.Request(AUTH_URL.rstrip('/') + '/_lab/internal/admin/students', headers=forwarded)
        # Never follow an authentication redirect to an untrusted destination.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=5) as response:
            return response.status == 200 and isinstance(json.load(response).get('items'), list)
    except (OSError, ValueError, urllib.error.URLError):
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # no request headers or bodies in logs

    def reply(self, status, data, content_type='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if not authorize(self.headers):
            self.reply(403, {'error': 'Live FAIG administrator session required'})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            return self.reply(200, {'status': 'ok'})
        if not self.allowed():
            return
        if path in ('/', '/app.js', '/style.css'):
            name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
            return self.reply(200, (Path(__file__).parent / name).read_bytes(), {'index.html':'text/html; charset=utf-8', 'app.js':'text/javascript; charset=utf-8', 'style.css':'text/css; charset=utf-8'}[name])
        with connect() as db:
            if path == '/api/state':
                jobs = [dict(zip(('id','kind','actor','created','status','request','detail'), row)) for row in db.execute('SELECT * FROM jobs ORDER BY created DESC, rowid DESC LIMIT 100')]
                return self.reply(200, {'catalog': catalog(), 'selected': [r[0] for r in db.execute('SELECT id FROM selection ORDER BY id')], 'jobs': jobs, 'auto_approval': {'enabled': False, 'status': 'unavailable'}})
        self.reply(404, {'error': 'not found'})

    def do_POST(self):
        if not self.allowed():
            return
        if not PUBLIC_ORIGIN or self.headers.get('Origin') != PUBLIC_ORIGIN or self.headers.get('X-Instructor-Request') != '1':
            return self.reply(403, {'error': 'invalid request origin'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192 or self.headers.get_content_type() != 'application/json':
                raise ValueError('invalid request')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('invalid request')
            with connect() as db:
                if self.path == '/api/selection' and set(body) == {'ids'}:
                    select(db, body['ids'], {s['id'] for s in catalog()})
                    return self.reply(200, {'saved': True})
                if self.path in ('/api/jobs/deploy', '/api/jobs/students'):
                    job = create_job(db, self.path.rsplit('/', 1)[-1], self.headers['X-Lab-User'], body)
                    return self.reply(201, {'id': job, 'status': 'blocked'})
            self.reply(404, {'error': 'not found'})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.reply(400, {'error': 'invalid request'})


if __name__ == '__main__':
    if not AUTH_URL or not PUBLIC_ORIGIN:
        raise SystemExit('INSTRUCTOR_AUTH_URL and INSTRUCTOR_PUBLIC_ORIGIN are required')
    connect().close()
    catalog()
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
