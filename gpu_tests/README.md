# FortiAIGate 8.0.2 GPU tests

This directory records the November 11–12, 2026 GPU experiments and the exact
lab-only deviations used in the G7 tests. Times are UTC
unless otherwise specified. These results are point-in-time observations, not
Fortinet support statements or production recommendations.

- [Consolidated GPU and CPU test report](2026-11-12-gpu-test-report.md):
  goals, instance details, results, changes required and lessons learned.
- [Experiment report](2026-11-11-gpu-experiment.md): L4 baseline, CPU-only
  behavior, G7 MIG results, observations, failures and log excerpts.
- [Next: two physical GPUs](2026-11-12-dual-gpu-plan.md): prepared plan,
  two-GPU MIG helper and validation gates.
- [Reproduction guide](reproduce-g7-mig.md): prerequisites, host bootstrap,
  MIG setup, Helm values, temporary patches, license/inspection verification
  and cleanup boundaries.
- [Two physical GPUs and two MIG slices](2026-11-12-dual-physical-mig.md):
  model and governed policy results for one slice on each GPU.
- [Single-slice vLLM](2026-11-12-single-slice-vllm.md) and
  [dedicated engines](2026-11-12-dedicated-slices.md): memory limits and failed
  full-policy attempts with one 16 GB slice for vLLM.
- [CPU Triton probe](2026-11-12-triton-cpu-probe.md) and
  [CPU Triton with dual-GPU vLLM](2026-11-12-cpu-triton-dual-vllm.md):
  unsupported CPU model and full-policy lab tests, including metering limits.
- [Artifacts](artifacts/): `nvidia-smi` and selected non-secret log captures, the exact
  host-local MIG boot configuration, the temporary CUDA allocation test, and
  the one-off NCCL and workload patch scripts, including the failed preload
  version and a reconstructed version matching the final settings.
  They are evidence and manual lab helpers; they are not integrated into the
  supported deployment workflow.

The vendor chart is **not** vendored here. The experiment used the extracted
`FAIG_helm/8.0.2/fortiaigate` chart in the parent workspace, from Fortinet's
`FAIG_helm_chart-V8.0.2-build0055-FORTINET.tar.gz`. Use the operator's licensed
copy, not a copy checked into this repository. User profiles, credentials,
license files, Kubernetes Secrets, rendered Helm manifests, Terraform state,
cluster IP addresses and GPU UUIDs do not belong in this directory.

The first single-physical-GPU MIG test used a host-mounted NCCL library and
manual Kubernetes patches; the later two-physical-GPU model did not need the
NCCL override. The CPU Triton layout additionally excludes its GPU reporter
from experimental metering. **A Helm upgrade or a normal bootstrap rerun can
remove or conflict with these changes.** Nothing in this directory is invoked
by the normal deployment workflow. Do not use the lab metering workaround to
hide an unreported GPU, and verify license coverage and inspection explicitly.
