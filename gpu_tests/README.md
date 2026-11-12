# FortiAIGate 8.0.2 GPU tests

This directory records the November 11, 2026 GPU experiments and the exact
lab-only deviations used to reproduce the G7 two-slice test. Times are UTC
unless otherwise specified. These results are point-in-time observations, not
Fortinet support statements or production recommendations.

- [Experiment report](2026-11-11-gpu-experiment.md): L4 baseline, CPU-only
  behavior, G7 MIG results, observations, failures and log excerpts.
- [Next: two physical GPUs](2026-11-12-dual-gpu-plan.md): prepared plan,
  two-GPU MIG helper and validation gates.
- [Reproduction guide](reproduce-g7-mig.md): prerequisites, host bootstrap,
  MIG setup, Helm values, temporary patches, license/inspection verification
  and cleanup boundaries.
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

The current G7 experiment used a host-mounted NCCL library and manually
patched Kubernetes workloads. **A Helm upgrade or a normal bootstrap rerun
can remove or conflict with these patches.** The artifacts do not make this
configuration upgrade-safe, and the host is billable until destroyed.
