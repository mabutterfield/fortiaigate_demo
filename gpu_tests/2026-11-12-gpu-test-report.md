# FortiAIGate 8.0.2 GPU and CPU experiments

**Test dates:** November 11–12, 2026

**Scope:** Single-node lab deployments using FortiAIGate 8.0.2 build 0055,
k3s, LiteLLM and an upstream Bedrock model.

## Goals

Determine the practical GPU memory requirements of FortiAIGate 8.0.2 and
whether its inference workloads could run on less expensive home-lab hardware.
Specifically, we wanted to:

1. Establish a working single-GPU baseline with governance, DLP and natural
   language detection enabled.
2. Test whether PolicyGuard's vLLM model can be split across two approximately
   16 GB GPU devices, first on one physical GPU and then across two cards.
3. Assess whether one 16 GB device could run vLLM, and whether Triton and
   vLLM could be placed on separate devices.
4. Explore whether Triton could run on the CPU while vLLM used both GPUs.

These were short functional experiments, not sizing, load, longevity or
security-certification tests. MIG slices on data-center GPUs are not identical
to standalone home-lab cards. Fortinet's reviewed 8.0.2 guide does not list the
L4 or RTX PRO 4500 as supported GPUs and states that DLP and Natural Language
detectors require a GPU. The CPU-Triton configuration is experimental and is
not a Fortinet support statement.

## Test environment

| AWS instance | GPU arrangement | Purpose |
| --- | --- | --- |
| `g6.4xlarge` | One NVIDIA L4, nominal 24 GB; 23,034 MiB reported | Single-GPU baseline and GPU-disabled test |
| `g7.4xlarge` | One NVIDIA RTX PRO 4500 Blackwell Server Edition, nominal 32 GB, divided into two `1g.16gb` MIG slices | Test two logical devices on one physical GPU |
| `g7.12xlarge` | Two RTX PRO 4500 cards, nominal 32 GB each; one `1g.16gb` slice on each | Compare full cards, two physical GPUs, separate engines and CPU Triton |

Each G7 slice reported 16,032 MiB. The G7 hosts used Ubuntu 24.04, NVIDIA open
driver 595.91.07, NVIDIA Container Toolkit 1.20.2, k3s `v1.35.10+k3s1`, and
NVIDIA device plugin v0.17.0. The k3s foundation used a guarded AWS local
instance-store device for the container image cache and a 300 GiB root volume.
The tested images included `faig-models:0.0.5-s1`,
`vllm-server:0.28.0-rpt-s1` and
`custom-triton:25.11-onnx-trt-agt-rpt-s1` from the operator's ECR.

The `l4` chart tuning profile was used for these development tests. It is not
a complete sizing recommendation. Licenses, Fortinet artifacts, user profiles
and credentials are not included in this repository.

## Results

### One L4: working baseline

The normal GPU-enabled FAIG deployment was installed on the `g6.4xlarge`,
licenses were uploaded, and LiteLLM and a provider, model, policy and virtual
key were configured. Benign traffic passed. Prompt injection and a Unicode
bidi-control input were blocked; the Traffic Log showed synthetic email and
SSN DLP input redaction. A synthetic card number matched DLP but was blocked
by a separate safety rule. The Palo Alto firewall natural-language policy
showed that neutral comparisons can need tuning.

After enabling the detectors, an idle `nvidia-smi` snapshot reported:

| Allocation | MiB |
| --- | ---: |
| vLLM process | 16,862 |
| Triton process | 2,400 |
| Total GPU usage | 19,276 of 23,034 |

The single-GPU model loader reported approximately 13.8 GiB of weights;
vLLM's process allocation also included runtime and cache memory. This idle
snapshot is not peak usage and does not prove that both engines fit or remain
stable on a 20 GB card. See the [L4 and original MIG report](2026-11-11-gpu-experiment.md).

### Global GPU disabled: traffic forwarded without inspection

Setting `fortiaigate.gpu.enabled: false` and rebooting left vLLM undeployed.
Triton loaded its model on CPU, but the Licenses page reported zero GPUs and
security scanning paused. A bidi-control prompt passed through and the
upstream model, rather than FAIG, refused a prompt-injection request. A ready
GUI and successful request did not mean inspection was active.

### Two 16 GB MIG slices on one physical GPU

The `g7.4xlarge` host required NVIDIA's open kernel driver. Two MIG instances
were created and exposed to k3s; the NVIDIA device plugin needed a temporary
privileged-container workaround for an insufficient-permissions error. The
host-local MIG layout and device-plugin test survived a reboot.

Getting vLLM to use both slices required several manual lab changes: explicit
MIG UUID visibility, a host-mounted NCCL 2.31.2 library, NCCL settings for the
same-physical-GPU layout, disabled custom all-reduce, and a reduced 0.62 GPU
memory target. A native Triton metrics endpoint lacked the GPU labels expected
by FAIG's licensing inventory, so an additional temporary metering workaround
and gateway restart were required. The shared Triton/vLLM pod became ready;
benign, injection and bidi-control tests worked after scanning was confirmed
enabled. These imperative changes are isolated from the normal deployment.

### Two physical GPUs: full cards and one MIG slice per card

On the `g7.12xlarge`, the normal k3s GPU and storage checks passed. With MIG
disabled, vLLM tensor parallelism across both full cards became healthy and
answered an internal inference request without the earlier MIG-specific
patches. Both physical GPUs and two licenses were recognized.

