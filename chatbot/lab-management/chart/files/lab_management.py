"""FortiAIGate 8.0.2 lab management service (instructor page at /manage/).

Adapted from the undeployed instructor-management/ prototype. Standard library
only, so it runs on the stock python image with code from a ConfigMap.

Served behind the lab login gateway: nginx strips the /manage prefix, so this
process sees "/", "/api/...", "/app.js". Every request except /healthz must
carry the gateway's signed X-Lab-* headers; they are forwarded to the gateway
auth service, which verifies the signature and makes a live FAIG admin call.
This pod holds no FAIG cookies, passwords, signing key or Kubernetes token.

Current scope: catalog preview from the rendered catalog view, saved scenario
selection, and a request journal. Requests are recorded as "blocked": there is
no FAIG executor yet, so nothing is created, approved or changed in FAIG.

Environment:
  LAB_MANAGEMENT_PORT     listen port (default 8080)
  LAB_MANAGEMENT_DB       SQLite journal path (default /data/lab-management.sqlite3)
  LAB_CATALOG_DIR         directory with catalog-student.json (default /catalog)
  LAB_AUTH_URL            gateway auth service base URL (required)
  LAB_PUBLIC_ORIGIN       optional exact browser origin for POSTs; when empty,
                          the origin must match X-Forwarded-Proto/-Host set by nginx
  LAB_STATIC_DIR          directory with index.html, app.js, style.css (default: this file's dir)
"""
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = int(os.environ.get('LAB_MANAGEMENT_PORT', '8080'))
DB = os.environ.get('LAB_MANAGEMENT_DB', '/data/lab-management.sqlite3')
CATALOG_DIR = Path(os.environ.get('LAB_CATALOG_DIR', '/catalog'))
AUTH_URL = os.environ.get('LAB_AUTH_URL', '').rstrip('/')
PUBLIC_ORIGIN = os.environ.get('LAB_PUBLIC_ORIGIN', '').rstrip('/')
STATIC_DIR = Path(os.environ.get('LAB_STATIC_DIR', Path(__file__).resolve().parent))
HEADERS = ('X-Lab-User', 'X-Lab-Student', 'X-Lab-Role', 'X-Lab-Workspace-Id', 'X-Lab-Ts', 'X-Lab-Signature')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}
AUTH_CACHE_SECONDS = 20
_auth_cache = {}
_auth_lock = threading.Lock()


# ---------------------------------------------------------------- catalog

def load_catalog(directory=None):
    """Return (items, platform, error). A missing or invalid view is reported, not raised."""
    path = Path(directory or CATALOG_DIR) / 'catalog-student.json'
    try:
        view = json.loads(path.read_text())
        if view.get('view') != 'student' or not isinstance(view.get('items'), list):
            raise ValueError('not a student catalog view')
        items = [preview(item) for item in view['items']]
        return items, view.get('platform') or {}, None
    except FileNotFoundError:
        return [], {}, 'catalog unavailable: catalog-student.json not found'
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [], {}, f'catalog unavailable: {exc}'


def preview(item):
    """Instructor preview of one scenario; no backend instruction text."""
    return {
        'id': item['id'],
        'version': item.get('scenario_version', ''),
        'content_hash': item.get('content_hash', ''),
        'title': item.get('display_name', item['id']),
        'description': item.get('description', ''),
        'models': [{'id': m.get('id'), 'public_name': m.get('public_name'), 'prices': m.get('prices')}
                   for m in item.get('models', [])],
        'tools': item.get('tools', []),
        'actions': [{'id': a.get('id'), 'label': a.get('display_name', a.get('id')),
                     'expected_behavior': a.get('expected_behavior', '')} for a in item.get('actions', [])],
        'prompts': item.get('prompts', {}),
        'tests': [{'id': t.get('id'), 'action': t.get('action'), 'prompt_ref': t.get('prompt_ref'),
                   'expect': t.get('expect', {})} for t in item.get('tests', [])],
    }


# ---------------------------------------------------------------- journal

def connect(path=None):
    db = sqlite3.connect(path or DB, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS selection (id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL, '
               'created INTEGER NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, detail TEXT NOT NULL)')
    db.commit()
    return db


def selected(db):
    return [r[0] for r in db.execute('SELECT id FROM selection ORDER BY id')]


def select(db, ids, known):
    if (not isinstance(ids, list) or any(not isinstance(x, str) for x in ids)
            or len(set(ids)) != len(ids) or not set(ids) <= known):
        raise ValueError('invalid scenario selection')
    with db:
        db.execute('DELETE FROM selection')
        db.executemany('INSERT INTO selection VALUES (?)', [(x,) for x in ids])


def create_job(db, kind, actor, request):
    # Fixed, non-secret fields only: the journal must never hold passwords or keys.
    if kind == 'models':
        if request != {}:
            raise ValueError('unexpected fields')
        clean = {'scenarios': selected(db)}
    elif kind == 'students':
        if (set(request) != {'count', 'start_index', 'prepopulate'}
                or type(request['count']) is not int or type(request['start_index']) is not int
                or type(request['prepopulate']) is not bool
                or not 1 <= request['count'] <= 100 or not 1 <= request['start_index'] <= 99):
            raise ValueError('invalid student batch')
        clean = dict(request, scenarios=selected(db))
    else:
        raise ValueError('unknown operation')
    if not clean['scenarios']:
        raise ValueError('select at least one scenario')
    job = str(uuid.uuid4())
    with db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                   (job, kind, actor, int(time.time()), 'blocked', json.dumps(clean),
                    'FAIG executor not connected yet; no changes were made.'))
    return job


