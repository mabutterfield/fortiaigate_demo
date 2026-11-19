"""Plan a test directly from the catalog, without loading credentials."""
from __future__ import annotations


def plan_case(catalog, scenario_id, action, *, test_id=None):
    scenario = catalog['scenarios'].get(scenario_id)
    if scenario is None:
        raise ValueError(f'unknown scenario: {scenario_id}')
    action_spec = next((item for item in scenario['actions'] if item['id'] == action), None)
    tests = [item for item in scenario['tests'] if item['action'] == action]
    if test_id is not None:
        tests = [item for item in tests if item['id'] == test_id]
    elif len(tests) > 1:
        tests = [item for item in tests if item['id'] == action + '-attack']
    if action_spec is None or len(tests) != 1:
        raise ValueError(f'could not select one test for {scenario_id}/{action}; specify a valid test ID')
    test = tests[0]
    prompt = next((prompt for group in scenario['prompts'].values() for prompt in group
                   if prompt['id'] == test['prompt_ref']), None)
    if prompt is None:
        raise ValueError('test prompt reference not found')
    frontend = test.get('frontend_instruction', 'none')
    system_prompt = ''
    if frontend == 'compromised':
        path = scenario.get('frontend_instruction_file')
        if not path:
            raise ValueError('compromised frontend fixture not found')
        system_prompt = (catalog['root'] / path).read_text(encoding='utf-8')
    tools = list(scenario['tools'])
    # Opt into only the extended sets required by this test; debug-only sets
    # must not become available implicitly.
    needed = set(test['required_tools']) | set(test['attack_tools'])
    for group in scenario['extended_tool_sets']:
        if needed.intersection(group['tools']):
            tools.extend(group['tools'])
    tools = list(dict.fromkeys(tools))
    model = catalog['models'][action_spec['model_ref']]
    return {'scenario': scenario_id, 'scenario_version': scenario['scenario_version'],
            'action': action, 'case_id': test['id'], 'model': model['public_name'],
            'prompt': prompt['text'], 'system_prompt': system_prompt,
            'tools': tools, 'max_rounds': scenario['max_rounds'], 'test': test}
