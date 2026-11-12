#!/usr/bin/env python3
import copy
import json
import subprocess

base = ['kubectl', '-n', 'fortiaigate']
d = json.loads(subprocess.check_output(base + ['get', 'deployment', 'triton-server', '-o', 'json']))
spec = copy.deepcopy(d['spec']['template']['spec'])
spec.pop('runtimeClassName', None)
for c in spec['containers'] + spec.get('initContainers', []):
    resources = c.get('resources', {})
    for group in ('limits', 'requests'):
        for key in list(resources.get(group, {})):
            if key.startswith('nvidia.com/'):
                del resources[group][key]
    if c['name'] == 'triton':
        env = [e for e in c.get('env', []) if e.get('name') not in ('NVIDIA_VISIBLE_DEVICES', 'CUDA_VISIBLE_DEVICES')]
        env += [{'name': 'NVIDIA_VISIBLE_DEVICES', 'value': 'void'}, {'name': 'CUDA_VISIBLE_DEVICES', 'value': '-1'}]
        c['env'] = env
spec['restartPolicy'] = 'Never'
pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'faig-triton-cpu-probe', 'namespace': 'fortiaigate', 'labels': {'faig-experiment': 'triton-cpu'}}, 'spec': spec}
subprocess.run(base + ['create', '-f', '-'], input=json.dumps(pod).encode(), check=True)
