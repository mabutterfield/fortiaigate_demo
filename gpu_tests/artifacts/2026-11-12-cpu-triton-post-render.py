#!/usr/bin/env python3
"""Lab-only Helm post-renderer: CPU Triton; preserve standard k3s patches."""
import importlib.util
import sys
import yaml

path = '/home/ubuntu/tmp/fortiaigate-post-render.py'
spec = importlib.util.spec_from_file_location('faig_base_postrender', path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
docs = [doc for doc in yaml.safe_load_all(sys.stdin) if doc]
for doc in docs:
    if doc.get('kind') == 'Deployment' and doc.get('metadata', {}).get('name') == 'triton-server':
        pod = doc['spec']['template']['spec']
        pod.pop('runtimeClassName', None)
        for container in pod.get('initContainers', []) + pod.get('containers', []):
            for group in ('limits', 'requests'):
                resources = container.get('resources', {}).get(group, {})
                for key in list(resources):
                    if key.startswith('nvidia.com/'):
                        del resources[key]
            if container['name'] == 'triton':
                env = [item for item in container.get('env', []) if item['name'] not in ('NVIDIA_VISIBLE_DEVICES', 'CUDA_VISIBLE_DEVICES')]
                env += [{'name': 'NVIDIA_VISIBLE_DEVICES', 'value': 'void'}, {'name': 'CUDA_VISIBLE_DEVICES', 'value': '-1'}]
                container['env'] = env
    base.patch_gpu_runtime(doc)
    base.patch_local_storage(doc)
yaml.safe_dump_all(docs, sys.stdout, explicit_start=True, sort_keys=False)
