# 2026-11-11: L4 baseline, CPU-only and two-slice G7 MIG experiment

## Scope and result

We tested whether FAIG 8.0.2 build 0055 can run its DLP and natural-language
inference workloads with two approximately 16 GiB GPU devices, as a step
on the way to evaluating inexpensive 12/16 GB home-lab cards. The final test
used **two MIG slices on one physical GPU**, not two independent cards. A
successful functional experiment therefore does not prove that two physical
cards, other GPU models, or production configurations work.

On an AWS `g7.4xlarge` in `us-east-1`, the FAIG shared Triton/vLLM pod reached
2/2 Ready, PolicyGuard returned an internal synthetic inference response, and
an ordinary request passed through FAIG, LiteLLM and Bedrock. After a metering
workaround and a gateway restart, the gateway logged that security scanning was
ON; test bidi-control and prompt-injection requests returned the FAIG block
message. Individual blocked requests were not correlated to their specific
Natural Language or other detector in this report. No sustained load, response
quality, security coverage or long-term reliability test was performed.

This setup is experimental: the RTX PRO 4500 was not on the 8.0.2 supported-GPU
list reviewed, the node runs a privileged NVIDIA device plugin, and vLLM uses a
newer NCCL library mounted from the host. Confirm vendor licensing and support
before treating any of this as supported. **Never assume that HTTP 200, a
ready pod, a `Governed` traffic label, or a successful model response means
security scanning is active.** The gateway previously passed traffic without
inspection while claiming readiness.

## Test context

- Repository: `fortiaigate_demo_802`, branch `feature/fortiaigate-8.0.2`;
  HEAD at capture `fa28ce5d309cf31cc41e85de7b9d2b006eb5e9eb`, with substantial
  uncommitted 8.0.2 foundation and deployment work. The hash alone does not
  reproduce that working tree; see the [reproduction guide](reproduce-g7-mig.md).
- Vendor chart: FortiAIGate 8.0.2 build 0055, outside the repo at
  `../FAIG_helm/8.0.2/fortiaigate` relative to the repo root. Chart `values.yaml`
  SHA-256 `6a8ff3944d766706eeabe9a1dd8dfa465133a5ccabfb97d0a6fe44f0da3e1a35`;
  `Chart.yaml` SHA-256
  `3686048ccc3856236c3a8567a80a539a14f4d8de8c98d2937fb6f07ff0968bda`.
  These are file hashes, not a checksum of the entire chart.
- Container tags: `faig-models:0.0.5-s1`,
  `vllm-server:0.28.0-rpt-s1`,
  `custom-triton:25.11-onnx-trt-agt-rpt-s1`, and build-0055 FAIG services.
  Images were pulled from the owner's ECR repositories, which were retained.
- G7: one RTX PRO 4500 Blackwell Server Edition, 32 GB marketed VRAM, two
  `1g.16gb` GPU instances, each reporting 16,032 MiB / 15.66 GiB; 16 vCPU,
  64 GiB host RAM, 875 GB nominal local NVMe and a 300 GiB root volume.
- Ubuntu 24.04; NVIDIA **open** driver `595.91.07`; host `nvidia-smi` reports
  CUDA 13.2 driver capability; NVIDIA Container Toolkit 1.20.2;
  k3s `v1.35.10+k3s1`; NVIDIA device plugin manifest v0.17.0. Host CUDA
  capability is not the same as the user-space CUDA version in the image.
- Existing role values selected the development-only `l4` tuning profile to
  keep Triton at one DLP instance per visible device, `vllm.gpuAttach: shared`,
  a 16,384-token context and 64 maximum sequences. This was a pragmatic test
  setting, not a supported tuning for the Blackwell GPU.

## L4: one GPU, working baseline

On a `g6.4xlarge` L4, FAIG, LiteLLM and Bedrock served a synthetic request
through a virtual key. Security guardrails blocked a prompt injection and a
Unicode bidi-control input. The owner verified the Traffic Log showed DLP
input redaction for a synthetic email and SSN; a synthetic card was redacted by
DLP but blocked by a separate General AI Safety rule. A neutral firewall
comparison was blocked on one run and allowed on a later run, so its
natural-language policy needs tuning. The observations are not a comprehensive
security evaluation.

The owner supplied these idle snapshots before and after adding DLP/NLP
configurations. The processes remained the same; the change is not a measurement
of peak or per-detector overhead. The relevant original `nvidia-smi` lines are
also preserved in [the L4 snapshot artifact](artifacts/nvidia-smi-l4-before-after-2026-11-11.txt):

```text
                         Before                After
GPU total                19,256 / 23,034 MiB   19,276 / 23,034 MiB
tritonserver              2,380 MiB             2,400 MiB
VLLM::EngineCore         16,862 MiB            16,862 MiB
```

Triton served the ONNX `sensitive_model` using TensorRT/CUDA. vLLM served
`policyguard`, the model behind Natural Language detectors. In that test the
single-card vLLM loader reported about 13.8 GiB for weights; this is distinct
from its overall GPU allocation.

