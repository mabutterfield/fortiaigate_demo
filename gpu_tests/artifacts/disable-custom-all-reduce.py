import json,subprocess
base=['kubectl','-n','fortiaigate'];d=json.loads(subprocess.check_output(base+['get','deployment','triton-vllm-server','-o','json']));i=next(i for i,c in enumerate(d['spec']['template']['spec']['containers']) if c['name']=='vllm')
ops=[{'op':'add','path':f'/spec/template/spec/containers/{i}/args/-','value':'--disable-custom-all-reduce'}]
subprocess.run(base+['patch','deployment','triton-vllm-server','--type=json','-p',json.dumps(ops)],check=True)
