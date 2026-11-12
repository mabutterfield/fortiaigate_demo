#!/usr/bin/env python3
import json
import subprocess

base = ['kubectl', '-n', 'fortiaigate']
deployment = json.loads(subprocess.check_output(base + ['get', 'deployment', 'triton-vllm-server', '-o', 'json']))
spec = deployment['spec']['template']['spec']
ops = []
undo = []

def replace(path, value, old):
    ops.append({'op': 'replace', 'path': path, 'value': value})
    undo.insert(0, {'op': 'replace', 'path': path, 'value': old})

def set_field(path, value, parent, key):
    if key in parent:
        replace(path, value, parent[key])
    else:
        ops.append({'op': 'add', 'path': path, 'value': value})
        undo.insert(0, {'op': 'remove', 'path': path})

for group, name in [('initContainers', 'gpu-probe'), ('containers', 'triton')]:
    i, container = next((i, c) for i, c in enumerate(spec[group]) if c['name'] == name)
    path = f'/spec/template/spec/{group}/{i}/resources/limits/nvidia.com~1mig-1g.16gb'
    replace(path, '1', container['resources']['limits']['nvidia.com/mig-1g.16gb'])

i, probe = next((i, c) for i, c in enumerate(spec['initContainers']) if c['name'] == 'gpu-probe')
j, expected = next((j, e) for j, e in enumerate(probe['env']) if e['name'] == 'GPU_PROBE_EXPECT_COUNT')
replace(f'/spec/template/spec/initContainers/{i}/env/{j}/value', '1', expected['value'])

i, triton = next((i, c) for i, c in enumerate(spec['containers']) if c['name'] == 'triton')
prefix = f'/spec/template/spec/containers/{i}'
set_field(prefix + '/command', ['/bin/sh', '-c'], triton, 'command')
replace(prefix + '/args', ['sleep 86400'], triton['args'])
for key in ('startupProbe', 'readinessProbe', 'livenessProbe'):
    if key in triton:
        ops.append({'op': 'remove', 'path': prefix + '/' + key})
        undo.insert(0, {'op': 'add', 'path': prefix + '/' + key, 'value': triton[key]})

i, vllm = next((i, c) for i, c in enumerate(spec['containers']) if c['name'] == 'vllm')
args = list(vllm['args'])
changes = {'--gpu-memory-utilization=': '--gpu-memory-utilization=0.97',
           '--tensor-parallel-size=': '--tensor-parallel-size=1',
           '--max-model-len=': '--max-model-len=1024',
           '--max-num-seqs=': '--max-num-seqs=1'}
for n, arg in enumerate(args):
    for old, new in changes.items():
        if arg.startswith(old):
            args[n] = new
args.append('--enforce-eager')
replace(f'/spec/template/spec/containers/{i}/args', args, vllm['args'])

with open('/root/faig-single-slice-undo.json', 'w') as stream:
    json.dump(undo, stream)
subprocess.run(base + ['patch', 'deployment', 'triton-vllm-server', '--type=json', '-p', json.dumps(ops)], check=True)