## CPU-only test

Set `fortiaigate.gpu.enabled: false`, applied the chart and rebooted. The
GPU showed 0 MiB in use; the Triton log said its `sensitive_model` loaded on
`CPU device 0`; vLLM was not deployed. After the owner added a license, a
normal gateway request succeeded. However, the Licenses page showed one valid
license, zero GPUs in use and **security scanning paused because no GPU was
detected**; it said traffic passes without inspection. The gateway logged
that scanning was skipped. A bidi input passed and a prompt-injection request
received the upstream model's refusal, not a FAIG block. This conflicts in
practice with the guide's statement that other detector types remain available
without a GPU and needs Fortinet clarification. A CPU-loaded model is not proof
that DLP or any inspection is supported or active.

## G7 host and MIG foundation

The L4 instance was replaced with a fresh G7 instance and the existing Elastic
IP was reassociated. No ECR repositories were destroyed. The first foundation
bootstrap used `nvidia-driver-595-server`, and failed:

```text
nvidia-smi: No devices were found
NVRM: ... requires use of the NVIDIA open kernel modules.
```

Switched to `nvidia-driver-595-server-open`, corrected the role's computation
of the non-`-open` compute-utils package, and reran the foundation bootstrap.
The NVIDIA driver, k3s, GPU test container, ingress, DNS and local-path PVC
checks passed. One local NVMe disk was safely selected and mounted for the
containerd image cache.

MIG was enabled, and two `1g.16gb` profiles were created. Kubernetes initially
failed to start the device plugin in `mixed` mode:

```text
error getting device memory info: Insufficient Permissions
```

