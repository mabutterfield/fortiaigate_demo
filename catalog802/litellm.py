"""Build the LiteLLM subset of the existing Ansible matrix from the catalog."""
from .loader import digest


def build_litellm_matrix(catalog, *, faig_chain_reentry_uri='/v1/passthrough'):
    models = catalog['models']
    aliases = {}
    for model in models.values():
        alias = model['backend_alias']
        spec = (model['target'], model['instruction_file'])
        if alias in aliases and aliases[alias] != spec:
            raise ValueError(f'conflicting target or instructions for LiteLLM alias {alias}')
        aliases[alias] = spec
    if aliases.get('pass-model') != ('llm-default', None):
        raise ValueError('pass-model must use llm-default without instructions')
    profiles = [{'name': 'passthrough', 'enabled': False, 'position': 'prepend',
                 'instruction': 'No backend instruction injection for passthrough model aliases.'}]
    model_entries = []
    model_profiles = {}
    for alias, (target, path) in sorted(aliases.items()):
        profile = alias if path else 'passthrough'
        if path:
            content = (catalog['root'] / path).read_bytes()
            profiles.append({'name': profile, 'enabled': True, 'position': 'prepend',
                             'source_path': path, 'content_hash': digest(content.decode('utf-8'))})
        model_entries.append({'name': alias, 'llm_target': target, 'instruction_profile': profile})
        model_profiles[alias] = profile
    return {'schema_version': 1,
            'global': {'passthrough_model_alias': 'pass-model', 'faig_passthrough_uri': '/v1/passthrough',
                       'faig_chain_reentry_uri': faig_chain_reentry_uri},
            'llm_targets': [{'name': target} for target in sorted({target for target, _ in aliases.values()})],
            'litellm_models': model_entries,
            'litellm_instruction_profiles': sorted(profiles, key=lambda item: item['name']),
            'litellm_model_instruction_profiles': model_profiles}
