import json,subprocess
base=['kubectl','-n','fortiaigate']
d=json.loads(subprocess.check_output(base+['get','deployment','triton-vllm-server','-o','json']))
s=d['spec']['template']['spec']; i=next(i for i,c in enumerate(s['containers']) if c['name']=='vllm'); c=s['containers'][i]
assert not any(v['name']=='faig-nccl-lab' for v in s['volumes'])
ops=[{'op':'add','path':'/spec/template/spec/volumes/-','value':{'name':'faig-nccl-lab','hostPath':{'path':'/opt/faig-lab/nccl-2.31.2','type':'Directory'}}},{'op':'add','path':f'/spec/template/spec/containers/{i}/volumeMounts/-','value':{'name':'faig-nccl-lab','mountPath':'/opt/faig-nccl-lab','readOnly':True}}]
# Reconstructed from the experiment's final state: never set LD_PRELOAD.
for name,value in [('VLLM_NCCL_SO_PATH','/opt/faig-nccl-lab/libnccl.so.2')]:
 assert not any(x['name']==name for x in c.get('env',[]))
 ops.append({'op':'add','path':f'/spec/template/spec/containers/{i}/env/-','value':{'name':name,'value':value}})
subprocess.run(base+['patch','deployment','triton-vllm-server','--type=json','-p',json.dumps(ops)],check=True)
