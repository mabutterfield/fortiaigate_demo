# G7 dual physical GPU baseline — November 12, 2026

This is a lab observation, not a Fortinet support statement. The subsequent
test should use one 16 GB MIG slice on each physical card; it has not yet been
performed as of this baseline.

- AWS `us-east-1`, `g7.12xlarge`, two NVIDIA RTX PRO 4500 Blackwell Server
  Edition GPUs, each reporting 32,623 MiB, MIG disabled.
- Ubuntu host, NVIDIA open driver 595.91.07 and CUDA 13.2 as reported by
  `nvidia-smi`; k3s foundation validation reported GO, including GPU container
  and local-path PVC checks. Kubernetes allocatable: two `nvidia.com/gpu`.
- Instance-store NVMe mounted at `/mnt/local` for the k3s image cache.
- Both physical GPUs advertise `MIG 1g.16gb`, profile ID 5, with 15.66 GiB
  usable per instance and two available per card. No MIG instances exist in
  this baseline. The profile lists P2P as unavailable.
- Standard FortiAIGate 8.0.2 deployment, shared Triton/vLLM, two physical
  GPU resources, `tensor_parallel_size=2`, GPU memory utilization 0.80.
  The experimental MIG NCCL, CUDA visibility, memory and all-reduce patches
  from the prior test were not applied.
- At 13:47 UTC all FAIG pods were ready, including both containers in
  `triton-vllm-server`. vLLM reported healthy; a direct, internal chat
  completion returned HTTP 200 with 24 completion tokens and finish reason
  `length`. This verifies model execution, not policy enforcement.
- vLLM logged 7.12 GiB for model loading on TP0, 16.35 GiB available KV
  cache, and 1,134,741 GPU KV-cache tokens. It reported `CUSTOM` and `PYNCCL`
  all-reduce backends for the TP group.

`nvidia-smi` at 13:47:14 UTC, abbreviated:

```text
GPU 0: 29216 MiB / 32623 MiB; MIG disabled
GPU 1: 29652 MiB / 32623 MiB; MIG disabled

GPU 0 tritonserver      2130 MiB
GPU 0 VLLM::Worker_TP0 27006 MiB
GPU 1 tritonserver      2566 MiB
GPU 1 VLLM::Worker_TP1 27006 MiB
```

Most allocated vLLM memory is not model weights alone; the configured KV
cache and runtime allocations account for additional use. Fresh license,
provider, policy and virtual-key setup and end-to-end scanning verification
were still pending at this observation. LiteLLM was deployed and ready.
The initial license managers restarted while the new database was being
migrated, then recovered after the API finished migration.

At 13:57 UTC the user confirmed two physical GPUs and two GPU licenses in
the GUI. The gateway logged license restoration and `scanning_enabled=true`.
No end-to-end guardrail enforcement test was performed for this baseline.
