"""FortiAIGate 8.0.2 lab management service (instructor page at /manage/).

Adapted from the undeployed instructor-management/ prototype (removed 2026-11-23;
kept at tag faig_8.0.2_gui_experiment). Standard library
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
password or FAIG cookie.

"students" creates or reconciles studentNN accounts, workspaces and scenario
projects through the gateway (lab_auth), which generates or applies the
password and keeps it in the lab-credentials Secret. A password typed by the
instructor passes through this process in memory only; the journal records the
password mode, never the value.

"prepopulate" (or "students" with prepopulate on) creates each student's
detectors, guardrails, policies and one key per selected scenario action plus a
passthrough key, from the catalog. lab_auth signs in as the student with the
stored password, approves each layer with the instructor's session and saves
new key secrets in the lab-keys Secret.

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
import re
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
# Change 2026-11-20: GUI-only install (no GPU, no license): FAIG does not inspect traffic.
GUI_ONLY = os.environ.get('LAB_GUI_ONLY', 'false').strip().lower() == 'true'
HEADERS = ('X-Lab-User', 'X-Lab-Student', 'X-Lab-Role', 'X-Lab-Workspace-Id', 'X-Lab-Ts', 'X-Lab-Signature')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/share.html': ('share.html', 'text/html; charset=utf-8'),
          '/share.js': ('share.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}
# Change 2026-11-23: 'file' = instructor student password file (resolved by lab_auth; no value sent).
PASSWORD_MODES = ('generated', 'shared', 'base', 'file')
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
    # Change 2026-11-20: instructor preferences (auto-approval on/off and hours); never secrets.
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    # Change 2026-11-20: auto-approval history copied from lab_auth (names and actions only).
    db.execute('CREATE TABLE IF NOT EXISTS approvals (boot TEXT NOT NULL, seq INTEGER NOT NULL, at INTEGER NOT NULL, '
               'student TEXT NOT NULL, submitted_by TEXT NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL, '
               'change TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL, approved_by TEXT NOT NULL, '
               'item_id TEXT NOT NULL, PRIMARY KEY (boot, seq))')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL, '
               'created INTEGER NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, detail TEXT NOT NULL)')
    db.commit()
    return db


def selected(db):
    return [r[0] for r in db.execute('SELECT id FROM selection ORDER BY id')]


# Change 2026-11-20: auto-approval preference. On by default (owner); it runs in lab_auth under the
# instructor's own FAIG session, so it starts when an instructor opens this page while it is stopped.
AUTO_APPROVAL_DEFAULTS = {'enabled': True, 'hours': 8}
AUTO_APPROVAL_MAX_HOURS = 8


def student_password_file_summary(handle):
    """{configured, kind, students?} from lab_auth; never values (Change 2026-11-23)."""
    try:
        return gateway(handle, '/_lab/internal/admin/student-password-file', timeout=15)
    except (SessionLost, BrokerError, UnknownOutcome) as exc:
        return {'configured': False, 'error': str(exc)}


def auto_approval_preference(db):
    rows = dict(db.execute("SELECT key, value FROM settings WHERE key IN ('auto_approval_enabled', 'auto_approval_hours')"))
    pref = dict(AUTO_APPROVAL_DEFAULTS)
    if 'auto_approval_enabled' in rows:
        pref['enabled'] = rows['auto_approval_enabled'] == '1'
    if 'auto_approval_hours' in rows:
        pref['hours'] = float(rows['auto_approval_hours'])
    return pref


APPROVAL_FIELDS = ('at', 'student', 'submitted_by', 'type', 'name', 'change', 'outcome', 'detail', 'approved_by', 'item_id')


def store_approvals(db, boot, items):
    """Insert history entries from lab_auth (idempotent per boot/seq); returns the number added."""
    rows = []
    for e in items:
        if not isinstance(e, dict) or not isinstance(e.get('seq'), int):
            continue
        rows.append((str(boot), e['seq'], int(e.get('at') or 0), str(e.get('student', ''))[:120],
                     str(e.get('submitted_by', ''))[:200], str(e.get('type', ''))[:40], str(e.get('name', ''))[:200],
                     str(e.get('change', ''))[:40], str(e.get('outcome', ''))[:20], str(e.get('detail', ''))[:200],
                     str(e.get('by', ''))[:200], str(e.get('item_id', ''))[:80]))
    with db:
        before = db.total_changes
        db.executemany('INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        return db.total_changes - before


def sync_approvals(db, handle, status):
    """Copy entries newer than our cursor from lab_auth; tolerate any failure (the list is best effort)."""
    boot, latest = status.get('boot'), status.get('history_seq')
    if not boot or not isinstance(latest, int):
        return 0
    cursor = dict(db.execute("SELECT key, value FROM settings WHERE key IN ('approvals_boot', 'approvals_seq')"))
    after = int(cursor.get('approvals_seq', '0')) if cursor.get('approvals_boot') == boot else 0
    if cursor.get('approvals_boot') == boot and after >= latest:
        return 0
    try:
        page = gateway(handle, '/_lab/internal/admin/auto-approve/history?boot=' + boot + '&after=' + str(after), timeout=15)
    except (SessionLost, BrokerError, UnknownOutcome):
        return 0
    added = store_approvals(db, page.get('boot', boot), page.get('items', []))
    with db:
        db.executemany('INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       [('approvals_boot', str(page.get('boot', boot))), ('approvals_seq', str(page.get('history_seq', latest)))])
    return added


def list_approvals(db, student='', limit=200):
    query, args = 'SELECT ' + ', '.join(APPROVAL_FIELDS) + ' FROM approvals', []
    if student:
        query, args = query + ' WHERE student = ?', [student]
    query += ' ORDER BY at DESC, seq DESC LIMIT ?'
    return [dict(zip(APPROVAL_FIELDS, row)) for row in db.execute(query, args + [max(1, min(int(limit), 1000))])]


def save_auto_approval_preference(db, enabled, hours):
    if not isinstance(enabled, bool):
        raise ValueError('enabled must be true or false')
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not 0.25 <= hours <= AUTO_APPROVAL_MAX_HOURS:
        raise ValueError(f'hours must be between 0.25 and {AUTO_APPROVAL_MAX_HOURS}')
    with db:
        db.executemany('INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       [('auto_approval_enabled', '1' if enabled else '0'), ('auto_approval_hours', repr(float(hours)))])


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
        if (set(request) != {'count', 'start_index', 'prepopulate', 'password_mode'}
                or type(request['count']) is not int or type(request['start_index']) is not int
                or type(request['prepopulate']) is not bool or request['password_mode'] not in PASSWORD_MODES
                or not 1 <= request['count'] <= 99 or not 1 <= request['start_index'] <= 99
                or request['start_index'] + request['count'] - 1 > 99):
            raise ValueError('invalid student batch')
        clean = dict(request, scenarios=selected(db))
    elif kind == 'prepopulate':
        # Change 2026-11-20: optional "restore" rotates prepopulated keys whose values were lost.
        request = dict(request)
        restore = request.pop('restore', False)
        if type(restore) is not bool:
            raise ValueError('invalid prepopulation batch')
        if (set(request) != {'count', 'start_index'} or type(request['count']) is not int
                or type(request['start_index']) is not int or not 1 <= request['count'] <= 99
                or not 1 <= request['start_index'] <= 99 or request['start_index'] + request['count'] - 1 > 99):
            raise ValueError('invalid prepopulation batch')
        clean = dict(request, restore=restore, scenarios=selected(db))
    elif kind == 'password':
        # Change 2026-11-20: student password reset moved here from the chatbot Admin tab.
        if (set(request) != {'number', 'password_mode'} or type(request['number']) is not int
                or not 1 <= request['number'] <= 99 or request['password_mode'] not in PASSWORD_MODES):
            raise ValueError('invalid password reset')
        clean = dict(request)
    else:
        raise ValueError('unknown operation')
    if kind != 'password' and not clean['scenarios']:
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


def gateway(handle, path, body=None, timeout=60):
    """Call a lab_auth broker endpoint as this caller for the instructor's session handle."""
    token = caller_token()
    if not token or not AUTH_URL:
        raise BrokerError('broker not configured (caller token missing); redeploy the gateway, then lab management')
    if not handle:
        raise SessionLost('no session handle')
    headers = {'Authorization': 'Bearer ' + token, 'X-Lab-Session': handle}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    request = urllib.request.Request(AUTH_URL + path, data=data, method='POST' if data else 'GET', headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            error = json.load(exc).get('error', '')
        except (ValueError, AttributeError):
            error = ''
        if exc.code == 401:
            raise SessionLost(error or 'sign in again') from None
        if exc.code == 504:
            raise UnknownOutcome(error or 'gateway timed out') from None
        raise BrokerError(error or f'gateway refused (HTTP {exc.code})') from None
    except (OSError, ValueError) as exc:
        raise UnknownOutcome(f'{type(exc).__name__}') from None


def broker(handle, method, path, body=None):
    """One allowlisted FAIG call with the instructor's session; returns the FAIG JSON body."""
    try:
        reply = gateway(handle, '/_lab/internal/admin/faig', {'method': method, 'path': path, 'body': body})
    except UnknownOutcome as exc:
        raise UnknownOutcome(f'{method} {path}: {exc}') from None
    except BrokerError as exc:
        raise BrokerError(f'{method} {path}: {exc}') from None
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


def catalog_providers(view, scenario_ids):
    return sorted(desired_models(view, scenario_ids))


def run_students_job(ensure, view, request, password, log):
    """Create or reconcile each student in turn with `ensure(body)` (the gateway endpoint)."""
    providers = catalog_providers(view, set(request['scenarios']))
    policy = {'mode': request['password_mode']}
    if request['password_mode'] in ('shared', 'base'):  # Change 2026-11-23: 'file' sends no value
        policy['value'] = password
    failures = 0
    for number in range(request['start_index'], request['start_index'] + request['count']):
        student = f'student{number:02d}'
        try:
            result = ensure({'number': number, 'password': policy, 'providers': providers,
                             'projects': sorted(request['scenarios'])})
        except (BrokerError, UnknownOutcome) as exc:
            failures += 1
            log(f'{student}: FAILED — {exc}')
            continue
        projects = ', '.join(f'{k} {v}' for k, v in sorted(result.get('projects', {}).items())) or 'none'
        log(f'{student}: account {result.get("account")}, password {result.get("password")}, '
            f'workspace {result.get("workspace")}, projects: {projects}; '
            f'{"verified by student sign-in" if result.get("verified") else "NOT verified"}'
            + (f'; {"; ".join(result["notes"])}' if result.get('notes') else ''))
        if not result.get('verified'):
            failures += 1
    if failures:
        raise BrokerError(f'{failures} student(s) need attention; re-run the same batch to reconcile')


def prepopulation_plan(view, scenario_ids, student):
    """Concrete object names and guard definitions for one student, from the FAIG catalog view."""
    platform = view.get('platform', {})
    naming = platform['naming']
    entries = []
    for item in view.get('items', []):
        if item['id'] not in scenario_ids:
            continue
        models = {m['id']: m for m in item.get('models', [])}
        for action in item.get('actions', []):
            model = models[action['model_ref']]
            guard = action['guard']
            fields = {'student': student, 'scenario': item['id'], 'action': action['id']}
            entries.append({
                'scenario': item['id'], 'action': action['id'], 'model': model['backend_alias'],
                'provider': model['provider'],
                'project': naming['project'].format(**fields), 'key': naming['key'].format(**fields),
                'policy': naming['policy'].format(**fields), 'guardrail': naming['guardrail'].format(**fields),
                'guard': {'direction': guard['direction'],
                          'deny_suspicious_characters': bool(guard.get('deny_suspicious_characters')),
                          'builtin_detectors': list(guard.get('builtin_detectors', [])),
                          'detectors': [dict(guard['resolved_detectors'][key],
                                             name=naming['detector'].format(student=student, detector=key))
                                        for key in guard.get('detectors', [])]}})
    plan = {'entries': entries}
    passthrough = platform.get('passthrough_model')
    if passthrough:
        plan['passthrough'] = {'key': naming['passthrough_key'].format(student=student),
                               'model': passthrough['backend_alias'], 'provider': passthrough['provider']}
    return plan


def summarize_prepopulation(student, result):
    parts = [f'{len(result.get("created", []))} created', f'{len(result.get("approved", []))} approved',
             f'{len(result.get("existing", []))} already present', f'{len(result.get("keys_saved", []))} key secrets saved']
    if result.get('keys_missing'):  # Change 2026-11-20: keys deleted in FAIG (informational)
        parts.append('deleted in FAIG, marked missing: ' + ', '.join(result['keys_missing']))
    if result.get('keys_restored'):  # Change 2026-11-20
        parts.append(f'{len(result["keys_restored"])} key(s) restored by rotation: ' + ', '.join(result['keys_restored']))
    line = f'{student}: prepopulated — ' + ', '.join(parts)
    if result.get('skipped'):
        line += '; skipped ' + '; '.join(result['skipped'])
    if result.get('notes'):
        line += '; ' + '; '.join(result['notes'])
    return line


def run_prepopulate_job(prepopulate, view, request, log):
    scenarios = set(request['scenarios'])
    failures = 0
    for number in range(request['start_index'], request['start_index'] + request['count']):
        student = f'student{number:02d}'
        try:
            body = {'number': number, 'plan': prepopulation_plan(view, scenarios, student)}
            if request.get('restore'):
                body['restore'] = True
            result = prepopulate(body)
        except (BrokerError, UnknownOutcome) as exc:
            failures += 1
            log(f'{student}: prepopulation FAILED — {exc}')
            continue
        log(summarize_prepopulation(student, result))
        if result.get('notes'):
            failures += 1
    if failures:
        raise BrokerError(f'{failures} student(s) need attention; re-run the same batch to reconcile')


EXECUTABLE = {'models', 'students', 'prepopulate', 'password'}
_job_lock = threading.Lock()


def execute(job, kind, request, handle, db_path=None, password=None):
    """Run one job in a worker thread. The handle and any password live only in memory for this run."""
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
            elif kind == 'students':
                view = load_faig_view()
                run_students_job(lambda body: gateway(handle, '/_lab/internal/admin/students/ensure', body, timeout=180),
                                 view, request, password, log)
                password = None
                if request.get('prepopulate'):
                    run_prepopulate_job(lambda body: gateway(handle, '/_lab/internal/admin/students/prepopulate', body,
                                                             timeout=600), view, request, log)
            elif kind == 'prepopulate':
                run_prepopulate_job(lambda body: gateway(handle, '/_lab/internal/admin/students/prepopulate', body,
                                                         timeout=600), load_faig_view(), request, log)
            elif kind == 'password':
                policy = {'mode': request['password_mode']}
                if request['password_mode'] in ('shared', 'base'):  # Change 2026-11-23: 'file' sends no value
                    policy['value'] = password
                result = gateway(handle, '/_lab/internal/admin/students/password',
                                 {'number': request['number'], 'password': policy}, timeout=120)
                password = policy = None
                log(f"{result['student']}: password reset and verified by student sign-in; stored for the share "
                    f"page; fallback sign-in {result.get('fallback', 'not changed')}")
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


def public_origin(headers):
    if PUBLIC_ORIGIN:
        return PUBLIC_ORIGIN
    return f"{headers.get('X-Forwarded-Proto', 'https')}://{headers.get('X-Forwarded-Host', '')}"


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
        if path in ('/api/roster', '/api/roster/share'):
            try:
                reply = gateway(self.headers.get('X-Lab-Session', ''),
                                '/_lab/internal/admin/roster' + ('?reveal=1' if path.endswith('share') else ''))
            except SessionLost:
                return self.reply(401, {'error': 'Your FAIG session ended; sign in again.'})
            except (BrokerError, UnknownOutcome) as exc:
                return self.reply(503, {'error': str(exc)})
            if path.endswith('share'):
                reply['sign_in_url'] = public_origin(self.headers) + '/'
            return self.reply(200, reply)
        if path == '/api/approvals':
            # Change 2026-11-20: auto-approval history (student, type, object, change, result).
            query = dict(urllib.parse.parse_qsl(urlsplit(self.path).query))
            student = query.get('student', '')
            limit = query.get('limit', '200')
            if not limit.isdigit():
                return self.reply(400, {'error': 'bad limit'})
            if student and not re.fullmatch(r'student\d{2,}|[^\s@]+@[^\s@]+', student):
                return self.reply(400, {'error': 'bad student filter'})
            with connect() as db:
                try:
                    status = gateway(self.headers.get('X-Lab-Session', ''), '/_lab/internal/admin/auto-approve', timeout=15)
                    sync_approvals(db, self.headers.get('X-Lab-Session', ''), status)
                except (SessionLost, BrokerError, UnknownOutcome):
                    pass  # show what is already stored
                return self.reply(200, {'items': list_approvals(db, student, int(limit))})
        if path == '/api/state':
            items, platform, error = load_catalog()
            # Change 2026-11-20: live auto-approval status from lab_auth (no secrets in it).
            try:
                approval = gateway(self.headers.get('X-Lab-Session', ''), '/_lab/internal/admin/auto-approve', timeout=15)
            except SessionLost:
                approval = {'state': 'unavailable', 'stop_reason': 'Your FAIG session ended; sign in again.'}
            except (BrokerError, UnknownOutcome) as exc:
                approval = {'state': 'unavailable', 'stop_reason': str(exc)}
            with connect() as db:
                approval['preference'] = auto_approval_preference(db)
                approval['history_added'] = sync_approvals(db, self.headers.get('X-Lab-Session', ''), approval)
                return self.reply(200, {
                    'user': self.headers.get('X-Lab-User', ''),
                    'catalog': items, 'catalog_error': error,
                    'pricing': {k: platform.get(k) for k in ('currency', 'unit', 'pricing_note')},
                    'selected': selected(db), 'jobs': jobs(db), 'faig_actions': bool(caller_token()),
                    'gui_only': GUI_ONLY,
                    # Change 2026-11-23: non-secret summary of the instructor student password file.
                    'student_password_file': student_password_file_summary(self.headers.get('X-Lab-Session', '')),
                    # 'auto_approval': {'enabled': False, 'state': 'unavailable',
                    #                   'detail': 'Auto-approval is not connected yet.'}})  # Change 2026-11-20
                    'auto_approval': approval})
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
                if path == '/api/auto-approve' and set(body) == {'enabled', 'hours'}:
                    # Change 2026-11-20: save the preference, then start/stop the worker in lab_auth.
                    save_auto_approval_preference(db, body['enabled'], body['hours'])
                    try:
                        status = gateway(self.headers.get('X-Lab-Session', ''), '/_lab/internal/admin/auto-approve',
                                         {'enabled': body['enabled'], 'hours': body['hours']}, timeout=15)
                    except SessionLost:
                        return self.reply(401, {'error': 'Your FAIG session ended; sign in again.'})
                    except (BrokerError, UnknownOutcome) as exc:
                        return self.reply(503, {'error': str(exc)})
                    status['preference'] = auto_approval_preference(db)
                    return self.reply(200, status)
                if path == '/api/roster/name' and set(body) == {'student', 'display_name'}:
                    try:
                        gateway(self.headers.get('X-Lab-Session', ''), '/_lab/internal/admin/roster/name', body)
                    except SessionLost:
                        return self.reply(401, {'error': 'Your FAIG session ended; sign in again.'})
                    except (BrokerError, UnknownOutcome) as exc:
                        return self.reply(400, {'error': str(exc)})
                    return self.reply(200, {'saved': True})
                password = None
                if path in ('/api/jobs/students', '/api/jobs/password'):
                    password = body.pop('password', None)
                    if body.get('password_mode') in ('shared', 'base') and (not isinstance(password, str) or not password):
                        raise ValueError('enter a password for this mode')
                    if body.get('password_mode') in ('generated', 'file') and password:
                        raise ValueError('this password mode takes no typed password')
                if path in ('/api/jobs/models', '/api/jobs/students', '/api/jobs/prepopulate', '/api/jobs/password'):
                    kind = path.rsplit('/', 1)[-1]
                    if kind in EXECUTABLE and not caller_token():
                        return self.reply(409, {'error': 'FAIG actions are not configured yet (no broker caller token).'})
                    job = create_job(db, kind, self.headers['X-Lab-User'], body)
                    status = db.execute('SELECT status, request FROM jobs WHERE id=?', (job,)).fetchone()
                    if kind in EXECUTABLE:
                        threading.Thread(target=execute, daemon=True,
                                         args=(job, kind, json.loads(status[1]), self.headers.get('X-Lab-Session', '')),
                                         kwargs={'password': password}).start()
                    password = None
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
