"""FortiAIGate 8.0.2 lab management service (instructor page at /manage/).

Adapted from the undeployed instructor-management/ prototype. Standard library
only, so it runs on the stock python image with code from a ConfigMap.

Served behind the lab login gateway: nginx strips the /manage prefix, so this
process sees "/", "/api/...", "/app.js". Every request except /healthz must
carry the gateway's signed X-Lab-* headers; they are forwarded to the gateway
auth service, which verifies the signature and makes a live FAIG admin call.
This pod holds no FAIG cookies, passwords, signing key or Kubernetes token.

Current scope: catalog preview from the rendered catalog view, saved scenario
selection, a request journal, and one FAIG action: "models" adds or re-prices
the selected scenarios' models (plus pass-model) on their FAIG provider while
keeping every other model and credential. It runs with the requesting
instructor's own FAIG session through the gateway broker: this service sends
its caller token plus the instructor's session handle (X-Lab-Session), never a
password or FAIG cookie. Student batches are still recorded as "blocked".

Environment:
  LAB_MANAGEMENT_PORT     listen port (default 8080)
  LAB_MANAGEMENT_DB       SQLite journal path (default /data/lab-management.sqlite3)
  LAB_CATALOG_DIR         directory with catalog-student.json (default /catalog)
  LAB_AUTH_URL            gateway auth service base URL (required)
  LAB_PUBLIC_ORIGIN       optional exact browser origin for POSTs; when empty,
                          the origin must match X-Forwarded-Proto/-Host set by nginx
  LAB_STATIC_DIR          directory with index.html, app.js, style.css (default: this file's dir)
  LAB_CALLER_TOKEN_FILE   bearer token for gateway broker calls (optional; FAIG actions need it)
"""
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = int(os.environ.get('LAB_MANAGEMENT_PORT', '8080'))
DB = os.environ.get('LAB_MANAGEMENT_DB', '/data/lab-management.sqlite3')
CATALOG_DIR = Path(os.environ.get('LAB_CATALOG_DIR', '/catalog'))
AUTH_URL = os.environ.get('LAB_AUTH_URL', '').rstrip('/')
PUBLIC_ORIGIN = os.environ.get('LAB_PUBLIC_ORIGIN', '').rstrip('/')
STATIC_DIR = Path(os.environ.get('LAB_STATIC_DIR', Path(__file__).resolve().parent))
CALLER_TOKEN_FILE = os.environ.get('LAB_CALLER_TOKEN_FILE', '/etc/lab-management/caller/token')
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
    status, detail = (('queued', 'Waiting to run.') if kind in EXECUTABLE
                      else ('blocked', 'FAIG executor not connected yet; no changes were made.'))
    with db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                   (job, kind, actor, int(time.time()), status, json.dumps(clean), detail))
    return job


def set_job(db, job, status, detail):
    with db:
        db.execute('UPDATE jobs SET status=?, detail=? WHERE id=?', (status, detail, job))


def interrupt_unfinished(db):
    """After a restart the instructor's session handle is gone: jobs cannot resume by themselves."""
    with db:
        db.execute("UPDATE jobs SET status='interrupted', detail='Service restarted; sign in and request again.' "
                   "WHERE status IN ('queued', 'running')")


# ---------------------------------------------------------------- gateway broker

class SessionLost(Exception):
    """The instructor's session or FAIG session is gone; they must sign in again."""


class UnknownOutcome(Exception):
    """The call may or may not have taken effect; re-read state before any retry."""


class BrokerError(Exception):
    pass


def caller_token():
    try:
        return Path(CALLER_TOKEN_FILE).read_text().strip()
    except OSError:
        return ''


