# Reproduce the G7 two-slice MIG experiment

This is a **manual lab recipe**, derived from the observed November 11 run.
It has not yet been validated from a completely clean second host. It installs
non-vendor NCCL into the runtime path, uses a privileged device plugin and
changes GPU metering behavior. Do not use it as a production deployment or
interpret a working test as Fortinet support. Validate the source, vendor terms,
versions, network exposure, costs and licensing first.

The commands below distinguish the **controller** (the Mac with this repo and
AWS SSO) from the **host** (the disposable Ubuntu EC2 instance). They do not
include account IDs, credentials, passwords, license contents, IP addresses or
GPU UUIDs. Never commit local profile files, kubeconfig, generated Helm values,
Terraform state, license files or the virtual key.

## 1. Prepare a fresh host — controller

1. Use the operator's extracted FAIG 8.0.2 build 0055 chart at
   `../FAIG_helm/8.0.2/fortiaigate`, and upload the exact image tags listed in
   the [experiment report](2026-11-11-gpu-experiment.md). The chart and images
   are not included in this repo. Confirm chart checksums and ECR access.
2. Log in with the configured AWS SSO profile. Check live capacity, quota,
   pricing, and instance-store layout for the selected region/AZ. The original
   test used `g7.4xlarge` in `us-east-1` with one RTX PRO 4500. An offered AZ
   does not reserve capacity. Make sure teardown preserves the intended ECR
   repositories. Review all Terraform plans before applying them.
3. The previous L4 host was intentionally **replaced**, not resized in place,
   because its application disk and k3s state were disposable. Replacing it
   destroys local database, license and configuration state unless backed up.
   Create-before-destroy can briefly require capacity for both GPU instances.
4. In the **ignored** local profile, select `g7.4xlarge`, set one expected
   physical GPU during initial bootstrap, and select
   `nvidia_driver_package: nvidia-driver-595-server-open`. The G7's Blackwell
   GPU did not initialize with `nvidia-driver-595-server`. The tested role
   changes are in `ansible/roles/nvidia_driver/tasks/main.yml`; they must be
   present in the working tree, not merely at the recorded commit.
5. Apply AWS prep and foundation using the repo's staged workflow. The test
   used a 300 GiB root disk and the fresh-host guarded instance-store image
   cache. Review SSH access and all other local values before applying.
6. Bootstrap, using the newly generated inventory:

   ```bash
   ansible-playbook -i ansible/inventory/aws.generated.ini \
     ansible/playbooks/bootstrap_gpu_k3s.yml
   ```

   Confirm the ordinary one-GPU foundation checks succeed **before** switching
   MIG modes. The role currently expects a whole `nvidia.com/gpu`; rerunning it
   after MIG setup can reset the plugin's settings or fail its validation.

## 2. Enable and persist two MIG slices — host

Inspect the GPU and profile availability first. The tested GPU reported
`1g.16gb`, profile ID `5`, with two available instances. Profile IDs are
hardware-specific; do not blindly reuse them on another GPU.

```bash
nvidia-smi -L
sudo nvidia-smi mig -lgip
sudo nvidia-smi -i 0 -mig 1
sudo nvidia-smi mig -i 0 -cgi 5,5 -C
nvidia-smi -L
```

These commands change the entire physical GPU's MIG configuration. Only run
them on an idle disposable test host after checking for existing GPU workloads
and MIG instances. Do not delete or replace an existing layout without review.

The actual host-local persistence files from the experiment are in
[`artifacts/`](artifacts/):

- `faig-mig-configure.sh` → `/usr/local/sbin/faig-mig-configure` (0755)
- `faig-mig.service` → `/etc/systemd/system/faig-mig.service` (0644)
- `20-faig-mig.conf` → `/etc/systemd/system/k3s.service.d/20-faig-mig.conf`
  (0644)

Copy them to the host, review their contents and install them with root
ownership, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now faig-mig.service
sudo systemctl status faig-mig.service --no-pager
```

The script targets GPU index 0 and profile ID 5. It creates two slices only if
there are none, and refuses a different nonempty layout. The k3s drop-in makes
successful MIG setup a prerequisite for k3s startup; a failure therefore keeps
k3s down rather than silently using the wrong GPU configuration. Review that
tradeoff and inspect `journalctl -u faig-mig.service` if it fails.

## 3. Configure the Kubernetes device plugin — host

The baseline bootstrap used NVIDIA's static v0.17.0 device-plugin manifest.
On this host, `MIG_STRATEGY=mixed` without elevated permissions produced
`error getting device memory info: Insufficient Permissions`. The lab used a
privileged plugin container with privilege escalation permitted. This changes
the plugin's security boundary; it is a temporary workaround on an isolated
lab host, not a general recommendation.

```bash
kubectl -n kube-system set env daemonset/nvidia-device-plugin-daemonset \
  MIG_STRATEGY=mixed