The isolated lab used a privileged NVIDIA device-plugin workaround for the
[NVIDIA toolkit issue](https://github.com/NVIDIA/nvidia-container-toolkit/issues/1740).
Kubernetes then advertised two `nvidia.com/mig-1g.16gb` devices. A temporary
CUDA-image pod requested both and displayed them with `nvidia-smi -L`. A
host-local systemd oneshot checked/recreated the two-slice layout before k3s;
the GPU layout, plugin registration and temporary pod test survived a reboot.
The host-local script refuses to alter a nonempty unexpected layout. These
settings are not yet automated by the repo's normal bootstrap.

## FAIG MIG rollout and troubleshooting

The current working tree adds deployment variables for GPU enablement, Triton
GPU count and resource name. The local profile selected GPU enabled, count 2,
`nvidia.com/mig-1g.16gb`, shared vLLM attachment and the `l4` tuning profile.
The chart's shared pod init probe requested both slices, annotated their MIG
UUIDs, and rendered `--tensor-parallel-size=2`.

1. **Device count:** the first vLLM attempt failed with `World size (2) is
   larger than the number of available GPUs (1)`. Inside the container,
   `nvidia-smi -L` and `cuDeviceGetCount` saw two slices; PyTorch's public
   pre-initialization device count and its NVML helper reported one. Explicit
   `CUDA_VISIBLE_DEVICES` containing both MIG UUIDs got vLLM past this check.
   The values were inserted as a manual deployment environment patch, not a
   dynamic chart value; UUIDs should be rediscovered after rebuilding.
2. **NCCL:** PyTorch reported NCCL 2.29.7, whereas vLLM's own log reported it
   loaded **2.30.7**. The two are distinct observations. Two ranks failed at
   `ncclCommInitRank` with `NCCL error: invalid usage`. NVIDIA documents
   [experimental multiple-MIG support starting with NCCL 2.31](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/communicators.html)
   and requires `NCCL_MNNVL_ENABLE=0`.
3. **Lab library override:** downloaded NVIDIA's `nvidia-nccl-cu13` 2.31.2
   wheel from PyPI, checked the wheel against its published SHA-256, extracted
   only `libnccl.so.2` into a separate host directory and mounted it read-only.
   The extracted library SHA-256 is
   `78103983bb558aef7277a0c05a9a5963e619a69f6e77ece3c449fb045a3368d4`.
   `VLLM_NCCL_SO_PATH` selected it without changing the vendor image.
   Process-wide `LD_PRELOAD` caused `sealed so_secret does not unwrap`; it
   was removed. This library substitution is not known to be vendor-supported.
4. **Same physical GPU:** with NCCL 2.31.2, warning logs said `Multiple Ranks
   are using the same GPU/Partition` and suggested
   `NCCL_MULTI_RANK_GPU_ENABLE=1`. Setting it got past communicator creation.
   The warning does not by itself explain whether NCCL classified the two MIG
   partitions as the same device, and this setting is not evidence of physical
   two-card behavior.
5. **Custom all-reduce:** vLLM then attempted to map MIG devices to physical
   NVML indexes and failed with `NVMLError_InvalidArgument`. Adding
   `--disable-custom-all-reduce` used the alternative communication path.
6. **Memory:** with `--gpu-memory-utilization=0.80`, vLLM requested 12.53 GiB
   per slice while only about 10.6–11.1 GiB was free after other allocations.
   Setting `0.62` got through startup. The rank-0 log reported
   approximately 7.12 GiB of model weights; both workers allocated GPU memory. During warmup vLLM reported
   about 0.42 GiB available KV cache, 29,323 cache tokens and an estimated
   1.79x concurrency for 16,384-token requests. These are model estimates,
   not measured throughput or peak headroom.

Live GPU output captured on the G7 at 18:50 UTC (trailing whitespace trimmed) is in
[nvidia-smi-g7-2026-11-11.txt](artifacts/nvidia-smi-g7-2026-11-11.txt).
Selected non-secret engine, inventory and scanning transition messages are in
[g7-selected-logs-2026-11-11.txt](artifacts/g7-selected-logs-2026-11-11.txt).
At that point the host reported 30,031 / 32,623 MiB total; the two slices
reported 15,241 / 16,032 MiB and 14,791 / 16,032 MiB. The individual vLLM
workers reported 12,754 and 12,746 MiB, while Triton reported 2,410 and
1,968 MiB. Those later, larger allocations matter more than the earlier
10–11 GiB warmup snapshots: there was less than 1.3 GiB per slice free at
this measurement. Memory includes weights, caches and runtime allocations;
these values cannot be summed as separate independent reservations.

## Licensing, inventory and end-to-end validation

The owner loaded three licenses; the UI showed one physical GPU in use and two
idle licenses. Although both GPU reporters mapped the two MIG IDs to one
physical GPU, the guardrail metering fallback also scraped native Triton
`:8002`, which under this MIG setup returned no `gpu_uuid` label. It therefore
reported one unreadable inventory source and the license manager paused
scanning. The UI accurately warned traffic would pass without inspection.

The temporary mitigation cleared only `GUARDRAIL_METERING_METRICS_ENDPOINTS`
while retaining the Triton and vLLM reporters on ports 9109 and 9110 and the
service-pair checks. The license manager subsequently reported three valid
licenses, one card and zero unreadable sources, then scanning enabled. This
reduces fallback coverage and is a lab workaround; if a reporter fails,
verify the remaining checks fail safely rather than assuming coverage.

The first gateway tests still passed uninspected even after the license manager
reported enabled. Restarting `llm-gateway` refreshed its state; its log then
reported `licence coverage restored: security scanning is ON`. A normal
`pass-model` request returned the expected synthetic response; the bidi and
prompt-injection tests returned the FAIG safety-block message. The upstream
LiteLLM service was deployed separately with an internal-only service, and its
Bedrock request returned HTTP 200. The owner's fresh FAIG provider, model,
policy and virtual key were used for the end-to-end test.

## Added DLP and Natural Language policy smoke test

After the owner added DLP redaction and a Natural Language rule to block
praise or ordering of Palo Alto Networks firewalls while allowing neutral
comparison/fact gathering, synthetic client requests produced these results
at approximately 19:00 UTC:

| Case | Client-observed result | Interpretation |
|---|---|---|
| Enthusiastic praise request | FAIG block message, HTTP 200, `content_filter` | Matches intended outcome; detector attribution still needs Traffic Log review. |
| Help ordering a Palo Alto firewall | FAIG block message, HTTP 200, `content_filter` | Matches intended outcome; detector attribution still needs Traffic Log review. |
| Neutral Fortinet/Palo Alto comparison | Allowed; output hit token limit | Matches allowed outcome, but response was incomplete. |
| Neutral product fact, retry with larger token budget | Allowed; response returned | Matches allowed outcome; not a factual-accuracy evaluation. |
| Repeat fictional `alice@example.com` | Original email visible in client response | Owner verified Traffic Log Modified input used `[REDACTED_EMAIL_1]`; detector `basic_dlp` matched Email address with Redact. The value was restored in the client response. |

The first fact-gathering attempt produced no visible response before the
512-token budget was exhausted; the 1,024-token retry completed. PolicyGuard's
vLLM logs showed inference activity during this window, but that alone does not
attribute individual praise or ordering blocks to the new detector. The owner
confirmed DLP's Modified input and detector finding. Check the two blocked
requests' detector findings before attributing their decisions to a particular
rule.

## Remaining questions

- Correlate each blocked request with its actual detector and prove a licensed
  Natural Language policy used the MIG-backed PolicyGuard path, then test DLP
  redaction on this configuration and check the Traffic Log.
- Measure startup, peak VRAM and host RAM, latency, concurrency, both allowed
  and denied inputs, and behavior when an engine or reporter becomes unavailable.
- Confirm vendor guidance for the GPU, MIG, library substitution and license
  accounting. Check why the gateway license state needed a restart.
- Reproduce and validate across Helm upgrades and host replacement before
  automating this setup. Current Kubernetes patches and host files are
  experimental and can be lost on redeploy.
- If useful, test `g7.12xlarge` with one 16 GB MIG slice on each of two
  physical GPUs; this is a different topology and incurs the full two-GPU cost.
