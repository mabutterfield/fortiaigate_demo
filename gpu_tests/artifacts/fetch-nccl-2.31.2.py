import hashlib,json,os,urllib.request,zipfile
root='/opt/faig-lab/nccl-2.31.2'; os.makedirs(root,exist_ok=True)
with urllib.request.urlopen('https://pypi.org/pypi/nvidia-nccl-cu13/2.31.2/json',timeout=30) as r: d=json.load(r)
x=next(x for x in d['urls'] if x['filename'].endswith('x86_64.whl'))
p=os.path.join(root,'nccl.whl')
with urllib.request.urlopen(x['url'],timeout=60) as r,open(p,'wb') as f:
 while True:
  block=r.read(1048576)
  if not block: break
  f.write(block)
h=hashlib.sha256()
with open(p,'rb') as f:
 for block in iter(lambda:f.read(1048576),b''):h.update(block)
if h.hexdigest()!=x['digests']['sha256']: raise RuntimeError('NCCL wheel checksum mismatch')
with zipfile.ZipFile(p) as z:
 files=[n for n in z.namelist() if n.endswith('/libnccl.so.2')]
 if len(files)!=1: raise RuntimeError('Expected exactly one NCCL shared library')
 with z.open(files[0]) as src,open(os.path.join(root,'libnccl.so.2'),'wb') as dest:
  while True:
   b=src.read(1048576)
   if not b: break
   dest.write(b)
os.chmod(os.path.join(root,'libnccl.so.2'),0o755);os.remove(p)
print('Installed NVIDIA NCCL 2.31.2 test library; wheel SHA256 verified')
