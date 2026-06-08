# FortiAIGate Post-Render Patches

The phase 1 deployment uses `k8s-overlays/bin/post_render_fortiaigate.py` as a Helm post-renderer. The script patches the rendered stock chart instead of editing or vendoring `FAIG_helm`.

Current patch behavior:

- FortiAIGate PVC uses `ReadWriteOnce` and `local-path`
- Triton deployment uses `runtimeClassName: nvidia`
- Triton deployment uses `Recreate`
- Triton container gets NVIDIA visibility/capability environment variables
- Triton resources are raised for the proven `g4dn.4xlarge` profile
- Triton `/dev/shm` memory volume is raised to `8Gi`
- nginx ingress gets `proxy-ssl-verify: "off"`