We then enabled one `1g.16gb` slice on each physical card. The experimental
helper was corrected for the installed driver's `nvidia-smi` output and then
created and recognized the intended layout. The device plugin again needed the
lab privilege workaround. Kubernetes allocation and the GPU reporters were
checked against the physical parent devices.

With a 0.80 vLLM memory target and a 16,384-token context, the unmodified
vLLM image loaded on both slices without the prior NCCL or UUID patches.
Each worker reported approximately 7.12 GiB of weights and 3.24 GiB of KV
cache. One snapshot showed 15,445/16,032 MiB on one slice and
15,881/16,032 MiB on the other, including Triton. The second slice had only
151 MiB free at that point.

The native Triton MIG-metrics issue again paused scanning. After verifying both
dedicated reporters covered both GPUs, we temporarily excluded the unreadable
native metrics source and refreshed the gateway. With scanning enabled, benign
traffic passed, prompt injection and bidi input were blocked, DLP logged an
email redaction, the Palo Alto praise and ordering requests were blocked, and
a neutral comparison passed. See [two-physical-GPU results](2026-11-12-dual-physical-mig.md).

### One 16 GB slice for vLLM; separate Triton and vLLM

To isolate vLLM's minimum, we temporarily made Triton idle and ran vLLM on one
slice with one sequence, eager execution and a 1,024-token context. The full
weights used 13.8 GiB. A 0.97 memory target failed during warmup; a 0.93
target reached readiness but ran out of memory on a request. At 0.91, one
short direct inference succeeded, with 15,966/16,032 MiB allocated afterward.
That is a narrow model-level success with only 66 MiB free, not a practical
full-policy result. See [single-slice details](2026-11-12-single-slice-vllm.md).

The chart's dedicated mode then placed Triton on one physical GPU's slice and
vLLM on the other. Both pods became healthy, but the existing governance rule
definitions did not fit the 1,024-token context and governed requests failed
closed with HTTP 503. A 3,072-token retry either lacked sufficient KV cache
to start or ran out of GPU memory on an actual governed request. No request
was sent upstream in those failures. Separate scheduling worked; full-policy
operation with one 16 GB slice for vLLM did not. See [dedicated-engine results](2026-11-12-dedicated-slices.md).

### CPU Triton with vLLM across both GPU slices

An isolated CPU-only Triton pod loaded `sensitive_model` and returned the
expected tensor shape for a synthetic inference. One request took about 2.0 s
on CPU and 0.012 s on GPU; this single comparison is not a benchmark and did
not prove equivalent DLP decisions.

We then deployed CPU-only Triton alongside a dedicated vLLM pod using both
physical-GPU MIG slices. This used lab-only Helm values and a post-renderer;
the normal deployment was not changed. Triton had no GPU devices and vLLM
was the only GPU process. Each slice used approximately 13,464/16,032 MiB,
leaving about 2.5 GiB free, while CPU Triton used about 3.4 GiB system RAM at
one observation.

CPU Triton's GPU reporter could not initialize NVIDIA's management library.
After verifying Triton had no GPU access and vLLM's reporter identified both
physical GPUs, the lab metering override used only vLLM's reporter and its
service-pair check. This reduced inventory coverage and is not a production
or supported licensing configuration. With the gateway reporting scanning
enabled, a benign request passed, a fictional email produced a DLP `ERASE`
action, the Palo Alto ordering request was blocked and a neutral fact passed.
Individual request times ranged from about 1.0 to 6.7 seconds; they are not
throughput measurements. The client saw the original email, consistent with
the earlier observed response rehydration. See [CPU Triton and dual-vLLM results](2026-11-12-cpu-triton-dual-vllm.md).

## Lessons learned

- **Measure inspection, not just readiness.** The GUI, pod readiness, a
  `Governed` traffic label or HTTP 200 alone cannot prove that scanning ran.
  Check license inventory, gateway state, detector attribution and traffic logs.
- **Weights are not the whole memory requirement.** vLLM also needs KV cache,
  CUDA/runtime allocations and transient attention workspaces. Triton adds
  its own model and runtime allocations when colocated.
- **Two MIG slices are not pooled memory.** Model parallelism must explicitly
  use both devices; two slices on one physical GPU behaved differently from
  slices on two physical GPUs.
- **A healthy model may still be unusable for a policy.** Reducing context can
  make startup possible while leaving too little room for detector definitions
  or the inference workspace. FAIG's fail-closed response was important.
- **CPU model execution is not automatically supported CPU inspection.** The
  CPU Triton result worked for the tested requests, but required an explicit
  licensing-inventory workaround and has not been tested for long-term use,
  broad DLP equivalence or load.
- **Licensing follows physical GPUs, not MIG slice count.** Reporter failures
  can pause scanning even when enough licenses are installed. Removing a
  failing reporter or metrics source reduces coverage and must never conceal
  an unreported GPU.
- **Keep experiments separate.** MIG setup, the privileged plugin, host NCCL
  override, CPU post-renderer and metering patches are lab-only. The normal
  8.0.2 path retains its guarded local-storage and standard GPU wiring.
- **20 GB remains a hypothesis.** The L4 idle result suggests one 20 GB card
  might fit both engines, but usable memory, peak allocations, concurrency and
  support on the intended card remain unverified. A longer L4 peak-memory test
  and an actual target-card test are the logical next checks.

Detailed commands, artifacts and limitations are indexed in the
[GPU test README](README.md). A clean-host replay of the combined experiments
has not yet been completed.
