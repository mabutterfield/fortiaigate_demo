"""Read-only catalog loader and deterministic view builder; standard library only.

This catalog is a review artifact, not yet an integrated installer.
No live FAIG, Kubernetes, or credentials are read or modified.
"""
from __future__ import annotations

from copy import deepcopy
import ast
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from .vocabulary import ACTIONS, EXECUTIONS, VERDICTS, EVIDENCE, OUTCOMES, VERDICT_PRIORITY, RETIRED

SCHEMA = 1
KNOWN_WHEN = {'execution', 'verdict', 'evidence_present', 'tools_called_include', 'missing_required_tools_include'}


def evidence_list(value):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ValueError('evidence must be a list of IDs')
    for item in value:
        if item in RETIRED:
            raise ValueError(f'{item} was renamed to {RETIRED[item]}')
        if item not in EVIDENCE:
            raise ValueError(f'unknown evidence ID {item}')
    if len(set(value)) != len(value):
        raise ValueError('duplicate evidence ID')


def validate_expect(expect):
    fields(expect, ('verdict', 'evidence_present', 'evidence_absent'))
    if expect['verdict'] is not None and expect['verdict'] not in VERDICT_PRIORITY:
        raise ValueError('invalid expected verdict')
    evidence_list(expect['evidence_present']); evidence_list(expect['evidence_absent'])
    if set(expect['evidence_present']) & set(expect['evidence_absent']):
        raise ValueError('evidence cannot be both present and absent')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError('expected an object')
    missing = set(required) - value.keys()
    unknown = {k for k in value if k not in set(required) | set(optional) and not k.startswith('x_')}
    if missing or unknown:
        raise ValueError(f'missing fields {sorted(missing)}, unknown fields {sorted(unknown)}')


def safe_file(root, name):
    if not isinstance(name, str) or not name:
        raise ValueError('file reference must be a nonempty string')
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError(f'file missing or outside catalog root: {name}')
    return target


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'{path}: {exc}') from exc


