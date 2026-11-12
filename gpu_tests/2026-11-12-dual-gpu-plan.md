# Next test: one 16 GB MIG slice on each of two physical GPUs

Prepared November 11, 2026 for a later session; **nothing in this file launches
an instance**. This is an experimental plan, not a validated installation or
Fortinet support statement. The previous result used two MIG devices on one
physical G7 GPU; this test changes the topology and may behave differently.

## Goal and decision points

Use one `g7.12xlarge` in `us-east-1` with two RTX PRO 4500 Blackwell 32 GB
physical GPUs. Create a single `1g.16gb` MIG instance on GPU 0 and one on GPU 1;
leave the other half of each physical GPU unallocated. Kubernetes should see
exactly two schedulable `nvidia.com/mig-1g.16gb` devices, one per physical
card. Run FAIG with tensor parallel size two and compare the November 11
baseline's startup, detection, memory, latency, licensing and traffic results.

The two slices have isolated memory; neither automatically pools VRAM. A
successful test supports the model-parallel hypothesis but does not prove
consumer 16 GB cards, other GPU models, long-term stability or a supported
Fortinet deployment. CUDA P2P and MIG/NCCL behavior across physical GPUs must
be observed; avoid assuming the same-GPU setting or communications path applies.
The previous test needed an experimental NCCL 2.31.2 override, explicit CUDA
visibility, disabled custom all-reduce, a 0.62 GPU-memory budget and a metering
workaround. Try and document which are actually required on two physical GPUs.

## Current preparation and costs

- Local ignored `terraform/aws-ec2-k3s/99-local.auto.tfvars` now selects
  `g7.12xlarge`. Local ignored `ansible/group_vars/user.yml` sets
  `nvidia_expected_gpu_count: 2`, selects the NVIDIA 595 **open** driver and
  retains the GPU-enabled shared two-MIG FAIG values from the previous test.
- AWS described `g7.12xlarge` as 48 vCPUs, 192 GiB RAM, two 32 GiB GPUs and
  **one 1,900 GB nominal local NVMe disk**. The one-disk layout is compatible
  with the guarded instance-store selector in principle; inspect the actual
  device before permitting formatting on a fresh host.
- An earlier on-demand quote for Virginia was $7.12832/hour of instance
  compute; price, quota and capacity can change. Three hours would be about
  $21.38 for compute, before EBS, IPs, transfers, Bedrock and other charges.
  Have a teardown point and review current prices/capacity before applying.
- The prior instance was intentionally terminated; its root volume, FAIG
  database, installed licenses, user-defined policies and host-only test files
  are disposable unless backed up separately. ECR repositories/images and
  remaining shared prep/network resources were not included in the host-only
  termination. Public IP and EBS charges may continue where applicable.
- Re-read [the one-GPU report](2026-11-11-gpu-experiment.md) and
  [reproduction guide](reproduce-g7-mig.md). Their host-persistence script
  targets one GPU; **do not use it unchanged** for this experiment. The new
  `artifacts/faig-mig-two-gpus.sh` is a prepared, unvalidated two-GPU lab
  helper. It was tested against a simulated `nvidia-smi`, not real hardware.

## Proposed sequence for the session

1. Refresh AWS SSO, check all AWS resources and Terraform state, determine the
   current public subnet AZ, quota and live `g7.12xlarge` capacity. Do not
   assume the prior availability probe reserves capacity. Review the Terraform
   plan, including any orphaned or pending instance state, EIP association,
   instance-store and root-volume settings before applying.
2. Launch a fresh GPU host without installing FAIG. Bootstrap with the open
   NVIDIA driver, the correct `nvidia_expected_gpu_count: 2`, k3s, runtime and
   device plugin. Run the normal foundation GPU/PVC tests **before** MIG is
   enabled. Preserve ECR; only verify, do not recreate or destroy it.