def jobs(db):
    cols = ('id', 'kind', 'actor', 'created', 'status', 'request', 'detail')
    return [dict(zip(cols, row)) for row in
            db.execute('SELECT * FROM jobs ORDER BY created DESC, rowid DESC LIMIT 100')]


# ---------------------------------------------------------------- authorization

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # never follow a redirect to another destination


def authorize(headers, now=None):
    """Admin only: the gateway verifies the signed identity and makes a live FAIG admin call."""
    if not AUTH_URL or headers.get('X-Lab-Role') != 'admin':
        return False
    forwarded = {k: headers.get(k, '') for k in HEADERS}
    if not all(forwarded[k] for k in ('X-Lab-User', 'X-Lab-Role', 'X-Lab-Ts', 'X-Lab-Signature')):
        return False
    now = time.time() if now is None else now
    cache_key = (forwarded['X-Lab-User'], forwarded['X-Lab-Ts'], forwarded['X-Lab-Signature'])
    with _auth_lock:
        for key, expires in list(_auth_cache.items()):
            if expires < now:
                del _auth_cache[key]
        if cache_key in _auth_cache:
            return True
    try:
        request = urllib.request.Request(AUTH_URL + '/_lab/internal/admin/students', headers=forwarded)
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=10) as response:
            ok = response.status == 200 and isinstance(json.load(response).get('items'), list)
    except (OSError, ValueError, urllib.error.URLError):
        ok = False
    if ok:
        with _auth_lock:
            _auth_cache[cache_key] = now + AUTH_CACHE_SECONDS
    return ok


def origin_ok(headers):
    origin = headers.get('Origin', '')
    if PUBLIC_ORIGIN:
        expected = PUBLIC_ORIGIN
    else:
        host = headers.get('X-Forwarded-Host', '')
        proto = headers.get('X-Forwarded-Proto', '')
        if not host or proto not in ('http', 'https'):
            return False
        expected = f'{proto}://{host}'
    return bool(origin) and origin == expected and headers.get('X-Lab-Request') == '1'


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = 'lab-management'

    def log_message(self, *args):
        pass  # never log request headers or bodies

    def reply(self, status, data, content_type='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if not authorize(self.headers):
            self.reply(403, {'error': 'Instructor (FAIG administrator) sign-in required'})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            return self.reply(200, {'status': 'ok'})
        if not self.allowed():
            return
        if path in STATIC:
            name, content_type = STATIC[path]
            return self.reply(200, (STATIC_DIR / name).read_bytes(), content_type)
        if path == '/api/state':
            items, platform, error = load_catalog()
            with connect() as db:
                return self.reply(200, {
                    'user': self.headers.get('X-Lab-User', ''),
                    'catalog': items, 'catalog_error': error,
                    'pricing': {k: platform.get(k) for k in ('currency', 'unit', 'pricing_note')},
                    'selected': selected(db), 'jobs': jobs(db),
                    'auto_approval': {'enabled': False, 'state': 'unavailable',
                                      'detail': 'Auto-approval is not connected yet.'}})
        self.reply(404, {'error': 'not found'})

    def do_POST(self):
        if not self.allowed():
            return
        if not origin_ok(self.headers):
            return self.reply(403, {'error': 'invalid request origin'})
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192 or self.headers.get_content_type() != 'application/json':
                raise ValueError('invalid request')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('invalid request')
            with connect() as db:
                if path == '/api/selection' and set(body) == {'ids'}:
                    items, _, error = load_catalog()
                    if error:
                        return self.reply(409, {'error': error})
                    select(db, body['ids'], {s['id'] for s in items})
                    return self.reply(200, {'saved': True})
                if path in ('/api/jobs/models', '/api/jobs/students'):
                    job = create_job(db, path.rsplit('/', 1)[-1], self.headers['X-Lab-User'], body)
                    return self.reply(201, {'id': job, 'status': 'blocked'})
            self.reply(404, {'error': 'not found'})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.reply(400, {'error': str(exc) if isinstance(exc, ValueError) else 'invalid request'})


def main():
    if not AUTH_URL:
        raise SystemExit('LAB_AUTH_URL is required')
    connect().close()
    _, _, error = load_catalog()
    if error:
        print(error, flush=True)  # start anyway; the page reports it
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