kubectl -n kube-system patch daemonset nvidia-device-plugin-daemonset \
  --type=json -p '[
    {"op":"add","path":"/spec/template/spec/containers/0/securityContext/privileged","value":true},
    {"op":"replace","path":"/spec/template/spec/containers/0/securityContext/allowPrivilegeEscalation","value":true}
  ]'
kubectl -n kube-system rollout status daemonset/nvidia-device-plugin-daemonset
kubectl describe node | grep -A12 Allocatable
```

Check the container index and existing security context before using this JSON
patch on a different manifest. Expect `nvidia.com/mig-1g.16gb: 2` and zero
whole `nvidia.com/gpu` resources. The plugin patch is stored in Kubernetes but
is **not** declared in the repo's bootstrap; applying its upstream manifest
again can reset it. A temporary pod example is
[`artifacts/mig-device-check.yaml`](artifacts/mig-device-check.yaml):

```bash
kubectl apply -f mig-device-check.yaml
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/faig-mig-check \
  --timeout=120s
kubectl logs pod/faig-mig-check
kubectl delete pod faig-mig-check
```

The YAML is in `gpu_tests/artifacts` on the controller; copy it to the host
first. It requests two slices in the default namespace and runs `nvidia-smi
-L`. In the recorded experiment the result was repeated after a host reboot.
Device visibility in `nvidia-smi` alone is not proof of CUDA peer communication.

## 4. Install FAIG with two slices — controller

The tested working tree's role defaults and 8.0.2 values template expose the
following values. They are local changes and were not committed at the recorded
HEAD. Review them before use:

```yaml
fortiaigate_gpu_enabled: true
fortiaigate_gpu_profile: l4               # development-only tuning used here
fortiaigate_vllm_gpu_attach: shared
fortiaigate_triton_gpu_count: 2
fortiaigate_triton_gpu_resource_name: nvidia.com/mig-1g.16gb
```

Set them in an **ignored** local profile or use explicit one-run extra vars;
do not overwrite unrelated operator values. The profile called `l4` is used
for its modest memory tuning and does not imply RTX PRO 4500 support.

```bash
ansible-playbook -i ansible/inventory/aws.generated.ini \
  ansible/playbooks/deploy_fortiaigate.yml \
  -e '{"fortiaigate_gpu_enabled":true,"fortiaigate_triton_gpu_count":2,"fortiaigate_triton_gpu_resource_name":"nvidia.com/mig-1g.16gb"}'