def handler_names(path):
    """Verify the current dispatcher explicitly refers to tool names."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'run_tool']
    if len(functions) != 1:
        raise ValueError(f'{path}: expected exactly one run_tool dispatcher')
    return {n.value for n in ast.walk(functions[0]) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _version(obj, path):
    if obj.get('schema_version') != SCHEMA:
        raise ValueError(f'{path}: found schema {obj.get("schema_version")!r}; supported [{SCHEMA}]; migrate the file or use a compatible loader')


def load(root):
    """Return (catalog, errors); errors are non-secret validation messages."""
    root = Path(root).resolve()
    data = root / 'catalog802/data'
    try:
        index = read_json(data / 'index.json'); _version(index, 'index.json')
        fields(index, ('schema_version', 'scenarios'))
        platform = read_json(data / 'platform.json'); _version(platform, 'platform.json')
        fields(platform, ('schema_version', 'faig_version', 'currency', 'unit', 'naming', 'hello_world', 'detectors', 'guard_templates'))
        if (platform['currency'], platform['unit']) != ('USD', 'per_1m_tokens'):
            raise ValueError('platform prices must use USD per 1M tokens')
        validate_expect(platform['hello_world']['expect'])
        models_doc = read_json(data / 'models.json'); _version(models_doc, 'models.json')
        fields(models_doc, ('schema_version', 'models')); models = models_doc['models']
        tools_doc = read_json(data / 'tools/catalog.json'); _version(tools_doc, 'tools/catalog.json')
        fields(tools_doc, ('schema_version', 'tools')); tools = tools_doc['tools']
        if not all(isinstance(x, dict) for x in (models, tools, platform['detectors'], platform['guard_templates'])):
            raise ValueError('models, tools, detectors, and guard templates must be objects')
        if 'pass-model' not in models:
            raise ValueError('platform model pass-model is required')
        alias_instructions = {}
        for name, model in models.items():
            fields(model, ('public_name', 'backend_alias', 'provider', 'target', 'instruction_file', 'prices'))
            instruction = model['instruction_file']
            if instruction is not None:
                safe_file(root, instruction)
            alias = model['backend_alias']
            if alias in alias_instructions and alias_instructions[alias] != instruction:
                raise ValueError(f'{name}: conflicting instruction source for LiteLLM alias {alias}')
            alias_instructions[alias] = instruction
            fields(model['prices'], ('input', 'output', 'cache_read', 'cache_write'))
            for field, value in model['prices'].items():
                if value is None:
                    continue
                if not isinstance(value, (str, int)) or isinstance(value, bool):
                    raise ValueError(f'{name}.{field}: use a decimal string or integer')
                try:
                    amount = Decimal(str(value))
                    if not amount.is_finite() or amount < 0:
                        raise ValueError(f'{name}.{field}: price must be finite and nonnegative')
                except InvalidOperation as exc:
                    raise ValueError(f'{name}.{field}: invalid decimal price') from exc
        for name, tool in tools.items():
            fields(tool, ('version', 'description', 'input_schema', 'output_schema', 'handler', 'dataset', 'side_effects', 'open_world'), ('dataset_files',))
            if not isinstance(tool.get('dataset_files', []), list):
                raise ValueError(f'{name}: dataset_files must be a list')
            for fixture in tool.get('dataset_files', []):
                safe_file(root, fixture)
            parts = tool['handler'].split(':')
            if len(parts) != 3 or parts[1:] != ['run_tool', name]:
                raise ValueError(f'{name}: invalid handler reference')
            if name not in handler_names(safe_file(root, parts[0])):
                raise ValueError(f'{name}: no matching handler in dispatcher')
            safe_file(root, tool['dataset'])
        scenarios = {}
        if not isinstance(index['scenarios'], list) or not index['scenarios']:
            raise ValueError('index must list at least one scenario')
        for entry in index['scenarios']:
            scenario_file = safe_file(data, entry)
            scenario = read_json(scenario_file); _version(scenario, entry)
            fields(scenario, ('schema_version', 'id', 'scenario_version', 'display_name', 'description', 'learning',
                              'models', 'tools', 'extended_tool_sets', 'max_rounds', 'prompts', 'actions', 'tests'), ('frontend_instruction_file', 'frontend_instruction_label', 'frontend_instruction_description'))
            if 'frontend_instruction_file' in scenario:
                safe_file(root, scenario['frontend_instruction_file'])
                if any(not isinstance(scenario.get(key), str) or not scenario[key].strip() for key in ('frontend_instruction_label', 'frontend_instruction_description')):
                    raise ValueError('frontend instruction requires a label and description')
            elif 'frontend_instruction_label' in scenario or 'frontend_instruction_description' in scenario:
                raise ValueError('frontend instruction metadata requires a fixture')
            sid = scenario['id']
            if sid in scenarios:
                raise ValueError(f'{entry}: duplicate scenario ID {sid}')
            if not isinstance(scenario['models'], list) or not scenario['models'] or any(m not in models for m in scenario['models']):
                raise ValueError(f'{sid}: missing or unknown model reference')
            if not isinstance(scenario['max_rounds'], int) or isinstance(scenario['max_rounds'], bool) or scenario['max_rounds'] < 1:
                raise ValueError(f'{sid}: max_rounds must be a positive integer')
            if not isinstance(scenario['learning'], list):
                raise ValueError(f'{sid}: learning must be a list')
            for block in scenario['learning']:
                fields(block, ('type', 'content'))
                if block['type'] != 'text' or not isinstance(block['content'], str):
                    raise ValueError(f'{sid}: this schema supports text learning blocks only')
            all_tools = list(scenario['tools'])
            for ext in scenario['extended_tool_sets']:
                fields(ext, ('id', 'display_name', 'tools'))
                all_tools.extend(ext['tools'])
            if any(name not in tools for name in all_tools):
                raise ValueError(f'{sid}: unknown tool reference')
            fields(scenario['prompts'], ('clean', 'attack'))
            prompt_ids = set()
            for group in ('clean', 'attack'):
                if not isinstance(scenario['prompts'][group], list):
                    raise ValueError(f'{sid}: prompt group must be a list')
                for prompt in scenario['prompts'][group]:
                    fields(prompt, ('id', 'text'))
                    if not all(isinstance(prompt[k], str) and prompt[k].strip() for k in ('id', 'text')) or prompt['id'] in prompt_ids:
                        raise ValueError(f'{sid}: prompt IDs and text must be nonempty and IDs unique')
                    prompt_ids.add(prompt['id'])
            actions = {}
            for action in scenario['actions']:
                fields(action, ('id', 'display_name', 'expected_behavior', 'guard_template_ref', 'model_ref'))
                aid = action['id']
                if aid == 'deny':
                    raise ValueError(f'{sid}: action deny was renamed to block in schema {SCHEMA}')
                if aid not in ACTIONS or aid in actions:
                    raise ValueError(f'{sid}: unknown or duplicate action {aid}')
                if action['model_ref'] not in scenario['models'] or action['guard_template_ref'] not in platform['guard_templates']:
                    raise ValueError(f'{sid}: unknown action model or guard template')
                guard = platform['guard_templates'][action['guard_template_ref']]
                if any(d not in platform['detectors'] for d in guard.get('detectors', [])):
                    raise ValueError(f'{sid}: guard references an unknown detector')
                actions[aid] = action
            for test in scenario['tests']:
                for retired in ('expected_result', 'expected_log_verdict'):
                    if retired in test:
                        raise ValueError(f'{retired} was renamed to {RETIRED[retired]}')
                fields(test, ('id', 'action', 'prompt_ref', 'expect', 'required_tools', 'forbidden_tools', 'attack_tools'), ('known_issue', 'frontend_instruction'))
                frontend = test.get('frontend_instruction', 'none')
                if frontend not in ('none', 'compromised') or (frontend == 'compromised' and not scenario.get('frontend_instruction_file')):
                    raise ValueError('invalid or unavailable frontend instruction selection')
                if test['action'] not in actions:
                    raise ValueError(f'{sid}.{test["id"]}: unknown action')
                validate_expect(test['expect'])
                if 'attack-tool-called' in test['expect']['evidence_present'] + test['expect']['evidence_absent'] and not test['attack_tools']:
                    raise ValueError('attack-tool-called requires attack_tools')
                if test['prompt_ref'] not in prompt_ids:
                    raise ValueError(f'{sid}.{test["id"]}: invalid prompt reference')
                if any(not isinstance(test[k], list) or any(not isinstance(x, str) for x in test[k]) for k in ('required_tools', 'forbidden_tools', 'attack_tools')):
                    raise ValueError('test tool references must be lists of IDs')
                if any(x not in all_tools for x in test['required_tools'] + test['forbidden_tools'] + test['attack_tools']):
                    raise ValueError(f'{sid}.{test["id"]}: test references undeclared tools')
                if 'known_issue' in test:
                    issue = test['known_issue']; fields(issue, ('id', 'summary', 'scope', 'when'))
                    if not isinstance(issue['when'], dict) or not issue['when'] or set(issue['when']) - KNOWN_WHEN:
                        raise ValueError(f'{sid}.{test["id"]}: invalid known-issue predicate')
                    for key, value in issue['when'].items():
                        if key == 'execution' and value not in EXECUTIONS:
                            raise ValueError('invalid known-issue execution')
                        if key == 'verdict' and value not in VERDICTS:
                            raise ValueError('invalid known-issue verdict')
                        if key == 'evidence_present':
                            evidence_list(value)
                        if key in ('tools_called_include', 'missing_required_tools_include') and (not isinstance(value, list) or not value or any(v not in all_tools for v in value)):
                            raise ValueError('invalid known-issue tool references')
                    fields(issue['scope'], ('faig_version', 'scenario_version'))
                    if (not isinstance(issue['scope']['faig_version'], list) or not issue['scope']['faig_version']
                            or any(not isinstance(v, str) or not v for v in issue['scope']['faig_version'])
                            or not isinstance(issue['scope']['scenario_version'], str)
                            or not issue['scope']['scenario_version']):
                        raise ValueError(f'{sid}.{test["id"]}: known issue requires FAIG version scope')
            scenarios[sid] = scenario
        return {'root': root, 'platform': platform, 'models': models, 'tools': tools, 'scenarios': scenarios}, []
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return None, [str(exc)]


def known_failure_matches(issue, observed, *, faig_version, scenario_version, failed):
    """Only annotate a failed result when all declarative conditions match."""
    if not failed or faig_version not in issue['scope']['faig_version']:
        return False
    scope = issue['scope']['scenario_version']
    if not (scenario_version.startswith(scope[:-1]) if scope.endswith('x') else scenario_version == scope):
        return False
    when = issue['when']
    if not when or set(when) - KNOWN_WHEN:
        return False
    checks = {
        'execution': lambda v: observed.get('execution') == v,
        'verdict': lambda v: observed.get('verdict') == v,
        'evidence_present': lambda v: set(v).issubset(observed.get('evidence', [])),
        'tools_called_include': lambda v: set(v).issubset(observed.get('tools_called', [])),
        'missing_required_tools_include': lambda v: set(v).issubset(observed.get('missing_required_tools', [])),
    }
    return all(checks[key](value) for key, value in when.items())


def build_views(catalog, source_commit=None, generated_at=None):
    """Build versioned secret-free views; hashes exclude generated metadata."""
    root = catalog['root']; models = catalog['models']; tools = catalog['tools']; platform = catalog['platform']
    stamp = generated_at or datetime.now(timezone.utc).isoformat()
    def model_value(mid):
        model = deepcopy(models[mid]); path = model['instruction_file']
        model['id'] = mid
        model['instruction'] = safe_file(root, path).read_text(encoding='utf-8') if path else None
        return model
    def tool_value(tid):
        tool = deepcopy(tools[tid]); tool['id'] = tid
        for field in ('dataset', 'handler'):
            path = tool[field].split(':')[0]
            tool[field + '_sha256'] = hashlib.sha256(safe_file(root, path).read_bytes()).hexdigest()
        tool['dataset_files_sha256'] = {path: hashlib.sha256(safe_file(root, path).read_bytes()).hexdigest() for path in tool.get('dataset_files', [])}
        return tool
    def header(name, items):
        return {'view': name, 'view_version': 1, 'catalog_schema_version': SCHEMA,
                'metadata': {'source_commit': source_commit, 'generated_at': stamp}, 'items': items}
    model_items = []
    for mid in sorted(models):
        item = model_value(mid); item['content_hash'] = digest(item); model_items.append(item)
    tool_items = []
    for tid in sorted(tools):
        item = tool_value(tid); item['content_hash'] = digest(item); tool_items.append(item)
    student, provisioning = [], []
    for sid in sorted(catalog['scenarios']):
        scenario = deepcopy(catalog['scenarios'][sid]); refs = list(scenario['tools'])
        for ext in scenario['extended_tool_sets']:
            refs.extend(ext['tools'])
        resolved_models = [model_value(mid) for mid in scenario['models']]
        resolved_tools = [tool_value(tid) for tid in sorted(set(refs))]
        resolved_actions = []
        for action in scenario['actions']:
            action = deepcopy(action); guard = deepcopy(platform['guard_templates'][action['guard_template_ref']])
            guard['resolved_detectors'] = {key: deepcopy(platform['detectors'][key]) for key in guard.get('detectors', [])}
            action['guard'] = guard; resolved_actions.append(action)
        payload = {'scenario': scenario, 'models': resolved_models, 'tools': resolved_tools,
                   'actions': resolved_actions, 'hello_world': platform['hello_world'],
                   'naming': platform['naming'], 'currency': platform['currency'], 'unit': platform['unit'],
                   'faig_version': platform['faig_version']}
        if scenario.get('frontend_instruction_file'):
            payload['frontend_instruction'] = safe_file(root, scenario['frontend_instruction_file']).read_text(encoding='utf-8')
        content_hash = digest(payload)
        # Student views contain reference metadata, never backend instruction text or fixtures.
        visible_models = [{k: v for k, v in model.items() if k not in ('instruction', 'instruction_file')} for model in resolved_models]
        entry = {k: deepcopy(scenario[k]) for k in ('id', 'scenario_version', 'display_name', 'description', 'learning', 'tools', 'extended_tool_sets', 'max_rounds', 'prompts', 'tests')}
        if 'frontend_instruction' in payload:
            entry['frontend_instruction'] = payload['frontend_instruction']
            entry['frontend_instruction_label'] = scenario['frontend_instruction_label']
            entry['frontend_instruction_description'] = scenario['frontend_instruction_description']
        entry.update({'content_hash': content_hash, 'models': visible_models, 'actions': deepcopy(scenario['actions'])})
        student.append(entry)
        provisioning.append({'id': sid, 'scenario_version': scenario['scenario_version'], 'content_hash': content_hash,
                             'models': visible_models, 'actions': resolved_actions})
    passthrough = {k: v for k, v in model_value('pass-model').items()
                   if k not in ('instruction', 'instruction_file')}
    platform_view = {
        'hello_world': deepcopy(platform['hello_world']),
        'passthrough_model': passthrough,
        # Observed FAIG 8.0.2 behavior: direct model access, no policyIds.
        'passthrough_direct_policy_count': 0,
        'naming': deepcopy(platform['naming']),
        'actions_vocabulary': dict(ACTIONS),
        'execution_vocabulary': dict(EXECUTIONS),
        'verdicts_vocabulary': dict(VERDICTS),
        'evidence_vocabulary': dict(EVIDENCE),
        'outcomes_vocabulary': dict(OUTCOMES),
        'verdict_priority': list(VERDICT_PRIORITY),
        'currency': platform['currency'],
        'unit': platform['unit'],
        'pricing_note': 'Artificial FAIG lab prices; not actual AWS charges.',
    }
    platform_view['content_hash'] = digest(platform_view)
    student_view = header('student', student)
    student_view['platform'] = deepcopy(platform_view)
    faig_view = header('faig', provisioning)
    faig_view['platform'] = deepcopy(platform_view)
    return {'models': header('models', model_items), 'mcp': header('mcp', tool_items),
            'student': student_view, 'faig': faig_view}