3. Inspect both GPUs and profile IDs with `nvidia-smi`; verify each exposes
   `MIG 1g.16gb` as ID 5 and check all existing instances. Enable MIG and
   create **one** GPU/compute instance per physical GPU only after inspection.
   The prepared helper in `artifacts/faig-mig-two-gpus.sh` preflights the two
   GPUs and refuses unexpected existing layouts; it is hardware-dependent,
   experimental and not tested on this G7 size. If a step fails halfway, stop
   and inspect both GPUs; do not assume it rolled back the first GPU. Adapt the
   host-local systemd service only after verifying the script on this hardware.
4. Set the NVIDIA device plugin to mixed MIG mode and address any toolkit
   permission issue. The prior single-GPU host needed the privileged-plugin
   workaround; validate whether the same workaround is necessary. Verify
   Kubernetes reports exactly two MIG resources. Request both in a temporary
   pod; verify `nvidia-smi -L`, CUDA enumeration, and, crucially, the parent
   physical GPU for each MIG UUID. Mere enumeration of two slices does not
   establish they are on separate cards. Reboot-test persistence if time allows.
5. Deploy FAIG using the chart's shared Triton/vLLM mode, two MIG resources
   and the conservative `l4` tuning profile from the last test. Confirm the
   GPU-probe annotation lists precisely the two allocated MIG UUIDs. The
   chart's `gpuCount: 2` selects tensor parallelism 2. The old live Kubernetes
   patches and host-mounted NCCL do **not** carry over to the new host.
   Reapply only the reviewed steps in the reproduction guide; dynamic UUIDs
   must come from the new pod, never copied from the old host.
6. Start with an explicit checklist of which NCCL/visibility/all-reduce and
   memory settings are present. If the vendor NCCL fails across MIG devices,
   the prior checksum-verified NCCL 2.31.2 host-mount test can be repeated as
   an unsupported isolated experiment. `NCCL_MNNVL_ENABLE=0` was required by
   NVIDIA's documented experimental MIG mode; do not set
   `NCCL_MULTI_RANK_GPU_ENABLE=1` by default on separate physical GPUs unless
   diagnostics justify it. Watch for vLLM using the NVML physical-device count
   rather than CUDA's MIG count, NCCL initialization failures, custom all-reduce
   failures, and out-of-memory errors. Never infer model health from GPU memory
   alone.
7. Upload licenses through the GUI and confirm the two physical cards are
   correctly counted and covered. The prior GUI showed three valid licenses on
   the old database, but a fresh database needs license upload again. Verify
   real reporter coverage and scanning state; do not disable inventory checks
   to mask missing cards. The prior native Triton metrics fallback had no GPU
   labels under MIG, and the earlier gateway also needed a restart to pick up
   the scanning-enabled state. Reproduce or resolve both carefully.
8. Deploy LiteLLM with the existing local-only credentials, configure the new
   FAIG provider/model/workspace/virtual key and policies, and verify ordinary
   traffic, DLP modified input, a specific Natural Language block and a neutral
   comparison. Review Traffic Log detector attribution and gateway logs; do
   not treat `Governed`, HTTP 200 or 2/2 Ready as evidence of scanning.
9. Capture sanitized `nvidia-smi`, model logs, instance IDs only if needed,
   GPU memory per slice, model readiness, KV cache, actual latency/concurrency,
   license inventory, security outcomes, cost and cleanup. Keep credentials,
   license contents, Terraform state and real sensitive inputs out of Git.
   Run a reviewed teardown at the end while preserving ECR.

## Explicit limits

The prior deployment's NCCL mount, GPU UUID environment, memory/all-reduce
arguments and metering changes were imperative live patches. They are not
preserved by a fresh Helm deployment or normal bootstrap. The two-GPU helper
and this sequence have not yet been exercised on real two-GPU hardware. A new
license, scanning-enabled state or a working inference call alone does not
prove the full security policy is active. User data and licensing constraints
must be checked before moving images or records to another provider.