def broker(handle, method, path, body=None):
    """One allowlisted FAIG call with the instructor's session; returns the FAIG JSON body."""
    token = caller_token()
    if not token or not AUTH_URL:
        raise BrokerError('broker not configured (caller token missing); redeploy the gateway, then lab management')
    if not handle:
        raise SessionLost('no session handle')
    payload = json.dumps({'method': method, 'path': path, 'body': body}).encode()
    request = urllib.request.Request(AUTH_URL + '/_lab/internal/admin/faig', data=payload, method='POST', headers={
        'Authorization': 'Bearer ' + token, 'X-Lab-Session': handle, 'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=60) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SessionLost('sign in again') from None
        if exc.code == 504:
            raise UnknownOutcome(f'{method} {path}: FAIG did not answer') from None
        raise BrokerError(f'{method} {path}: broker refused (HTTP {exc.code})') from None
    except (OSError, ValueError) as exc:
        raise UnknownOutcome(f'{method} {path}: {type(exc).__name__}') from None
    if reply.get('status') != 200:
        detail = reply.get('body') or {}
        message = detail.get('error') or detail.get('detail') or '' if isinstance(detail, dict) else ''
        raise BrokerError(f'{method} {path}: FAIG returned HTTP {reply.get("status")} {message}'.strip())
    return reply.get('body')


# ---------------------------------------------------------------- models job

COST_FIELDS = {'input': 'customInputCost', 'output': 'customOutputCost',
               'cache_read': 'customCacheReadCost', 'cache_write': 'customCacheWriteCost'}
MODEL_FIELDS = ('uuid', 'modelId', 'publicName', 'enabled', 'isCustom', 'description', 'customizedCost',
                'customInputCost', 'customOutputCost', 'customCacheReadCost', 'customCacheWriteCost')


def api_number(value):
    """Catalog decimal string -> JSON number FAIG accepts (int when integral)."""
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f'invalid price {value!r}') from None
    return int(number) if number == number.to_integral_value() else float(number)


def cost_fields(prices):
    fields = {COST_FIELDS[k]: api_number((prices or {}).get(k)) for k in COST_FIELDS}
    fields['customizedCost'] = any(v is not None for v in fields.values())
    return fields


def load_faig_view(directory=None):
    path = Path(directory or CATALOG_DIR) / 'catalog-faig.json'
    view = json.loads(path.read_text())
    if view.get('view') != 'faig':
        raise ValueError('catalog-faig.json is not a FAIG view')
    return view


def desired_models(view, scenario_ids):
    """{provider: {modelId: {'publicName', costs...}}} for pass-model plus the selected scenarios."""
    wanted = {}
    models = [view.get('platform', {}).get('passthrough_model')]
    for item in view.get('items', []):
        if item['id'] in scenario_ids:
            models += item.get('models', [])
    missing = set(scenario_ids) - {item['id'] for item in view.get('items', [])}
    if missing:
        raise ValueError('selected scenarios missing from the catalog: ' + ', '.join(sorted(missing)))
    for model in filter(None, models):
        entry = {'publicName': model['public_name'], **cost_fields(model.get('prices'))}
        previous = wanted.setdefault(model['provider'], {}).get(model['backend_alias'])
        if previous and previous != entry:
            raise ValueError(f'conflicting catalog definitions for {model["backend_alias"]}')
        wanted[model['provider']][model['backend_alias']] = entry
    return wanted


def model_changes(provider, wanted):
    """(missing modelIds, {modelId: {field: (old, new)}}) needed to match the catalog."""
    present = {m['modelId']: m for m in provider.get('models', [])}
    add = sorted(set(wanted) - set(present))
    reprice = {}
    for model_id, entry in wanted.items():
        if model_id in present:
            diff = {f: (present[model_id].get(f), v) for f, v in entry.items()
                    if f != 'publicName' and present[model_id].get(f) != v}
            if diff:
                reprice[model_id] = diff
    return add, reprice


def provider_update(provider, wanted):
    """Full provider PUT body (as the FAIG GUI sends it): every existing model and stored
    credential is kept (credentials by ID only, no secret), catalog prices are applied and
    missing catalog models are appended."""
    models = []
    for model in provider.get('models', []):
        updated = {f: model.get(f) for f in MODEL_FIELDS}
        if model['modelId'] in wanted:
            updated.update({k: v for k, v in wanted[model['modelId']].items() if k != 'publicName'})
        models.append(updated)
    for model_id in sorted(set(wanted) - {m['modelId'] for m in provider.get('models', [])}):
        entry = wanted[model_id]
        models.append({'modelId': model_id, 'publicName': entry['publicName'], 'enabled': True, 'isCustom': True,
                       'description': '', **{k: v for k, v in entry.items() if k != 'publicName'}})
    return {'providerId': provider['providerId'], 'platform': provider['platform'], 'name': provider['name'],
            'endpoint': provider['endpoint'], 'description': provider.get('description'),
            'autoSyncNewModels': provider.get('autoSyncNewModels', False),
            'apiKeys': [{'id': k['id'], 'name': k['name'], 'description': k.get('description'),
                         'enabled': k.get('enabled', True), 'weight': k.get('weight', 1)}
                        for k in provider.get('apiKeys', [])],
            'models': models, 'updatedAt': provider['updatedAt']}


def check_saved(before, after, wanted):
    """Problems with a saved provider: lost models or credentials, or catalog prices not applied."""
    problems = []
    kept = {m['modelId'] for m in before.get('models', [])} - {m['modelId'] for m in after.get('models', [])}
    if kept:
        problems.append('models disappeared: ' + ', '.join(sorted(kept)))
    if [k['id'] for k in after.get('apiKeys', [])] != [k['id'] for k in before.get('apiKeys', [])]:
        problems.append('stored credentials changed')
    add, reprice = model_changes(after, wanted)
    if add or reprice:
        problems.append('catalog prices or models not applied: ' + ', '.join(sorted(set(add) | set(reprice))))
    return problems


def run_models_job(call, view, scenario_ids, log):
    """Apply catalog models and prices with `call(method, path, body)`; returns summary lines."""
    for provider_id, wanted in sorted(desired_models(view, scenario_ids).items()):
        path = '/api/v1/admin/ai-providers/' + urllib.parse.quote(provider_id, safe='')
        before = call('GET', path)
        add, reprice = model_changes(before, wanted)
        if not add and not reprice:
            log(f'{provider_id}: {len(wanted)} catalog model(s) already present with catalog prices; no change.')
            continue
        log(f'{provider_id}: add {", ".join(add) or "none"}; re-price {", ".join(sorted(reprice)) or "none"}.')
        try:
            call('PUT', path, provider_update(before, wanted))
        except UnknownOutcome:
            log(f'{provider_id}: save outcome unknown; re-reading provider.')
        after = call('GET', path)
        problems = check_saved(before, after, wanted)
        if problems:
            raise BrokerError(f'{provider_id}: ' + '; '.join(problems))
        log(f'{provider_id}: saved and verified ({len(after.get("models", []))} models, credentials unchanged).')


EXECUTABLE = {'models'}
_job_lock = threading.Lock()


def execute(job, kind, request, handle, db_path=None):
    """Run one job in a worker thread. The handle lives only in memory for this run."""
    lines = []
    with _job_lock, connect(db_path) as db:
        def log(line):
            lines.append(line)
            set_job(db, job, 'running', '\n'.join(lines))
        try:
            set_job(db, job, 'running', 'Started.')
            if kind == 'models':
                run_models_job(lambda m, p, b=None: broker(handle, m, p, b), load_faig_view(),
                               set(request['scenarios']), log)
            set_job(db, job, 'done', '\n'.join(lines) or 'Done.')
        except SessionLost:
            set_job(db, job, 'needs-sign-in', '\n'.join(lines + ['Your FAIG session ended; sign in again and re-run.']))
        except UnknownOutcome as exc:
            set_job(db, job, 'failed', '\n'.join(lines + [f'{exc}. Re-run after checking FAIG; nothing is retried blindly.']))
        except (BrokerError, ValueError, KeyError, OSError) as exc:
            set_job(db, job, 'failed', '\n'.join(lines + [str(exc)]))


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
                    'selected': selected(db), 'jobs': jobs(db), 'faig_actions': bool(caller_token()),
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
                    kind = path.rsplit('/', 1)[-1]
                    if kind in EXECUTABLE and not caller_token():
                        return self.reply(409, {'error': 'FAIG actions are not configured yet (no broker caller token).'})
                    job = create_job(db, kind, self.headers['X-Lab-User'], body)
                    status = db.execute('SELECT status, request FROM jobs WHERE id=?', (job,)).fetchone()
                    if kind in EXECUTABLE:
                        threading.Thread(target=execute, daemon=True,
                                         args=(job, kind, json.loads(status[1]), self.headers.get('X-Lab-Session', ''))).start()
                    return self.reply(201, {'id': job, 'status': status[0]})
            self.reply(404, {'error': 'not found'})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.reply(400, {'error': str(exc) if isinstance(exc, ValueError) else 'invalid request'})


def main():
    if not AUTH_URL:
        raise SystemExit('LAB_AUTH_URL is required')
    with connect() as db:
        interrupt_unfinished(db)
    _, _, error = load_catalog()
    if error:
        print(error, flush=True)  # start anyway; the page reports it
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
