# G7: one 16 GB MIG slice on each of two physical GPUs

November 12, 2026. Disposable, single-node lab; not a supported deployment
claim. See the adjacent dual-physical baseline for host and driver details.

The two RTX PRO 4500 cards each advertised profile ID 5 (`1g.16gb`). After
stopping the GPU workload, the experimental host helper created one slice per
GPU. `nvidia-smi -L` and a temporary Kubernetes pod confirmed that the two MIG
UUIDs mapped to different physical parent GPUs. Kubernetes advertised exactly
two `nvidia.com/mig-1g.16gb` resources. A host-local systemd service was
installed to recreate this layout before k3s; reboot persistence has not yet
been tested on this host.

The NVIDIA device plugin failed with `error getting device memory info:
Insufficient Permissions` in mixed mode. The lab used the same privileged
device-plugin workaround as the previous test; it is not part of the normal
deployment workflow.

The unmodified FAIG vLLM image started with tensor parallel size 2, memory
utilization 0.80 and 16,384 maximum model length. It loaded 7.12 GiB of weights
per worker, reported 3.24 GiB KV cache and 225,054 cache tokens, became healthy,
and returned HTTP 200 to a direct internal 24-token inference request. It used
PYNCCL across the two physical GPUs. The prior same-physical-GPU test's NCCL
replacement, CUDA UUID visibility override, disabled custom all-reduce, and
reduced 0.62 memory target were not applied.

Observed `nvidia-smi` after inference:

```text
GPU 0 MIG: 15445 / 16032 MiB; Triton 1974 MiB; TP0 13394 MiB
GPU 1 MIG: 15881 / 16032 MiB; Triton 2410 MiB; TP1 13394 MiB
```

The second slice had only 151 MiB free at that instant, so stability under
other loads is unproven. The figures include runtime and cache allocations,
not just weights.

Scanning initially paused even though both licenses were valid: the native
Triton `:8002` metrics endpoint lacked `gpu_uuid` labels. Both dedicated
reporters (`:9109` and `:9110`) were independently checked and each correctly
mapped both MIG UUIDs to the two physical GPUs. The lab temporarily cleared
only `GUARDRAIL_METERING_METRICS_ENDPOINTS`, leaving dedicated reporters and
service-pair checks intact, and restarted the gateway. License manager then
reported two cards, two valid licenses, zero unreadable sources and scanning
enabled; gateway logged `scanning_enabled=true`. This reduces metrics
redundancy and is not validated for multiple nodes or a production deployment.
At 14:31–14:32 UTC, after the user configured a provider and policy, governed
end-to-end tests through model `litellm-pass-model` returned the expected benign
response, blocked the prompt-injection test, and blocked an input containing a
Unicode bidi override. The gateway attributed the injection deny to General AI
Safety Guard; guardrail logs also recorded an OWASP policy deny. The normalizer
blocked the bidi request. Both block responses had `finish_reason` set to
`content_filter`. The benign request's input and output both appeared in scan logs.

At 14:33–14:34 UTC after DLP and the Palo Alto firewall natural-language
detector were added, a fictional email input produced a DLP `ERASE` action;
the client response contained the original email. The user reported that the
Traffic Log's LLM Messages showed the assistant response as `[REDACTED_EMAIL_1]`,
consistent with the gateway restoring the original value to the client. The NLP
detector blocked both a praise request and an order request. A neutral product
fact request and a neutral comparison passed; input and output scan logs showed
no NLP deny for the comparison. This does not establish behavior for all
phrasings or sensitive information types.

On first use the two-GPU helper refused to run because `nvidia-smi -i -L` is
unsupported by the installed driver; its profile check also hit `pipefail` on
early grep exit. The isolated experimental helper was fixed to parse the full
listing by parent GPU and capture profile output before matching. It then ran
successfully and recognized its existing layout on a second invocation.
