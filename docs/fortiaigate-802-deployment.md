# FortiAIGate 8.0.2 AWS Development Deployment

The 8.0.2 deployment path is under live validation. Use only on an isolated
single-node lab with trusted ingress sources. The chart's L4 profile is marked
development-only; it is not a production hardware recommendation. The existing
`ingress-nginx` controller is retired upstream and must be replaced before
production exposure.

After the [AWS k3s foundation](aws-k3s-foundation.md) is ready and the 8.0.2
images are in ECR, run from the repository root:

```bash
ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_fortiaigate.yml
```

Before Helm submission, the role pre-pulls the model, vLLM and Triton images
into the node cache with temporary pods and the namespace pull secret. Set
`fortiaigate_prefetch_images: false` to skip this stage. Image availability is
verified in k3s; an image lacking `/bin/true` can report a pod execution error
after its successful pull. The pod is cleaned up after verification. Cache hits and cold pre-pulls of all three large ECR images were verified on
a fresh AWS host.

This initial path supports the EC2 instance-role ECR token source. It refreshes
the namespace image-pull secret at startup and every six hours through a
root-owned systemd timer. AWS registry tokens expire, so check the timer and
service if subsequent image pulls fail:

```bash
sudo systemctl status fortiaigate-ecr-refresh.timer
sudo systemctl status fortiaigate-ecr-refresh.service
kubectl -n fortiaigate get pods,pvc,ingress
```

GPU profile and attachment are configured by `fortiaigate_gpu_profile` and
`fortiaigate_vllm_gpu_attach`; the tracked defaults are `l4` and `shared` for
the first L4 lab. Set an appropriate profile in ignored `user.yml` when using a
different GPU. Dedicated attachment needs additional allocatable GPUs and
licensing. The local-path storage post-render patch uses ReadWriteOnce for the
vendor's shared PVC; all consuming pods must stay on the same node. Multi-node
installations require a properly configured shared storage class.

<!-- Historical CPU-only experiment: fortiaigate_gpu_enabled: false.
Do not use as a normal deployment: the observed lab forwarded traffic with
security scanning paused. GPU experiments are not invoked by this workflow. -->

The chart creates a master-key Secret and uses a Kubernetes lookup to retain it
across Helm upgrades. The Secret is marked to survive Helm uninstall, but not
namespace deletion, cluster loss or a rebuild. Back it up securely with the
associated application database before changing or destroying the cluster.
Never commit its contents. Restore the same key with its database or stored
credentials cannot be decrypted.

The 8.0.2 license is uploaded after install through the administrator GUI or
supported API, rather than being staged into the Helm chart. A successful Helm
submission does not mean the application, GPU model, license or scanning is
ready. Check pod and application health and validate a licensed request before
using the deployment.

## LiteLLM Credential For FortiAIGate

FortiAIGate's LiteLLM provider and the chatbot's direct mode use a shared,
non-admin LiteLLM virtual key instead of the LiteLLM master key. The master key
is LiteLLM's administrator credential (key management, spend logs, model
changes); a virtual key can only call models.

`deploy_litellm.yml` creates the key once by alias (`faig-lab-shared`, no model
restriction), stores it in the `litellm/litellm-shared-virtual-key` Secret
(key `api-key`) and in the owner-only file named by
`litellm_shared_virtual_key_local_file` outside Git, and verifies that it can
list models but cannot generate keys. Later runs reuse it. If the Secret is
lost while the alias still exists in LiteLLM, the role stops rather than
creating a duplicate; rerun with
`-e litellm_shared_virtual_key_regenerate=true` only after deciding how to
replace the old key.

Point FortiAIGate's provider at the key with the experimental provider tool,
which also checks the stored credential mask and runs FortiAIGate's
connectivity test:

```bash
python3 experiments/faig-api-lab/model_pricing.py --url "$FAIG_URL" \
  --admin-credentials "$FAIG_ADMIN_FILE" --insecure \
  --provider litellm-direct \
  --set-credential-file "$LITELLM_SHARED_KEY_FILE" --apply
```

Because FortiAIGate no longer holds the master key, rotating the master key no
longer breaks FortiAIGate. Per-student LiteLLM keys (for example with
FortiAIGate key passthrough) remain a possible later extension.

## Vendor Chart Expectations Versus Lab Workarounds

Reviewed against `FAIG_helm/8.0.2/fortiaigate` (chart 8.0.2, build 0055):

| Area | What the 8.0.2 chart expects | What this lab applies | Notes |
|---|---|---|---|
| Ingress | `ingress.className: nginx` (default) with ingress-nginx annotations: `app-root /ui`, `proxy-body-size 64m`, backend HTTPS; `traefik` and `alb` are also templated | Installs the `ingress-nginx` controller (chart 4.15.1, controller v1.15.1) with k3s Traefik disabled | Matches the vendor default, but ingress-nginx is retired upstream. The chart's Traefik branch only sets entrypoint and a `default-redirect-https` middleware; backend HTTPS, body size and the root redirect would need verification before switching. |
| Shared storage | One `ReadWriteMany` PVC (`fortiaigate-storage`), shared by the application services and PostgreSQL (`existingClaim`); access mode hardcoded in `storage.yaml` | `local-path` storage class; the post-renderer rewrites the PVC to `ReadWriteOnce` | Works only because every pod runs on one node. The `storage.accessModes` value we render is ignored by the chart. Multi-node needs a real RWX class (for example NFS or EFS). |
| GPU runtime | No `runtimeClassName` option; assumes the NVIDIA runtime is the node default (as the GPU Operator configures) | k3s registers a non-default `nvidia` RuntimeClass; the post-renderer adds `runtimeClassName: nvidia` to GPU workloads (`triton-vllm-server` in shared mode) | Setting the NVIDIA runtime as the k3s default would remove this patch. |
| GPU sizing | `fortiaigate.gpu.type` profiles in `files/gpu-profiles.yaml`; `vllm.gpuAttach` shared or dedicated | `gpu.type: l4`, `gpuAttach: shared`, `updateStrategy: Recreate` | Vendor options, not workarounds; `l4` is marked development-only by the vendor. |
| Images | Pull from the image repository with `pullSecrets` | Private ECR mirror, instance-role ECR token refresh timer, image pre-pull | Deployment choice; pre-pull avoids slow first starts with large images. |
| TLS | Certificate and key read from files inside the chart (`tls.cert`, `tls.key`) | Custom TLS files are copied into the staged chart before install | Needed because the chart reads files rather than an existing Secret. |
| PostgreSQL/Redis | Bitnami subcharts using `bitnamilegacy/*` images | Used as shipped | Vendor-side risk: the legacy repository no longer receives updates. |
| Chart packaging | Vendor tarball | Repacked without macOS metadata files | Workstation artifact only. |