```

The role pre-pulls the three large images, lints and renders the supplied chart,
and applies the repo's post-renderer to the 8.0.2 release. No credentials are
required on the command line. Confirm the rendered shared pod requests two MIG
resources and contains `--tensor-parallel-size=2`. The initial deployment on
this host did **not** start vLLM without the additional experimental changes
below.

## 5. Apply the temporary vLLM/MIG experiment — host

Review the scripts in `gpu_tests/artifacts` before copying them to the host.
They modify a live deployment and are intentionally **not** integrated into
Helm. The current test was on a trusted single-node host. They may not be
idempotent: some assert that their mount/variables do not already exist.

1. The original image reported NCCL 2.30.7 from vLLM; a separate PyTorch query
   returned 2.29.7. Create an isolated host directory and download the
   **specific** NVIDIA NCCL 2.31.2 library by copying and running
   `fetch-nccl-2.31.2.py` with appropriate permissions. The script verifies the
   wheel using the SHA-256 published in PyPI metadata; also compare the
   extracted shared library with the SHA-256 in the experiment report. This
   does not establish vendor compatibility. Never replace the image's files.
2. Read the two current MIG UUIDs from `nvidia-smi -L` on the host. Do not
   copy UUIDs from an old machine. Set them explicitly in the vLLM container;
   this worked around PyTorch's one-physical-GPU NVML count. The two UUIDs must
   be the *same devices actually allocated by the probe*; compare with the
   `gpu-probe` init log and the pod's `fortiaigate.io/gpu-device` annotation
   before applying. Read the probe annotation into a comma-separated `MIG_UUIDS`
   variable on the host, then verify it is nonempty and lists the expected two
   allocated slices:

   ```bash
   MIG_UUIDS="$(kubectl -n fortiaigate get pod -l app=triton-vllm-server \
     -o jsonpath='{.items[0].metadata.annotations.fortiaigate\.io/gpu-device}')"
   test -n "$MIG_UUIDS" || { echo "GPU probe annotation is missing" >&2; exit 1; }
   kubectl -n fortiaigate set env deployment/triton-vllm-server -c vllm \
     "CUDA_VISIBLE_DEVICES=$MIG_UUIDS" NCCL_MNNVL_ENABLE=0 \
     NCCL_MULTI_RANK_GPU_ENABLE=1 NCCL_DEBUG=WARN
   ```

   This value is static and can become stale after replacing or recreating
   slices; fail closed and re-check rather than assuming it follows allocation.
3. Copy and run `mount-nccl-test.py` on the host. It is reconstructed to
   match the final working state; the original failing preload patch is saved
   separately as `mount-nccl-original-failed.py` and must not be run. It adds the read-only
   `/opt/faig-lab/nccl-2.31.2` hostPath mount and sets
   `VLLM_NCCL_SO_PATH=/opt/faig-nccl-lab/libnccl.so.2`. **Do not set
   `LD_PRELOAD`**: that attempt caused the sealed vendor loader to reject the
   installation. The experiment uses NCCL 2.31.2 only in vLLM's selected
   library path; it is not a supported replacement of the full vendor stack.
4. Copy and run `disable-custom-all-reduce.py` and `set-memory-budget.py` on
   the host. The first adds `--disable-custom-all-reduce`; the second changes
   `--gpu-memory-utilization` to `0.62`. These scripts identify the vLLM
   container by name but assume the chart and argument shapes observed in
   this release; inspect the diff before use.
5. Wait for the shared deployment and inspect logs and per-slice memory:

   ```bash
   kubectl -n fortiaigate rollout status deployment/triton-vllm-server --timeout=300s
   kubectl -n fortiaigate logs deployment/triton-vllm-server -c gpu-probe
   kubectl -n fortiaigate logs deployment/triton-vllm-server -c vllm --tail=100
   nvidia-smi
   ```

   Verify both workers load, the model is Ready, and actual inference works.
   The recorded pod took minutes to decrypt, initialize workers and warm up.
   A successful `nvidia-smi` list or temporary worker memory allocation is not
   enough. Diagnostic logs may include request details; sanitize before sharing.

## 6. License inventory and scanning — host and FAIG GUI

Upload valid GPU licenses via the FAIG GUI; never save them in the repo. The
recorded UI counted the two slices as one physical GPU, with three valid
licenses. Check **Security Scanning** and inspect logs; the GUI may show
licensed cards while scanning is paused for another reason.

The recorded MIG run had a specific inventory mismatch: the Triton and vLLM
reporters on `:9109` and `:9110` correctly reported the physical GPU, but the
additional native Triton `:8002` scrape had no `gpu_uuid` metric. Guardrail
reported an unreadable source and licensing paused scanning. The temporary
experiment cleared only the optional native-metrics endpoint:

```bash
kubectl -n fortiaigate set env deployment/guardrail \
  GUARDRAIL_METERING_METRICS_ENDPOINTS=
kubectl -n fortiaigate rollout status deployment/guardrail --timeout=90s
```

Before doing this, verify the dedicated reporters and service-pair checks are
present and reporting accurate, complete inventory. Removing the fallback
reduces redundancy and must not be used to conceal missing/unlicensed GPUs.
The test was single-node, and this workaround is not verified for multiple
engines or nodes. Confirm the license manager reports zero unreadable sources
and the actual expected physical GPU count. The original gateway continued to
log skipped scans after the license manager enabled scanning; restarting the
gateway refreshed it:

```bash
kubectl -n fortiaigate rollout restart deployment/llm-gateway
kubectl -n fortiaigate rollout status deployment/llm-gateway --timeout=90s
kubectl -n fortiaigate logs deployment/llm-gateway --tail=80
```

Verify the gateway reports `scanning_enabled=true` and the GUI agrees. Do not
proceed as if traffic is protected when the GUI or logs report paused scanning.

## 7. Test and preserve evidence

Deploy LiteLLM using the operator's **existing local-only** credentials and the
repo's `deploy_litellm.yml`, then verify a short direct Bedrock request. The
service in this test was internal-only. Set up the FAIG provider, model,
workspace/key bindings and policy, and upload licenses through the GUI. Do not
paste keys into chat or commit them.

Send a benign control request, a deterministic safe matching request, and a
natural-language detector case through the virtual key. Verify the FAIG Traffic
Log identifies the expected detector and action, and verify the model path
actually used PolicyGuard. Use synthetic data for DLP and compare the log's
Original and Modified views: a redacted value can be restored in the response.
Collect timestamps, per-slice `nvidia-smi`, model logs, license state, expected
versus actual outcomes and performance; remove credentials and sensitive
prompt content before recording them. GPU and license information alone is not
proof of enforcement.

The GPU host is billable. Use the approved teardown workflow when testing is
complete, preserving ECR if desired. Do not use `terraform destroy` on the ECR
state unless the owner explicitly requests deletion of the images.
