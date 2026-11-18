# FortiAIGate Post-Render Patches

The 8.0.2 deployment uses `k8s-overlays/bin/post_render_fortiaigate_802.py`
to select the NVIDIA runtime for GPU-requesting workloads and adapt the
`fortiaigate-storage` PVC to single-node `local-path` storage. It does not
apply the legacy image or Triton resource overrides listed below.

For releases before 8.0.2, the deployment uses
`k8s-overlays/bin/post_render_fortiaigate.py`. Both patch rendered output
instead of editing or vendoring `FAIG_helm`.

Legacy patch behavior:

- FortiAIGate PVC uses `ReadWriteOnce` and `local-path`
- Triton deployment uses `runtimeClassName: nvidia`
- Triton deployment uses `Recreate`
- Triton container gets NVIDIA visibility/capability environment variables
- Triton resources are raised for the proven `g4dn.4xlarge` profile
- Triton `/dev/shm` memory volume is raised to `8Gi`
- nginx ingress gets `proxy-ssl-verify: "off"`
